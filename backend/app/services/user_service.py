from __future__ import annotations

from fastapi import HTTPException

from app.repositories.base import CreditRepository
from synthetic.models import User


class UserService:
    def __init__(self, repository: CreditRepository) -> None:
        self.repository = repository

    def list_users(self) -> list[User]:
        return self.repository.list_users()

    def get_user(self, user_id: str) -> User:
        user = self.repository.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail=f"User not found for user_id={user_id}")
        return user
