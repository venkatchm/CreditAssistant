from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from json import JSONDecoder
from urllib import error, request

from pydantic import BaseModel, Field

from app.schemas.chat import AgentAction, EvidenceItem, ExecutionPlan

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

try:
    import anthropic as anthropic_sdk
except ImportError:  # pragma: no cover
    anthropic_sdk = None


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
        self._log_cache_usage(getattr(response, "usage", None))
        output_text = getattr(response, "output_text", None)
        if not output_text:
            raise RuntimeError("OpenAI model gateway returned no text output.")
        parsed = self._parse_generated_output(output_text=output_text, payload=payload)
        return GeneratedAnswerPayload(**normalize_generated_payload(parsed, payload))

    def stream(self, payload: ModelGatewayRequest):
        import time
        started_at = time.perf_counter()

        try:
            stream = self._responses_create(payload, stream=True, response_format="plain_text")
        except Exception as exc:
            logger.error("openai_responses_create_failed error=%s", exc)
            print(f"[ERROR] openai _responses_create failed: {exc}", flush=True)
            yield from self._empty_response_fallback(payload)
            return

        if stream is None:
            logger.error("openai_responses_create_returned_none")
            print("[ERROR] openai _responses_create returned None", flush=True)
            yield from self._empty_response_fallback(payload)
            return

        first_chunk_at: float | None = None
        chunks_yielded = 0
        completed_response = None
        for event in stream:
            event_type = getattr(event, "type", "")
            if event_type in ("response.completed", "response.incomplete"):
                resp = getattr(event, "response", None)
                if event_type == "response.completed":
                    usage = getattr(resp, "usage", None)
                    self._log_cache_usage(usage)
                    if usage is not None:
                        total_ms = int((time.perf_counter() - started_at) * 1000)
                        ttft_ms = int((first_chunk_at - started_at) * 1000) if first_chunk_at else 0
                        output_tokens = getattr(usage, "output_tokens", 0)
                        tps = round(output_tokens / (total_ms / 1000), 1) if total_ms else 0
                        print(
                            f"[SPEED] ttft={ttft_ms}ms  total={total_ms}ms  "
                            f"output_tokens={output_tokens}  tokens/sec={tps}",
                            flush=True,
                        )
                else:
                    finish = getattr(resp, "incomplete_details", None)
                    reason = getattr(finish, "reason", "max_output_tokens") if finish else "max_output_tokens"
                    print(f"[WARN] openai response.incomplete reason={reason}", flush=True)
                    logger.warning("openai_stream_incomplete reason=%s", reason)
                completed_response = resp
            elif event_type == "response.failed":
                error = getattr(getattr(event, "response", None), "error", None)
                msg = getattr(error, "message", str(error)) if error else "unknown"
                print(f"[ERROR] openai response.failed: {msg}", flush=True)
                logger.error("openai_stream_failed error=%s", msg)
                raise RuntimeError(f"OpenAI response failed: {msg}")
            elif event_type == "response.output_text.delta":
                delta = getattr(event, "delta", "")
                if delta:
                    if first_chunk_at is None:
                        first_chunk_at = time.perf_counter()
                    chunks_yielded += 1
                    yield delta

        # Fallback: if no text deltas were streamed, try to extract text from
        # the completed/incomplete response object (handles content-filter
        # refusals, non-text output blocks, and max_output_tokens edge cases).
        if chunks_yielded == 0:
            if completed_response is not None:
                fallback_text = getattr(completed_response, "output_text", None) or ""
                if not fallback_text:
                    for output_item in (getattr(completed_response, "output", None) or []):
                        for content in (getattr(output_item, "content", None) or []):
                            text = getattr(content, "text", "")
                            if text:
                                fallback_text = text
                                break
                        if fallback_text:
                            break
                if fallback_text:
                    print("[WARN] no stream deltas received; using fallback from response object", flush=True)
                    logger.warning("openai_stream_no_deltas_fallback len=%d", len(fallback_text))
                    yield fallback_text
                    return
            print("[ERROR] openai stream completed with no text output at all", flush=True)
            logger.error("openai_stream_empty_response")
            yield from self._empty_response_fallback(payload)

    def _log_cache_usage(self, usage: object) -> None:
        if usage is None:
            return
        total = getattr(usage, "input_tokens", None)
        details = getattr(usage, "input_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) if details else 0
        output = getattr(usage, "output_tokens", None)
        if total is not None:
            saved_pct = round(cached / total * 100) if total else 0
            msg = f"[CACHE] openai  input={total} cached={cached} ({saved_pct}% from cache) output={output}"
            print(msg, flush=True)
            logger.info(msg)

    def _empty_response_fallback(self, payload: ModelGatewayRequest):
        """Yield a grounded fallback answer when the model returned no text."""
        result = fallback_generated_payload("", payload)
        yield result["message"]

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
        """
        OpenAI prompt caching is automatic — no explicit cache_control needed.
        It caches any prompt prefix longer than 1024 tokens that is identical
        across requests. Cache hits appear in usage.input_tokens_details.cached_tokens.

        To maximise cache hits the input is split into two content blocks:

          Block 1 — evidence context (cacheable prefix):
            Contains tool results, retrieval knowledge, plan and grounding rules.
            This is identical for follow-up questions about the same customer,
            so OpenAI will serve it from cache after the first request.

          Block 2 — user question (dynamic suffix):
            Changes every request — kept separate so it does not invalidate
            the cached prefix above it.

        Before this change the entire payload was one JSON blob that included
        the user message, meaning the prefix was never identical and caching
        never triggered.
        """
        evidence_context = self._build_evidence_context(payload)
        user_content: list[dict] = []
        if evidence_context:
            user_content.append({"type": "input_text", "text": evidence_context})
        user_content.append({"type": "input_text", "text": payload.user_message})

        return self.client.responses.create(
            model=self.config.model,
            max_output_tokens=1024,
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
                    "content": user_content,
                },
            ],
            stream=stream,
        )

    def _build_evidence_context(self, payload: ModelGatewayRequest) -> str:
        """Serialise all grounding context into a stable text block that sits
        before the user question. Keeping this block identical across follow-up
        questions about the same customer is what lets OpenAI's automatic prefix
        cache kick in."""
        parts: list[str] = []
        if payload.tool_context:
            parts.append(f"[Tool results]\n{json.dumps(payload.tool_context, ensure_ascii=True)}")
        if payload.retrieval_context:
            joined = "\n".join(f"- {chunk}" for chunk in payload.retrieval_context)
            parts.append(f"[Knowledge base]\n{joined}")
        if payload.evidence:
            lines = [f"- {item.title}: {item.detail}" for item in payload.evidence]
            parts.append("[Evidence]\n" + "\n".join(lines))
        if payload.grounding_rules:
            rules = "\n".join(f"- {rule}" for rule in payload.grounding_rules)
            parts.append(f"[Grounding rules]\n{rules}")
        if payload.user_attributes:
            attrs = ", ".join(f"{k}={v}" for k, v in payload.user_attributes.items())
            parts.append(f"[User attributes] {attrs}")
        return "\n\n".join(parts)

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
                "Do not return JSON or markdown code fences. "
                "Write like a human advisor sending a chat message — not a report. "
                "Keep the total response under 150 words. "
                "Start with one direct sentence that answers the question. "
                "Then give 2 to 4 short bullet points for key reasons or actions. "
                "No long paragraphs. No filler phrases like 'Great question' or 'In summary'. "
                "Be specific — use the actual numbers from the evidence."
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


