"""Routes for the in-app assistant: paths, status codes and OpenAPI metadata only."""

from typing import Annotated

from fastapi import APIRouter, Depends

from podcast_engine.api.controllers.assistant_controller import AssistantController
from podcast_engine.api.dependencies import CurrentUserDep, get_assistant_controller
from podcast_engine.api.models.assistant_model import Answer, Question
from podcast_engine.api.openapi import errors

router = APIRouter(prefix="/assistant", tags=["assistant"])

Controller = Annotated[AssistantController, Depends(get_assistant_controller)]


@router.post(
    "/ask",
    response_model=Answer,
    summary="Ask the companion bot",
    response_description="The answer, suggested next steps, and questions left this hour",
    responses=errors(
        e404="The episode or show is not yours, or does not exist",
        e422="The question is empty or too long",
        e429="Too many questions this hour",
    ),
)
def ask(question: Question, me: CurrentUserDep, controller: Controller) -> Answer:
    """Ask about the app or the episode on screen. With the LLM on, Gemini answers from your
    episode's own data (its status, error, segments and the claims the fact-check cut); otherwise,
    or if the model is unavailable, the built-in help does. Suggested actions are only offered as
    buttons; nothing runs by itself. Limited per person per hour
    (`ASSISTANT_QUESTIONS_PER_HOUR`)."""
    return controller.ask(me, question)
