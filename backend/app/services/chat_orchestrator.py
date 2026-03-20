from __future__ import annotations

from app.schemas.chat import ChatResponse
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.credit_service import CreditService
from app.services.inquiry_service import InquiryService
from app.services.metrics_service import MetricsService
from app.services.payment_history_service import PaymentHistoryService
from app.services.query_analyzer import QueryAnalyzer
from app.services.rag_service import RagService
from app.services.recommendation_service import RecommendationService


class ChatOrchestrator:
    def __init__(
        self,
        query_analyzer: QueryAnalyzer,
        agent_orchestrator: AgentOrchestrator,
        credit_service: CreditService,
        metrics_service: MetricsService,
        recommendation_service: RecommendationService,
        inquiry_service: InquiryService,
        payment_history_service: PaymentHistoryService,
        rag_service: RagService,
    ) -> None:
        self.query_analyzer = query_analyzer
        self.agent_orchestrator = agent_orchestrator
        self.credit_service = credit_service
        self.metrics_service = metrics_service
        self.recommendation_service = recommendation_service
        self.inquiry_service = inquiry_service
        self.payment_history_service = payment_history_service
        self.rag_service = rag_service

    def respond(self, user_id: str, message: str) -> ChatResponse:
        analysis = self.query_analyzer.analyze(message)
        return self.agent_orchestrator.execute(user_id=user_id, message=message, analysis=analysis)
