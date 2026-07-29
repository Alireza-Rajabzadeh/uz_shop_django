from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _


User = get_user_model()


class ProfileServiceError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__(str(errors))


class AdminProfileService:
    def get_profile(self, user_id):
        return User.objects.prefetch_related("groups").get(pk=user_id)

    def update_profile(self, user_id, values):
        values = dict(values)
        current_password = values.pop("current_password", None)

        try:
            with transaction.atomic():
                user = User.objects.select_for_update().get(pk=user_id)
                final_username = values.get("username", user.username)
                final_email = values.get("email", user.email)
                sensitive_change = (
                    final_username != user.username or final_email != user.email
                )
                if sensitive_change and (
                    not current_password or not user.check_password(current_password)
                ):
                    raise ProfileServiceError({
                        "current_password": _(
                            "The current password is required and must be correct."
                        )
                    })

                for field, value in values.items():
                    setattr(user, field, value)
                if values:
                    user.save(update_fields=list(values))
        except IntegrityError as exc:
            raise ProfileServiceError({
                "username": _("A user with that username already exists.")
            }) from exc

        return self.get_profile(user_id)

    def change_password(self, user_id, current_password, new_password):
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=user_id)
            if not user.check_password(current_password):
                raise ProfileServiceError({
                    "current_password": _("The current password is incorrect.")
                })

            try:
                password_validation.validate_password(new_password, user=user)
            except ValidationError as exc:
                raise ProfileServiceError({"new_password": exc.messages}) from exc

            user.set_password(new_password)
            user.save(update_fields=["password"])
