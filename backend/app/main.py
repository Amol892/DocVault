from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    activity,
    auth,
    documents,
    folders,
    health,
    invites,
    members,
    public,
    share_links,
    workspaces,
)
from app.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(title="DocVault API")
    register_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)  # /health stays at the root (compose and CI probe it)

    api = APIRouter(prefix="/api/v1")
    api.include_router(auth.router)
    api.include_router(workspaces.router)
    api.include_router(members.router)
    api.include_router(invites.router)
    api.include_router(activity.router)
    api.include_router(folders.router)
    api.include_router(documents.router)
    api.include_router(share_links.router)
    api.include_router(public.router)
    app.include_router(api)
    return app


app = create_app()
