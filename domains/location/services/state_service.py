from core.services.base import BaseService
from domains.location.models import State


class StateService(BaseService):
    model = State
