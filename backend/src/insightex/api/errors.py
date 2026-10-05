"""API error shape: {"error": {"code", "message"}} with a 4xx/5xx status."""

from __future__ import annotations

from fastapi.responses import JSONResponse

from insightex.ingest.errors import IngestError


def error_response(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": str(code), "message": message}}, status_code=status)


def ingest_error_response(exc: IngestError, status: int = 400) -> JSONResponse:
    return error_response(exc.code, exc.message, status)
