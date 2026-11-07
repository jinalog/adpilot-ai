from fastapi import FastAPI

from app.api.errors import application_error_handler
from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import ApplicationError


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Safe AI backend for advertising campaign operations.",
    )
    application.add_exception_handler(ApplicationError, application_error_handler)
    application.include_router(api_router, prefix=settings.api_v1_prefix)
    return application


app = create_app()
