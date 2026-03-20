from __future__ import annotations

from typing import List

from pydantic import BaseModel

from synthetic.models import PersonaCode, User


class UserSummary(BaseModel):
    user_id: str
    full_name: str
    city: str
    state: str
    occupation: str
    persona: PersonaCode

    @classmethod
    def from_user(cls, user: User) -> "UserSummary":
        return cls(
            user_id=user.user_id,
            full_name=user.full_name,
            city=user.city,
            state=user.state,
            occupation=user.occupation,
            persona=user.persona,
        )


class UserDetail(BaseModel):
    user_id: str
    full_name: str
    age: int
    city: str
    state: str
    occupation: str
    annual_income: int
    persona: PersonaCode

    @classmethod
    def from_user(cls, user: User) -> "UserDetail":
        payload = user.model_dump() if hasattr(user, "model_dump") else user.dict()
        return cls(**payload)


class UsersListResponse(BaseModel):
    users: List[UserSummary]
