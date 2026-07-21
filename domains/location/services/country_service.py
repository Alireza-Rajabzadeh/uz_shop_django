from core.services.base import BaseService
from domains.location.models import Country


class CountryService(BaseService):
    model = Country
