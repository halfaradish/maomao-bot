from pathlib import Path

from nonebot import (
    get_app,
    logger,
    get_driver
)
from fastapi import (
    APIRouter,
    FastAPI,
    Request
)
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..config.response import success
from .bot import router as bot_router
from .auth import router as auth_router
from .permissions import router as perm_router

# ---------------------------------------------------------------------------
# SPA static files — exception handler approach (compatible with WebSocket)
# ---------------------------------------------------------------------------

_WEBUI_DIR = Path(__file__).resolve().parent.parent / "webui"
_WEBUI_INDEX = _WEBUI_DIR / "index.html"


async def _spa_404_handler(request: Request, exc: StarletteHTTPException):
    """Serve SPA index.html for 404s on non-API GET paths.

    Uses Starlette's exception handler instead of app.mount("/", StaticFiles)
    because ``mount`` catches *all* traffic (including NoneBot's WebSocket
    connections with NapCat) and StaticFiles crashes on websocket scope.
    """
    if (
        exc.status_code == 404
        and request.method == "GET"
        and not request.url.path.startswith("/api/")
        and _WEBUI_INDEX.exists()
    ):
        return FileResponse(str(_WEBUI_INDEX), media_type="text/html")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


# ---------------------------------------------------------------------------
# Router assembly
# ---------------------------------------------------------------------------

api_router = APIRouter()
api_router.include_router(bot_router, tags=["bot信息"])
api_router.include_router(auth_router, prefix="/v1/auth")
api_router.include_router(perm_router)

app: FastAPI = get_app()
app.include_router(api_router, prefix="/api")
app.add_exception_handler(StarletteHTTPException, _spa_404_handler)

@app.get('/hello')
async def hello(request: Request):
    return success(
        request=request
    )

@get_driver().on_startup
async def consolo_setup_msg(): 
    logger.success(f"API routes have been registered. on http://127.0.0.1:{get_driver().config.port}")