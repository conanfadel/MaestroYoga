from fastapi.templating import Jinja2Templates

try:
    from ..app_version import APP_VERSION_STRING
except ImportError:
    from backend.app.app_version import APP_VERSION_STRING  # type: ignore[no-redef]

from ..web_shared import PUBLIC_INDEX_DEFAULT_PATH
from .constants import BACKEND_ROOT

templates = Jinja2Templates(directory=str(BACKEND_ROOT / "templates"))
templates.env.globals["PUBLIC_INDEX_DEFAULT_PATH"] = PUBLIC_INDEX_DEFAULT_PATH
templates.env.globals["app_version"] = APP_VERSION_STRING
