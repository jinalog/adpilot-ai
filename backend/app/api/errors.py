from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import ApplicationError


async def application_error_handler(_: Request, exc: ApplicationError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": {"code": exc.code, "message": exc.message}},
    )
