"""Define safe domain errors and HTTP error contracts.

Services raise domain errors; shared handlers translate them at the API boundary.
"""

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


class FieldError(BaseModel):
    """Safe field-level feedback, excluding submitted values."""

    field: str
    message: str


class ErrorBody(BaseModel):
    """Stable machine-readable code with safe user-facing text."""

    code: str
    message: str
    details: list[FieldError] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Common API failure envelope."""

    error: ErrorBody


class DomainError(Exception):
    """A service failure whose explicitly supplied message is safe to display."""

    def __init__(
        self, code: str, message: str, status: int = 400, details: list[FieldError] | None = None
    ) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
        self.details = details or []


def error_response(
    status: int, code: str, message: str, details: list[FieldError] | None = None
) -> JSONResponse:
    """Build the standard failure response."""
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details or []))
    return JSONResponse(body.model_dump(), status_code=status)


ERROR_RESPONSES = {
    status: {"model": ErrorResponse, "description": HTTPStatus(status).phrase}
    for status in (400, 401, 403, 404, 405, 409, 422, 500, 503)
}


def install_error_handlers(app: FastAPI) -> None:
    """Register uniform handlers without reflecting exception details to clients."""

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return error_response(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        malformed = any(error["type"] == "json_invalid" for error in exc.errors())
        return error_response(
            400 if malformed else 422,
            "malformed_request" if malformed else "validation_error",
            "Malformed JSON." if malformed else "One or more fields are invalid.",
            [
                FieldError(field=".".join(map(str, e["loc"])), message="Invalid value.")
                for e in exc.errors()
            ],
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        codes = {401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}
        try:
            message = HTTPStatus(exc.status_code).phrase
        except ValueError:
            message = "Request failed."
        response = error_response(
            exc.status_code, codes.get(exc.status_code, "http_error"), message
        )
        for name, value in (exc.headers or {}).items():
            response.headers[name] = value
        return response

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unexpected request failure", exc_info=exc)
        return error_response(500, "internal_error", "An unexpected error occurred.")
