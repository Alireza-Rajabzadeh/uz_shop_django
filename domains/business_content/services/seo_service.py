from ..models import SEORecord


class SEOService:
    #: Only the two page-shaped resources live in this domain. Catalog
    #: resources (product/category/brand) keep their SEO records in
    #: `domains.content`, which owns the public `seo/<type>/<slug>` route.
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
