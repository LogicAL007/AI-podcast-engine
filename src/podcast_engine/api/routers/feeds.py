"""FR10: RSS feeds and show notes for podcast apps."""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/feeds", tags=["feeds"])


@router.get("")
def list_feeds() -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "feeds listing is not implemented yet")
