from core.services.base import BaseService
from domains.location.models import City


class CityService(BaseService):
    model = City
