from __future__ import annotations

from fastapi import HTTPException

from app.repositories.base import CreditRepository
from synthetic.models import Recommendation


class RecommendationService:
    def __init__(self, repository: CreditRepository) -> None:
        self.repository = repository

    def get_recommendations(self, user_id: str) -> list[Recommendation]:
        user = self.repository.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail=f"User not found for user_id={user_id}")
        return self.repository.list_recommendations(user_id)
