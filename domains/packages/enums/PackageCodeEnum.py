from enum import Enum


class PackageCodeEnum(Enum):
    FREE = 1
    PLUS = 2
    PRO = 3

    @property
    def code(self) -> str:
        return self.name.lower()
