from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from json import JSONDecoder
from urllib import error, request

from pydantic import BaseModel, Field

from app.schemas.chat import AgentAction, EvidenceItem, ExecutionPlan

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


class GeneratedAnswerPayload(BaseModel):
    message: str
    causes: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)


class ModelGatewayRequest(BaseModel):
    plan: ExecutionPlan
    user_message: str
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    user_attributes: dict[str, str] = Field(default_factory=dict)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    tool_context: dict[str, object] = Field(default_factory=dict)
    retrieval_context: list[str] = Field(default_factory=list)
    grounding_rules: list[str] = Field(default_factory=list)


class ModelGateway(ABC):
    @abstractmethod
    def generate(
        self,
        payload: ModelGatewayRequest,
    ) -> GeneratedAnswerPayload:
        raise NotImplementedError

    def stream(self, payload: ModelGatewayRequest):
        raise NotImplementedError

    def decide_action(
        self,
        payload: ModelGatewayRequest,
        available_tools: list[str],
        completed_tools: list[str],
        retrieval_done: bool,
        retrieval_attempts: int = 0,
        last_retrieval_confidence: float = 0.0,
    ) -> AgentAction:
        raise NotImplementedError


class LocalModelGateway(ModelGateway):
    def decide_action(
        self,
        payload: ModelGatewayRequest,
        available_tools: list[str],
        completed_tools: list[str],
        retrieval_done: bool,
        retrieval_attempts: int = 0,
        last_retrieval_confidence: float = 0.0,
    ) -> AgentAction:
        pending_tools = [tool_name for tool_name in available_tools if tool_name not in completed_tools]
        normalized_message = payload.user_message.lower()

        if payload.plan.query_type == "GENERAL_KNOWLEDGE":
            if not retrieval_done:
                return AgentAction(
                    action="retrieve",
                    query=payload.plan.retrieval_query or payload.user_message,
                    reasoning="Need educational retrieval evidence before answering.",
                )
            if not payload.retrieval_context and retrieval_attempts < 2:
                return AgentAction(
                    action="retrieve",
                    query=self._refine_retrieval_query(payload.user_message, payload.evidence),
                    reasoning="Initial retrieval was weak, so trying a refined educational query.",
                )
            if not payload.retrieval_context:
                return AgentAction(
                    action="insufficient_evidence",
                    reasoning="Retrieval did not produce grounded educational evidence after bounded retries.",
                )
            return AgentAction(action="answer", reasoning="Sufficient educational evidence gathered for grounded answer.")

        if pending_tools:
            for tool_name in self._rank_tools(pending_tools, normalized_message, payload):
                return AgentAction(
                    action="tool_call",
                    tool_name=tool_name,
                    reasoning=f"Need grounded tool evidence from {tool_name} before answering.",
                )

        if payload.plan.retrieval_needed and (not retrieval_done or (last_retrieval_confidence < 0.35 and retrieval_attempts < 2)):
            return AgentAction(
                action="retrieve",
                query=(
                    self._refine_retrieval_query(payload.user_message, payload.evidence)
                    if retrieval_attempts > 0
                    else payload.plan.retrieval_query or payload.user_message
                ),
                reasoning=(
                    "Need educational retrieval evidence before answering."
                    if retrieval_attempts == 0
                    else "Refining retrieval query because the earlier search was weak."
                ),
            )
        if payload.plan.query_type == "COMPLEX_EXPLANATION" and not payload.evidence:
            return AgentAction(
                action="insufficient_evidence",
                reasoning="No grounded evidence was collected for the explanation request.",
            )
        if payload.plan.query_type == "COMPLEX_EXPLANATION" and not any(item.source_kind == "retrieval" for item in payload.evidence):
            return AgentAction(
                action="insufficient_evidence",
                reasoning="Tool evidence exists, but retrieval grounding is still missing after bounded retries.",
            )
        return AgentAction(action="answer", reasoning="Sufficient evidence gathered for grounded answer.")

    def generate(
        self,
        payload: ModelGatewayRequest,
    ) -> GeneratedAnswerPayload:
        plan = payload.plan
        user_message = payload.user_message
        evidence = payload.evidence
        tool_context = payload.tool_context
        retrieval_context = payload.retrieval_context
        if plan.query_type == "GENERAL_KNOWLEDGE":
            message = retrieval_context[0] if retrieval_context else "The knowledge layer could not find a strong enough educational match yet."
            return GeneratedAnswerPayload(message=message, evidence=retrieval_context[:3])

        if plan.query_type == "COMPLEX_EXPLANATION":
            profile = tool_context.get("get_credit_profile")
            metrics = tool_context.get("get_credit_metrics")
            recommendations = tool_context.get("get_recommendations", [])
            causes: list[str] = []
            if profile is not None:
                causes.extend(profile["credit_report"]["score_factors"][:3])
            if metrics is not None:
                causes.extend(metrics["key_drivers"][:3])
            if any("payment" in item.detail.lower() or "delinquency" in item.detail.lower() for item in evidence):
                causes.insert(0, "Recent late payment activity is contributing to the score decline.")
            deduped_causes = _dedupe(causes)[:4]

            evidence_lines: list[str] = []
            if profile is not None:
                change = profile["credit_report"]["score_change_30d"]
                direction = f"up {change} points" if change > 0 else f"down {abs(change)} points" if change < 0 else "unchanged"
                evidence_lines.append(f"Score change over 30 days: {direction}")
            if metrics is not None:
                evidence_lines.append(f"Revolving utilization: {metrics['revolving_utilization']:.1%}")
                evidence_lines.append(f"Hard inquiries in last 12 months: {metrics['total_hard_inquiries_12m']}")
                if metrics["months_since_last_delinquency"] is not None:
                    evidence_lines.append(f"Last delinquency: {metrics['months_since_last_delinquency']} months ago")
            evidence_lines.extend(f"{item.title} ({item.citation})" for item in evidence if item.source_kind == "retrieval")
            evidence_lines = evidence_lines[:6]
            suggested_actions = [
                item.get("title", str(item))
                for item in recommendations[:3]
            ]
            if profile is not None and metrics is not None:
                score = profile["credit_report"]["score"]
                score_band = profile["credit_report"]["score_band"].replace("_", " ").title()
                score_change = metrics["score_change_30d"]
                direction = f"up {score_change} points" if score_change > 0 else f"down {abs(score_change)} points" if score_change < 0 else "unchanged"
                message = (
                    f"Your latest credit score is {score} ({score_band}), {direction} over the last 30 days. "
                    f"{profile['credit_report']['summary']}"
                )
                if any("late" in item.detail.lower() or "delinquency" in item.detail.lower() for item in evidence):
                    message += " The strongest tool-grounded signal is recent payment trouble."
                return GeneratedAnswerPayload(
                    message=message,
                    causes=deduped_causes,
                    evidence=evidence_lines,
                    suggested_actions=suggested_actions,
                )

        return GeneratedAnswerPayload(message=user_message, evidence=[item.detail for item in evidence[:3]])

    def stream(self, payload: ModelGatewayRequest):
        result = self.generate(payload)
        yield result.message

    def _rank_tools(self, pending_tools: list[str], normalized_message: str, payload: ModelGatewayRequest) -> list[str]:
        scored: list[tuple[int, str]] = []
        for tool_name in pending_tools:
            score = 0
            if payload.plan.query_type == "SIMPLE_FACT":
                if tool_name == "get_credit_profile" and any(term in normalized_message for term in ["credit score", "score", "report", "profile"]):
                    score += 8
                if tool_name == "get_credit_metrics" and "utilization" in normalized_message:
                    score += 8
            if payload.plan.query_type == "SIMPLE_RECOMMENDATION":
                if tool_name == "get_recommendations":
                    score += 8
                if tool_name == "get_credit_metrics":
                    score += 4
            if tool_name == "get_payment_history" and any(term in normalized_message for term in ["late", "payment", "delinquency", "missed", "drop"]):
                score += 4
            if tool_name == "get_inquiries" and any(term in normalized_message for term in ["inquiry", "application", "hard pull", "hard inquiry"]):
                score += 4
            if tool_name == "get_credit_metrics" and any(term in normalized_message for term in ["utilization", "drop", "change", "score"]):
                score += 3
            if tool_name == "get_credit_profile" and any(term in normalized_message for term in ["score", "profile", "report", "drop"]):
                score += 3
            if tool_name == "get_recommendations" and any(term in normalized_message for term in ["improve", "recommend", "what should i do", "next step"]):
                score += 3
            if tool_name in payload.tool_context:
                score -= 10
            scored.append((score, tool_name))
        return [tool_name for _, tool_name in sorted(scored, key=lambda item: (-item[0], item[1]))]

    def _refine_retrieval_query(self, user_message: str, evidence: list[EvidenceItem]) -> str:
        evidence_terms = " ".join(item.title for item in evidence[:3])
        if evidence_terms:
            return f"{user_message} {evidence_terms} credit explanation education"
        return f"{user_message} credit score factors payment history utilization inquiry explanation"


