from django.shortcuts import get_object_or_404


class BaseService:
    model = None

    def get(self, id):
        return get_object_or_404(self.model, id=id)

    def get_or_none(self, id):
        try:
            return self.model.objects.get(id=id)
        except self.model.DoesNotExist:
            return None

    def list(self, **filters):
        return self.model.objects.filter(**filters)

    def create(self, **data):
        return self.model.objects.create(**data)

    def update(self, instance, **data):
        for attr, value in data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

    def delete(self, instance):
        instance.delete()
