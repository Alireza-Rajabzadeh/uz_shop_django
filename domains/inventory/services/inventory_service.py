from core.services.base import BaseService
from domains.inventory.models import InventoryStrategy


class InventoryService(BaseService):
    model = InventoryStrategy