@dataclass(frozen=True)
class RemoteModelGatewayConfig:
    base_url: str
    api_key: str | None = None
    model_name: str | None = None
    timeout_seconds: float = 30.0


class RemoteModelGateway(ModelGateway):
    def __init__(self, config: RemoteModelGatewayConfig) -> None:
        self.config = config

    def generate(self, payload: ModelGatewayRequest) -> GeneratedAnswerPayload:
        return self._request(payload)

    def stream(self, payload: ModelGatewayRequest):
        body = {
            "model": self.config.model_name,
            "input": payload.model_dump(mode="json"),
            "stream": True,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/x-ndjson, application/json",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        http_request = request.Request(
            url=self.config.base_url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        buffered_text = ""
        try:
            with request.urlopen(http_request, timeout=self.config.timeout_seconds) as response:
                yielded = False
                for chunk in _iter_remote_stream(response):
                    if chunk:
                        yielded = True
                        buffered_text += chunk
                        yield chunk
                if not yielded:
                    if buffered_text.strip():
                        yield buffered_text
        except error.URLError as exc:  # pragma: no cover
            raise RuntimeError(f"Remote model gateway request failed: {exc}") from exc

    def decide_action(
        self,
        payload: ModelGatewayRequest,
        available_tools: list[str],
        completed_tools: list[str],
        retrieval_done: bool,
        retrieval_attempts: int = 0,
        last_retrieval_confidence: float = 0.0,
    ) -> AgentAction:
        # Reserve remote calls for the final answer path. Deterministic planning removes one full model round-trip.
        return LocalModelGateway().decide_action(payload, available_tools, completed_tools, retrieval_done, retrieval_attempts, last_retrieval_confidence)

    def _request(self, payload: ModelGatewayRequest) -> GeneratedAnswerPayload:
        body = {
            "model": self.config.model_name,
            "input": payload.model_dump(mode="json"),
        }
        headers = {
            "Content-Type": "application/json",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        http_request = request.Request(
            url=self.config.base_url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.config.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except error.URLError as exc:  # pragma: no cover
            raise RuntimeError(f"Remote model gateway request failed: {exc}") from exc

        if "output" in response_payload:
            response_payload = response_payload["output"]
        return GeneratedAnswerPayload(**normalize_generated_payload(response_payload, payload))


@dataclass(frozen=True)
class OpenAIModelGatewayConfig:
    api_key: str
    model: str
    base_url: str | None = None


class OpenAIModelGateway(ModelGateway):
    def __init__(self, config: OpenAIModelGatewayConfig) -> None:
        if OpenAI is None:
            raise RuntimeError("The OpenAI Python SDK is required for the openai model backend.")
        client_kwargs = {"api_key": config.api_key}
        if config.base_url:
            client_kwargs["base_url"] = config.base_url
        self.client = OpenAI(**client_kwargs)
        self.config = config

    def generate(self, payload: ModelGatewayRequest) -> GeneratedAnswerPayload:
        response = self._responses_create(payload, stream=False, response_format="structured")
        output_text = getattr(response, "output_text", None)
        if not output_text:
            raise RuntimeError("OpenAI model gateway returned no text output.")
        parsed = self._parse_generated_output(output_text=output_text, payload=payload)
        return GeneratedAnswerPayload(**normalize_generated_payload(parsed, payload))

    def stream(self, payload: ModelGatewayRequest):
        stream = self._responses_create(payload, stream=True, response_format="plain_text")
        for event in stream:
            event_type = getattr(event, "type", "")
            if event_type == "response.output_text.delta":
                delta = getattr(event, "delta", "")
                if delta:
                    yield delta

    def decide_action(
        self,
        payload: ModelGatewayRequest,
        available_tools: list[str],
        completed_tools: list[str],
        retrieval_done: bool,
        retrieval_attempts: int = 0,
        last_retrieval_confidence: float = 0.0,
    ) -> AgentAction:
        # Reserve OpenAI usage for final answer generation instead of spending an extra model call on action planning.
        return LocalModelGateway().decide_action(payload, available_tools, completed_tools, retrieval_done, retrieval_attempts, last_retrieval_confidence)

    def _responses_create(self, payload: ModelGatewayRequest, stream: bool, response_format: str):
        return self.client.responses.create(
            model=self.config.model,
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": self._build_answer_system_prompt(response_format),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(payload.model_dump(mode="json"), ensure_ascii=True),
                        }
                    ],
                },
            ],
            stream=stream,
        )

    def _build_answer_system_prompt(self, response_format: str) -> str:
        shared_rules = (
            "You are a credit assistant answer generator. "
            "Use only the supplied evidence. "
            "Personal credit facts must come from tool evidence. "
            "Educational explanations may come from retrieved evidence. "
        )
        if response_format == "plain_text":
            return (
                f"{shared_rules}"
                "Return only natural-language answer text for the user. "
                "Do not return JSON. "
                "Do not use markdown code fences. "
                "Write a complete answer in plain English, not a single sentence. "
                "Start with a direct answer to the user's question. "
                "Then briefly explain the main drivers or reasons when relevant. "
                "Include 2 to 4 short actionable recommendations when relevant. "
                "Prefer short paragraphs or simple bullet points. "
                "Keep the response clear, grounded, and directly actionable."
            )
        return (
            f"{shared_rules}"
            "Return strict JSON with keys: message, causes, evidence, suggested_actions."
        )

    def _parse_generated_output(self, output_text: str, payload: ModelGatewayRequest) -> dict[str, object]:
        try:
            return json.loads(output_text)
        except json.JSONDecodeError:
            extracted = extract_json_object(output_text)
            if extracted is not None:
                return extracted
            return fallback_generated_payload(output_text=output_text, payload=payload)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        normalized = item.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(item)
    return deduped


