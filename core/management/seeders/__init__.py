from .base import BaseSeeder
from .configs import CONFIG_SEEDERS, CONFIG_SEEDERS_MAP, get_config_seeder
from .developing import DEVELOPING_SEEDERS, DEVELOPING_SEEDERS_MAP, get_developing_seeder
from . import configs
from . import developing

# Aliases
config = configs
fake = developing

__all__ = [
    "BaseSeeder",
    "CONFIG_SEEDERS",
    "CONFIG_SEEDERS_MAP",
    "DEVELOPING_SEEDERS",
    "DEVELOPING_SEEDERS_MAP",
    "configs",
    "config",
    "developing",
    "fake",
    "get_config_seeder",
    "get_developing_seeder",
]
