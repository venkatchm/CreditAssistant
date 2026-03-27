from __future__ import annotations

from functools import lru_cache

from app.core.settings import get_settings
from app.gateway.model_gateway import (
    AnthropicModelGateway,
    AnthropicModelGatewayConfig,
    LocalModelGateway,
    ModelGateway,
    OpenAIModelGateway,
    OpenAIModelGatewayConfig,
    RemoteModelGateway,
    RemoteModelGatewayConfig,
)
from app.repositories.base import CreditRepository
from app.repositories.json_credit_repository import JsonCreditRepository
from app.repositories.postgres_credit_repository import PostgresCreditRepository
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


@lru_cache(maxsize=1)
def get_credit_repository() -> CreditRepository:
    settings = get_settings()
    if settings.credit_data_backend == "postgres":
        if not settings.retrieval_postgres_dsn:
            raise RuntimeError("RETRIEVAL_POSTGRES_DSN is required when CREDIT_DATA_BACKEND=postgres.")
        from pathlib import Path
        base_dir = Path(__file__).resolve().parents[2]
        migration_sql = (base_dir / "migrations" / "0004_credit_data_schema.sql").read_text(encoding="utf-8")
        return PostgresCreditRepository(dsn=settings.retrieval_postgres_dsn, migration_sql=migration_sql)
    return JsonCreditRepository()


@lru_cache(maxsize=1)
def get_user_service() -> UserService:
    return UserService(get_credit_repository())


@lru_cache(maxsize=1)
def get_credit_service() -> CreditService:
    return CreditService(get_credit_repository())


@lru_cache(maxsize=1)
def get_metrics_service() -> MetricsService:
    return MetricsService(get_credit_repository())


@lru_cache(maxsize=1)
def get_recommendation_service() -> RecommendationService:
    return RecommendationService(get_credit_repository())


@lru_cache(maxsize=1)
def get_inquiry_service() -> InquiryService:
    return InquiryService(get_credit_repository())


@lru_cache(maxsize=1)
def get_payment_history_service() -> PaymentHistoryService:
    return PaymentHistoryService(get_credit_repository())


@lru_cache(maxsize=1)
def get_classifier_service() -> ClassifierService:
    return ClassifierService()


@lru_cache(maxsize=1)
def get_query_analyzer() -> QueryAnalyzer:
    return QueryAnalyzer()


@lru_cache(maxsize=1)
def get_rag_service() -> RagService:
    return RagService()


@lru_cache(maxsize=1)
def get_execution_planner() -> ExecutionPlanner:
    return ExecutionPlanner()


@lru_cache(maxsize=1)
def get_evidence_builder() -> EvidenceBuilder:
    return EvidenceBuilder()


@lru_cache(maxsize=1)
def get_grounded_response_composer() -> GroundedResponseComposer:
    return GroundedResponseComposer(
        model_gateway=get_model_gateway(),
        evidence_builder=get_evidence_builder(),
    )


@lru_cache(maxsize=1)
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
    if settings.model_backend == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required when MODEL_BACKEND=anthropic.")
        return AnthropicModelGateway(
            AnthropicModelGatewayConfig(
                api_key=settings.anthropic_api_key,
                model=settings.anthropic_model or "claude-haiku-4-5-20251001",
            )
        )
    return LocalModelGateway()


@lru_cache(maxsize=1)
def get_tool_registry() -> ToolRegistry:
    return ToolRegistry(
        credit_service=get_credit_service(),
        metrics_service=get_metrics_service(),
        recommendation_service=get_recommendation_service(),
        inquiry_service=get_inquiry_service(),
        payment_history_service=get_payment_history_service(),
    )


@lru_cache(maxsize=1)
def get_agent_orchestrator() -> AgentOrchestrator:
    return AgentOrchestrator(
        planner=get_execution_planner(),
        tool_registry=get_tool_registry(),
        rag_service=get_rag_service(),
        evidence_builder=get_evidence_builder(),
        response_composer=get_grounded_response_composer(),
    )


@lru_cache(maxsize=1)
def get_chat_orchestrator() -> ChatOrchestrator:
    return ChatOrchestrator(
        query_analyzer=get_query_analyzer(),
        agent_orchestrator=get_agent_orchestrator(),
    )
