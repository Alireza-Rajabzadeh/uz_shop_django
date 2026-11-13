from enum import Enum


class BusinessServiceModeEnum(Enum):
    ONLINE = 1
    IN_PERSON = 2

    @property
    def code(self) -> str:
        return self.name.lower()
