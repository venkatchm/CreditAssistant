from __future__ import annotations

from fastapi import HTTPException

from app.repositories.base import CreditRepository
from synthetic.models import Inquiry


class InquiryService:
    def __init__(self, repository: CreditRepository) -> None:
        self.repository = repository

    def get_inquiries(self, user_id: str) -> list[Inquiry]:
        user = self.repository.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail=f"User not found for user_id={user_id}")
        return self.repository.list_inquiries(user_id)
