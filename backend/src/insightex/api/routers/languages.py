"""GET /api/languages: the selectable lecture languages, grouped by tier (ADR-0040)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from insightex.api.deps import settings_of
from insightex.asr.languages import languages_for

router = APIRouter(prefix="/api/languages")


@router.get("")
def list_languages(request: Request):
    """`{"groups": [{"tier", "label", "languages": [{"id", "label", "tier"}]}]}`: tested first, each sorted by label."""
    return {"groups": languages_for(settings_of(request)).grouped()}
