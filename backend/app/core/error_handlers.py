"""Common exception handlers with standardized error codes per API spec V1.1."""

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException


# Error codes per interface doc V1.1 section 9
ERROR_CODES = {
    400: 1001,  # Invalid request parameters
    401: 1002,  # Unauthorized or token expired
    403: 1003,  # Access denied
    404: 1004,  # Resource not found
    429: 1005,  # Rate limit exceeded
    500: 2001,  # Internal server error
    502: 2002,  # AI engine timeout or unavailable
}


async def http_exception_handler(request: Request, exc: HTTPException):
    code = ERROR_CODES.get(exc.status_code, exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": code, "message": exc.detail},
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    messages = []
    for err in exc.errors():
        loc = " → ".join(str(x) for x in err["loc"])
        messages.append(f"{loc}: {err['msg']}")
    return JSONResponse(
        status_code=400,
        content={"code": 1001, "message": "; ".join(messages)},
    )


def register_error_handlers(app):
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
