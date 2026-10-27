from fastapi import APIRouter, Depends, HTTPException
from app.models import SkillPassport
from app.repository import InMemoryRepository, get_repository

router = APIRouter(prefix="/api/v1/passport", tags=["Public Skill Passport API"])


@router.get("/{token}", response_model=SkillPassport)
async def get_public_passport(token: str, repo: InMemoryRepository = Depends(get_repository)):
    passport = repo.get_passport_by_token(token)
    if not passport:
        raise HTTPException(status_code=404, detail="Skill Passport not found or token has expired")
    return passport
