from __future__ import annotations

from app.core.settings import get_settings
from app.gateway.model_gateway import (
    LocalModelGateway,
    ModelGateway,
    OpenAIModelGateway,
    OpenAIModelGatewayConfig,
    RemoteModelGateway,
    RemoteModelGatewayConfig,
)
from app.repositories.base import CreditRepository
from app.repositories.json_credit_repository import JsonCreditRepository
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.classifier_service import ClassifierService
from app.services.credit_service import CreditService
from app.services.evidence_builder import EvidenceBuilder
from app.services.execution_planner import ExecutionPlanner
from app.services.grounded_response_composer import GroundedResponseComposer
from app.services.inquiry_service import InquiryService
from app.services.metrics_service import MetricsService
from app.services.payment_history_service import PaymentHistoryService
from app.services.query_analyzer import QueryAnalyzer
from app.services.rag_service import RagService
from app.services.recommendation_service import RecommendationService
from app.services.tool_registry import ToolRegistry
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


def get_query_analyzer() -> QueryAnalyzer:
    return QueryAnalyzer()


def get_rag_service() -> RagService:
    return RagService()


def get_execution_planner() -> ExecutionPlanner:
    return ExecutionPlanner()


def get_evidence_builder() -> EvidenceBuilder:
    return EvidenceBuilder()


def get_grounded_response_composer() -> GroundedResponseComposer:
    return GroundedResponseComposer(
        model_gateway=get_model_gateway(),
        evidence_builder=get_evidence_builder(),
    )


def get_model_gateway() -> ModelGateway:
    settings = get_settings()
    if settings.model_backend == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when MODEL_BACKEND=openai.")
        return OpenAIModelGateway(
            OpenAIModelGatewayConfig(
                api_key=settings.openai_api_key,
                model=settings.openai_model or "gpt-5",
                base_url=settings.openai_base_url,
            )
        )
    if settings.model_backend == "remote":
        if not settings.model_base_url:
            raise RuntimeError("MODEL_BASE_URL is required when MODEL_BACKEND=remote.")
        return RemoteModelGateway(
            RemoteModelGatewayConfig(
                base_url=settings.model_base_url,
                api_key=settings.model_api_key,
                model_name=settings.model_name,
            )
        )
    return LocalModelGateway()


def get_tool_registry() -> ToolRegistry:
    repository = get_credit_repository()
    return ToolRegistry(
        credit_service=CreditService(repository),
        metrics_service=MetricsService(repository),
        recommendation_service=RecommendationService(repository),
        inquiry_service=InquiryService(repository),
        payment_history_service=PaymentHistoryService(repository),
    )


def get_agent_orchestrator() -> AgentOrchestrator:
    return AgentOrchestrator(
        planner=get_execution_planner(),
        tool_registry=get_tool_registry(),
        rag_service=get_rag_service(),
        evidence_builder=get_evidence_builder(),
        response_composer=get_grounded_response_composer(),
    )


def get_chat_orchestrator() -> ChatOrchestrator:
    return ChatOrchestrator(
        query_analyzer=QueryAnalyzer(),
        agent_orchestrator=get_agent_orchestrator(),
    )
