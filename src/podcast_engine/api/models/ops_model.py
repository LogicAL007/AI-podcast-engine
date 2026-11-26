from typing import Literal

from pydantic import BaseModel, Field


class Health(BaseModel):
    """Liveness: the process is up and serving requests."""

    status: str = Field(description="Always `ok` when the process is serving", examples=["ok"])
    version: str = Field(description="API version", examples=["0.1.0"])


class Readiness(BaseModel):
    """Readiness: whether every dependency the API needs is reachable."""

    status: Literal["ready", "not ready"] = Field(description="`ready` only if every check passed")
    checks: dict[str, str] = Field(
        description="Each dependency and `ok`, or what went wrong",
        examples=[{"database": "ok", "queue": "ok", "storage": "ok"}],
    )
