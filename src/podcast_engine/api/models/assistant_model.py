from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

AssistantPage = Literal[
    "shows", "show", "new_show", "episode", "voices", "new_voice", "companion", "welcome", "other"
]
ActionId = Literal[
    "open_script",
    "open_factcheck",
    "open_listen",
    "approve",
    "retry",
    "cancel",
    "generate_episode",
    "new_show",
    "add_voice",
    "open_voices",
    "open_companion",
    "start_tour",
]


class Question(BaseModel):
    """A question for the assistant, with where it was asked."""

    question: str = Field(min_length=1, max_length=500, description="What the person asked")
    page: AssistantPage = Field(default="other", description="The page it was asked on")
    episode_id: UUID | None = Field(
        default=None, description="The episode on screen, if any; it must be yours"
    )
    show_id: UUID | None = Field(
        default=None, description="The show on screen, if any; it must be yours"
    )

    @field_validator("question")
    @classmethod
    def _tidy(cls, value: str) -> str:
        """Collapse runs of whitespace in the question and refuse a blank one.

        Args:
            value: The question as sent.

        Returns:
            The question on one line, with single spaces.

        Raises:
            ValueError: The question is only whitespace.
        """
        text = " ".join(value.split())
        if not text:
            raise ValueError("ask a question")
        return text


class Answer(BaseModel):
    """The assistant's reply."""

    answer: str = Field(description="The reply, in plain text")
    actions: list[ActionId] = Field(
        description="Suggested next steps the page can offer as buttons (never run by themselves)"
    )
    source: Literal["gemini", "help"] = Field(
        description="`gemini`: written by the model from your episode's data; `help`: the "
        "built-in help, used when the model is off or unavailable"
    )
    remaining: int = Field(description="Questions left this hour")


class ModelAnswer(BaseModel):
    """What the model is asked to return (checked before it reaches the page)."""

    answer: str = Field(max_length=1500)
    actions: list[ActionId] = Field(default_factory=list, max_length=3)
