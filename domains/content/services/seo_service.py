from domains.catalog.models import Brand, Category

from ..models import SEORecord


class SEOService:
    PUBLIC_RESOURCE_MODELS = {
        "brand": Brand,
        "category": Category,
    }

    @staticmethod
    def get_for(resource_type, resource_id):
        try:
            record = SEORecord.objects.get(
                resource_type=resource_type,
                resource_id=resource_id,
            )
        except SEORecord.DoesNotExist:
            return None
        return {
            "title": record.title,
            "description": record.description,
            "canonical_url": record.canonical_url,
            "image_id": record.image_id,
            "index": record.index,
            "follow": record.follow,
            "metadata": record.metadata,
        }

    @classmethod
    def get_public_resource(cls, resource_type, slug):
        model = cls.PUBLIC_RESOURCE_MODELS.get(resource_type)
        if model is None:
            return None
        resource = model.objects.filter(slug=slug).first()
        if resource is None:
            return None
        if resource_type == "category" and not cls._category_is_active(resource):
            return None
        return {
            "resource": {
                "id": resource.id,
                "slug": resource.slug,
                "name": resource.name,
            },
            "seo": cls.get_for(resource_type, resource.id),
        }

    @staticmethod
    def _category_is_active(category):
        seen = set()
        current = category
        while current and current.id not in seen:
            seen.add(current.id)
            if current.status.name.casefold() != "active":
                return False
            current = current.parent
        return current is None
