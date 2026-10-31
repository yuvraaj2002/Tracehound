"""The signed-in user's own profile. A 200 also confirms the access token is still valid."""

from fastapi import APIRouter

from tracehound.api.dependencies import CurrentUserDep
from tracehound.schemas import Me

router = APIRouter(prefix="/v1/me", tags=["me"])


@router.get("")
def get_me(user: CurrentUserDep) -> Me:
    return Me(id=user.user_id, email=user.email, name=user.name, avatar_url=user.avatar_url)
