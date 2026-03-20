from __future__ import annotations

from app.schemas.credit import RecommendationsResponse
from app.services.recommendation_service import RecommendationService


def get_recommendations(service: RecommendationService, user_id: str) -> RecommendationsResponse:
    return RecommendationsResponse(user_id=user_id, recommendations=service.get_recommendations(user_id))