def normalize_generated_payload(payload: dict[str, object], request_payload: ModelGatewayRequest) -> dict[str, object]:
    normalized = dict(payload)
    for key in ("causes", "evidence", "suggested_actions"):
        value = normalized.get(key, [])
        if not isinstance(value, list):
            normalized[key] = []
            continue
        normalized[key] = [coerce_text_item(item) for item in value]
    if not isinstance(normalized.get("message"), str):
        normalized["message"] = coerce_text_item(normalized.get("message", ""))
    normalized["evidence"] = [prettify_evidence_item(item) for item in normalized.get("evidence", []) if item]
    normalized["causes"] = [item for item in normalized.get("causes", []) if item]
    normalized["suggested_actions"] = [item for item in normalized.get("suggested_actions", []) if item]
    if not normalized["message"]:
        normalized["message"] = fallback_generated_payload("", request_payload)["message"]
    return normalized


def coerce_text_item(item: object) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for preferred_key in ("title", "action", "detail", "text", "message"):
            value = item.get(preferred_key)
            if isinstance(value, str) and value.strip():
                return value
        return json.dumps(item, ensure_ascii=True)
    if item is None:
        return ""
    return str(item)


def prettify_evidence_item(item: str) -> str:
    stripped = item.strip()
    if not stripped.startswith("{"):
        return stripped
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    quote = parsed.get("quote")
    citation = parsed.get("citation")
    source = parsed.get("source")
    if isinstance(quote, str) and isinstance(citation, str):
        if source:
            return f"{quote} ({citation}; {source})"
        return f"{quote} ({citation})"
    return stripped


