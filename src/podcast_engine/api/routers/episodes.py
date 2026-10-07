"""Episode status, script review (FR7) and regeneration."""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/episodes", tags=["episodes"])


@router.get("")
def list_episodes() -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "episodes listing is not implemented yet")
