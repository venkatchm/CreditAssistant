from __future__ import annotations

from app.repositories.base import CreditRepository
from app.repositories.json_credit_repository import JsonCreditRepository
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.classifier_service import ClassifierService
from app.services.credit_service import CreditService
from app.services.inquiry_service import InquiryService
from app.services.metrics_service import MetricsService
from app.services.payment_history_service import PaymentHistoryService
from app.services.recommendation_service import RecommendationService
from app.services.user_service import UserService


def get_credit_repository() -> CreditRepository:
    return JsonCreditRepository()


def get_user_service() -> UserService:
    return UserService(get_credit_repository())


def get_credit_service() -> CreditService:
    return CreditService(get_credit_repository())


def get_metrics_service() -> MetricsService:
    return MetricsService(get_credit_repository())


def get_recommendation_service() -> RecommendationService:
    return RecommendationService(get_credit_repository())


def get_inquiry_service() -> InquiryService:
    return InquiryService(get_credit_repository())


def get_payment_history_service() -> PaymentHistoryService:
    return PaymentHistoryService(get_credit_repository())


def get_classifier_service() -> ClassifierService:
    return ClassifierService()


def get_chat_orchestrator() -> ChatOrchestrator:
    repository = get_credit_repository()
    return ChatOrchestrator(
        classifier_service=ClassifierService(),
        credit_service=CreditService(repository),
        metrics_service=MetricsService(repository),
        recommendation_service=RecommendationService(repository),
        inquiry_service=InquiryService(repository),
        payment_history_service=PaymentHistoryService(repository),
    )