def extract_json_object(output_text: str) -> dict[str, object] | None:
    start = output_text.find("{")
    end = output_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = output_text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def _iter_remote_stream(response):
    content_type = ""
    if hasattr(response, "headers") and response.headers is not None:
        content_type = response.headers.get("Content-Type", "")
    decoder_buffer = ""
    pending_sse_lines: list[str] = []
    while True:
        chunk = response.read(1024)
        if not chunk:
            break
        text = chunk.decode("utf-8", errors="ignore")
        if content_type.startswith("text/plain"):
            yield text
            continue
        if "text/event-stream" in content_type:
            pending_sse_lines.extend(text.splitlines())
            while "" in pending_sse_lines:
                blank_index = pending_sse_lines.index("")
                event_lines = pending_sse_lines[:blank_index]
                pending_sse_lines = pending_sse_lines[blank_index + 1 :]
                data_lines = [line[5:].strip() for line in event_lines if line.startswith("data:")]
                if not data_lines:
                    continue
                payload_text = "\n".join(data_lines)
                try:
                    payload = json.loads(payload_text)
                except json.JSONDecodeError:
                    yield payload_text
                    continue
                delta = _extract_stream_text(payload)
                if delta:
                    yield delta
            continue

        if "application/x-ndjson" in content_type:
            decoder_buffer += text
            while "\n" in decoder_buffer:
                line, decoder_buffer = decoder_buffer.split("\n", 1)
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError:
                    yield stripped
                    continue
                delta = _extract_stream_text(payload)
                if delta:
                    yield delta
            continue

        decoder_buffer += text
        parsed_objects, decoder_buffer = _iter_json_objects(decoder_buffer)
        for parsed in parsed_objects:
            delta = _extract_stream_text(parsed)
            if delta:
                yield delta

    if decoder_buffer.strip():
        try:
            payload = json.loads(decoder_buffer)
        except json.JSONDecodeError:
            return
        delta = _extract_stream_text(payload)
        if delta:
            yield delta


