"""Consistent error envelope for the API.

Every handled error returns::

    {"error": {"code": "<machine_code>", "message": "<human readable>", "details": {...}}}

Expected errors (validation, auth, not-found, throttling) never surface as 500s.
Unexpected exceptions are logged and returned as a generic 500 envelope.
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from common.logging import get_logger

log = get_logger("api")

_CODE_BY_STATUS = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    409: "conflict",
    415: "unsupported_media_type",
    429: "throttled",
}


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if response is None:
        # Unhandled exception -> log with traceback, return generic 500 envelope.
        log.error("api.unhandled_exception", exc_info=exc)
        return Response(
            {
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred.",
                    "details": {},
                }
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    code = getattr(exc, "default_code", None) or _CODE_BY_STATUS.get(
        response.status_code, "error"
    )
    data = response.data
    message = _extract_message(data)

    response.data = {
        "error": {
            "code": code,
            "message": message,
            "details": data if isinstance(data, (dict, list)) else {},
        }
    }
    return response


def _extract_message(data) -> str:
    if isinstance(data, dict):
        detail = data.get("detail")
        if detail:
            return str(detail)
        return "Request could not be processed; see details."
    if isinstance(data, list) and data:
        return str(data[0])
    return str(data)
