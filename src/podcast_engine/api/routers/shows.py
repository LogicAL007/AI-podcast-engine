"""FR1: create and configure shows."""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/shows", tags=["shows"])


@router.get("")
def list_shows() -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "shows listing is not implemented yet")
