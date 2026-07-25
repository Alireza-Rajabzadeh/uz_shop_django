from django.shortcuts import get_object_or_404


class BaseService:
    model = None

    def _get(self, id):
        return get_object_or_404(self.model, id=id)

    def _get_or_none(self, id):
        try:
            return self.model.objects.get(id=id)
        except self.model.DoesNotExist:
            return None

    def _list(self, **filters):
        return self.model.objects.filter(**filters)

    def _create(self, **data):
        return self.model.objects.create(**data)

    def _update(self, instance, **data):
        for attr, value in data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

    def _delete(self, instance):
        instance.delete()

    # Backward-compat aliases — will be removed as each domain adds explicit methods
    get = _get
    get_or_none = _get_or_none
    list = _list
    create = _create
    update = _update
    delete = _delete
