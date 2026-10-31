"""Routes for today's Gemini usage: paths, status codes and OpenAPI metadata only."""

from typing import Annotated

from fastapi import APIRouter, Depends

from podcast_engine.api.controllers.usage_controller import UsageController
from podcast_engine.api.dependencies import get_usage_controller
from podcast_engine.api.models.usage_model import UsageRead

router = APIRouter(tags=["usage"])

Controller = Annotated[UsageController, Depends(get_usage_controller)]


@router.get(
    "/usage",
    response_model=UsageRead,
    summary="Today's Gemini usage",
    response_description="Requests used and left today, per Gemini model in use",
)
def usage_today(controller: Controller) -> UsageRead:
    """How much of today's Gemini budget is spent. The free tier caps requests per model per day,
    resetting at midnight Pacific time; `LLM_REQUESTS_PER_DAY` and `TTS_REQUESTS_PER_DAY` set the
    caps here. The budget is shared by every account and the bot, so this is the same for all."""
    return controller.today()
