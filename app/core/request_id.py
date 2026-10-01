import uuid
from collections.abc import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

CORRELATION_HEADER = "X-Request-Id"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware ensuring every HTTP request has a correlation ID.
    If 'X-Request-Id' is passed by client, preserves it.
    Otherwise generates a new UUID4 string.
    Attaches the ID to request.state.request_id and sets the response header.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        incoming_id = request.headers.get(CORRELATION_HEADER)
        request_id = incoming_id if incoming_id else str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers[CORRELATION_HEADER] = request_id
        return response


def get_request_id(request: Request) -> str:
    """
    FastAPI dependency resolving the current request correlation ID.
    """
    return getattr(request.state, "request_id", None) or str(uuid.uuid4())