@dataclass(frozen=True)
class AnthropicModelGatewayConfig:
    api_key: str
    model: str = "claude-haiku-4-5-20251001"


class AnthropicModelGateway(ModelGateway):
    """
    Anthropic Claude gateway with explicit prompt caching.

    Caching strategy:
      1. System prompt           — always cached (static instructions, never changes)
      2. Evidence / tool context — cached per request (stable within a session,
                                   saves tokens on follow-up questions about the
                                   same customer)
      3. User message            — never cached (changes every request)

    Anthropic caches any block marked with cache_control for 5 minutes.
    Minimum cacheable size: 1024 tokens (Haiku/Sonnet), 2048 (Opus).
    Savings: up to 90% cost reduction and lower latency on cache hits.
    """

    SYSTEM_PROMPT = (
        "You are a credit assistant answer generator. "
        "Use only the supplied evidence. "
        "Personal credit facts must come from tool evidence. "
        "Educational explanations may come from retrieved evidence. "
        "Return only natural-language answer text. "
        "Do not return JSON or markdown code fences. "
        "Write like a human advisor sending a chat message — not a report. "
        "Keep the total response under 150 words. "
        "Start with one direct sentence that answers the question. "
        "Then give 2 to 4 short bullet points for key reasons or actions. "
        "No long paragraphs. No filler phrases like 'Great question' or 'In summary'. "
        "Be specific — use the actual numbers from the evidence."
    )

    def __init__(self, config: AnthropicModelGatewayConfig) -> None:
        if anthropic_sdk is None:
            raise RuntimeError("anthropic SDK is required. Run: pip install anthropic")
        self.client = anthropic_sdk.Anthropic(api_key=config.api_key)
        self.config = config

    # ── Public interface ────────────────────────────────────────────────────

    def generate(self, payload: ModelGatewayRequest) -> GeneratedAnswerPayload:
        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=1024,
            system=self._cached_system(),
            messages=self._build_messages(payload),
        )
        self._log_cache_usage(response.usage)
        text = response.content[0].text if response.content else ""
        return GeneratedAnswerPayload(message=text)

    def stream(self, payload: ModelGatewayRequest):
        with self.client.messages.stream(
            model=self.config.model,
            max_tokens=1024,
            system=self._cached_system(),
            messages=self._build_messages(payload),
        ) as stream:
            for text in stream.text_stream:
                if text:
                    yield text
            self._log_cache_usage(stream.get_final_message().usage)

    def _log_cache_usage(self, usage: object) -> None:
        if usage is None:
            return
        input_tokens   = getattr(usage, "input_tokens", 0)
        cache_created  = getattr(usage, "cache_creation_input_tokens", 0)
        cache_read     = getattr(usage, "cache_read_input_tokens", 0)
        output_tokens  = getattr(usage, "output_tokens", 0)
        total_input    = input_tokens + cache_created + cache_read
        saved_pct      = round(cache_read / total_input * 100) if total_input else 0
        logger.info(
            "anthropic_cache  input=%s cache_created=%s cache_read=%s (%s%% served from cache) output=%s",
            input_tokens, cache_created, cache_read, saved_pct, output_tokens,
        )

    def decide_action(
        self,
        payload: ModelGatewayRequest,
        available_tools: list[str],
        completed_tools: list[str],
        retrieval_done: bool,
        retrieval_attempts: int = 0,
        last_retrieval_confidence: float = 0.0,
    ) -> AgentAction:
        # Use deterministic local planning — saves one full model round-trip.
        return LocalModelGateway().decide_action(
            payload, available_tools, completed_tools,
            retrieval_done, retrieval_attempts, last_retrieval_confidence,
        )

    # ── Cache helpers ───────────────────────────────────────────────────────

    def _cached_system(self) -> list[dict]:
        """
        System prompt as a content block with cache_control.
        Anthropic caches this for 5 minutes across all requests that send
        the identical text — zero re-encoding cost on cache hits.
        """
        return [
            {
                "type": "text",
                "text": self.SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def _build_messages(self, payload: ModelGatewayRequest) -> list[dict]:
        """
        Build the user turn with two content blocks:

        Block 1 — evidence context (cached):
          Contains tool results, retrieval knowledge, grounding rules.
          Marked cache_control so follow-up questions about the same customer
          reuse this block without re-sending thousands of tokens.

        Block 2 — user message (not cached):
          The actual question. Changes every request so caching would never hit.
        """
        content: list[dict] = []

        evidence_text = self._format_evidence(payload)
        if evidence_text:
            content.append(
                {
                    "type": "text",
                    "text": evidence_text,
                    # Cache the evidence block — stable within a customer session.
                    "cache_control": {"type": "ephemeral"},
                }
            )

        content.append({"type": "text", "text": payload.user_message})

        return [{"role": "user", "content": content}]

    def _format_evidence(self, payload: ModelGatewayRequest) -> str:
        """Serialise all grounding context into a single text block."""
        parts: list[str] = []

        if payload.tool_context:
            parts.append(f"[Tool results]\n{json.dumps(payload.tool_context, ensure_ascii=False)}")

        if payload.retrieval_context:
            joined = "\n".join(f"- {chunk}" for chunk in payload.retrieval_context)
            parts.append(f"[Knowledge base]\n{joined}")

        if payload.evidence:
            lines = [f"- {item.title}: {item.detail}" for item in payload.evidence]
            parts.append(f"[Evidence]\n" + "\n".join(lines))

        if payload.grounding_rules:
            rules = "\n".join(f"- {rule}" for rule in payload.grounding_rules)
            parts.append(f"[Grounding rules]\n{rules}")

        if payload.user_attributes:
            attrs = ", ".join(f"{k}={v}" for k, v in payload.user_attributes.items())
            parts.append(f"[User attributes] {attrs}")

        return "\n\n".join(parts)


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
