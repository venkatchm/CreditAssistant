from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.dependencies import get_user_service
from app.schemas.users import UserDetail, UserSummary, UsersListResponse
from app.services.user_service import UserService


router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UsersListResponse)
def list_users(user_service: UserService = Depends(get_user_service)) -> UsersListResponse:
    users = [UserSummary.from_user(user) for user in user_service.list_users()]
    return UsersListResponse(users=users)


@router.get("/{user_id}", response_model=UserDetail)
def get_user(user_id: str, user_service: UserService = Depends(get_user_service)) -> UserDetail:
    return UserDetail.from_user(user_service.get_user(user_id))