def _extract_stream_text(payload: object) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        for key in ("delta", "text", "output_text", "message", "content"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                combined = "".join(_extract_stream_text(item) for item in value)
                if combined:
                    return combined
        return ""
    if isinstance(payload, list):
        return "".join(_extract_stream_text(item) for item in payload)
    return ""


def _iter_json_objects(buffer: str) -> tuple[list[object], str]:
    decoder = JSONDecoder()
    parsed: list[object] = []
    index = 0
    while index < len(buffer):
        while index < len(buffer) and buffer[index].isspace():
            index += 1
        if index >= len(buffer):
            return parsed, ""
        try:
            value, next_index = decoder.raw_decode(buffer, index)
        except ValueError:
            return parsed, buffer[index:]
        parsed.append(value)
        index = next_index
    return parsed, ""


def fallback_generated_payload(output_text: str, payload: ModelGatewayRequest) -> dict[str, object]:
    fallback_evidence = [item.detail for item in payload.evidence[:6]]
    fallback_causes = [item.detail for item in payload.evidence if item.source_kind == "tool"][:4]
    fallback_actions = [
        item.get("title", "")
        for item in payload.tool_context.get("get_recommendations", [])
        if isinstance(item, dict)
    ][:3]
    message = output_text.strip() or "I could not fully format the model output, so this fallback answer uses grounded evidence only."
    return {
        "message": message,
        "causes": fallback_causes,
        "evidence": fallback_evidence,
        "suggested_actions": fallback_actions,
    }
