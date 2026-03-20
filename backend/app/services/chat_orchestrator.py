from __future__ import annotations

import logging

from app.schemas.chat import ChatResponse
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.query_analyzer import QueryAnalyzer


logger = logging.getLogger(__name__)


class ChatOrchestrator:
    def __init__(
        self,
        query_analyzer: QueryAnalyzer,
        agent_orchestrator: AgentOrchestrator,
    ) -> None:
        self.query_analyzer = query_analyzer
        self.agent_orchestrator = agent_orchestrator

    def respond(self, user_id: str, message: str) -> ChatResponse:
        analysis = self.query_analyzer.analyze(message)
        execution = self.agent_orchestrator.execute(user_id=user_id, message=message, analysis=analysis)
        logger.info(
            "chat_request_routed trace_id=%s user_id=%s query_type=%s execution_mode=%s tool_calls=%s retrieval_used=%s",
            execution.trace.trace_id,
            user_id,
            execution.trace.query_type,
            execution.trace.execution_mode,
            execution.trace.tool_calls,
            execution.trace.retrieval_used,
        )
        return execution.response
