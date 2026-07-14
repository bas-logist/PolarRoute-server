from polarrouteserver.settings.base import *
from polarrouteserver.settings.development import *

STATIC_ROOT = os.getenv("POLARROUTE_STATIC_ROOT", None)
