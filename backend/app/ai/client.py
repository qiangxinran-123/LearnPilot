from __future__ import annotations

import json
import logging
import re
import socket
import time
from dataclasses import dataclass
from typing import TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ValidationError

from backend.app.ai.errors import AIServiceError
from backend.app.ai.models import DiagnosticQuestionGenerationOutput
from backend.app.core.settings import Settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class GeneratedStructuredOutput:
    data: BaseModel
    provider: str
    model: str


class LLMClient:
    def generate_structured(
        self,
        *,
        operation: str,
        messages: list[dict[str, str]],
        schema: type[T],
    ) -> GeneratedStructuredOutput:
        raise NotImplementedError


class OpenAICompatibleLLMClient(LLMClient):
    provider = "openai-compatible"

    def __init__(self, settings: Settings) -> None:
        self.api_key = settings.llm_api_key
        self.base_url = settings.llm_base_url.rstrip("/")
        self.model = settings.llm_model
        self.timeout_seconds = settings.llm_timeout_seconds
        self.max_attempts = settings.llm_max_attempts
        if not self.api_key or not self.base_url or not self.model:
            raise AIServiceError(
                "AI_NOT_CONFIGURED",
                "AI 服务尚未配置。请在后端设置 LLM_API_KEY、LLM_BASE_URL 和 LLM_MODEL。",
            )

    @property
    def endpoint(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    def generate_structured(
        self,
        *,
        operation: str,
        messages: list[dict[str, str]],
        schema: type[T],
    ) -> GeneratedStructuredOutput:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        last_error: AIServiceError | None = None
        for attempt in range(self.max_attempts):
            started = time.monotonic()
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    raw_body = response.read()
                try:
                    body = json.loads(raw_body)
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise AIServiceError("AI_INVALID_OUTPUT", "AI 服务未返回有效的 JSON。") from error
                content = self._extract_content(body)
                try:
                    result = schema.model_validate_json(content)
                except ValidationError as error:
                    raise AIServiceError(
                        "AI_INVALID_OUTPUT",
                        "AI 返回结果不符合预期结构。",
                        retryable=True,
                    ) from error
                self._log(operation, started, True)
                return GeneratedStructuredOutput(result, self.provider, self.model)
            except HTTPError as error:
                if error.code in {401, 403}:
                    code = "AI_AUTHENTICATION_FAILED"
                elif error.code == 429:
                    code = "AI_RATE_LIMITED"
                else:
                    code = "AI_PROVIDER_ERROR"
                retryable = error.code == 429 or error.code >= 500
                last_error = AIServiceError(code, "AI 服务暂时不可用，请稍后重试。", retryable=retryable)
            except TimeoutError, socket.timeout:
                last_error = AIServiceError("AI_TIMEOUT", "AI 请求超时，请稍后重试。", retryable=True)
            except URLError:
                last_error = AIServiceError("AI_PROVIDER_ERROR", "无法连接 AI 服务，请稍后重试。", retryable=True)
            except AIServiceError as error:
                last_error = error
            self._log(operation, started, False)
            if last_error is None or not last_error.retryable or attempt + 1 >= self.max_attempts:
                break
            time.sleep(0.25 * (attempt + 1))
        if last_error is None:
            raise AIServiceError("AI_PROVIDER_ERROR", "AI 服务调用失败。")
        raise last_error

    @staticmethod
    def _extract_content(body: object) -> str:
        if not isinstance(body, dict):
            raise AIServiceError("AI_INVALID_OUTPUT", "AI 服务响应结构不完整。")
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise AIServiceError("AI_INVALID_OUTPUT", "AI 服务响应结构不完整。")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise AIServiceError("AI_INVALID_OUTPUT", "AI 服务响应结构不完整。")
        content = message.get("content")
        if not isinstance(content, str):
            raise AIServiceError("AI_INVALID_OUTPUT", "AI 服务未返回可解析的结构化结果。")
        return content

    def _log(self, operation: str, started: float, success: bool) -> None:
        logger.info(
            "llm_operation operation=%s provider=%s model=%s latency_ms=%d success=%s",
            operation,
            self.provider,
            self.model,
            int((time.monotonic() - started) * 1000),
            success,
        )


def _mock_diagnostic_question(source: str) -> dict[str, object]:
    # Only the request header supplies the target; material content is untrusted.
    header, separator, remainder = source.partition("\n<untrusted_course_material>\n")
    context, end, _ = remainder.partition("\n</untrusted_course_material>")
    target = re.search(r"^目标知识节点：id=(\d+); name=([^\n;]+); description=", header, re.MULTILINE)
    kind = re.search(r"^题型：(single_choice|true_false|multiple_choice)$", header, re.MULTILINE)
    difficulty = re.search(r"^难度：(easy|medium|hard)$", header, re.MULTILINE)
    count = re.search(r"^生成 (\d+) 道互不重复的候选题。$", header, re.MULTILINE)
    reference = re.search(r"^\[material_id=(\d+); source_reference=([^\]\n]+)\]\n([^\n]+)", context, re.MULTILINE)
    if not separator or not end or not target or not kind or not difficulty or not count or not reference:
        raise AIServiceError("AI_INVALID_OUTPUT", "Mock 诊断需要有效的知识点和资料来源。")
    if int(count.group(1)) != 1:
        raise AIServiceError("AI_INVALID_OUTPUT", "Mock 诊断每次只能生成一道题，请减少请求数量。")
    node_id, material_id = int(target.group(1)), int(reference.group(1))
    node_name = target.group(2).strip()
    excerpt = reference.group(3).strip()[:160]
    if node_id < 1 or material_id < 1 or not node_name or len(excerpt) < 12:
        raise AIServiceError("AI_INVALID_OUTPUT", "Mock 诊断的知识点或资料内容不足。")

    question_type = kind.group(1)
    if question_type == "true_false":
        stem = f"【模拟题】关于「{node_name}」，资料中是否包含这段原文：{excerpt}"
        options = [{"key": "TRUE", "text": "正确"}, {"key": "FALSE", "text": "错误"}]
        answers = ["TRUE"]
        explanation = "题干引用的是提供的资料原文，因此正确；该模拟题只核对原文。"
    elif question_type == "multiple_choice":
        middle = len(excerpt) // 2
        stem = f"【模拟题】关于「{node_name}」，哪些片段来自提供的资料原文？"
        options = [
            {"key": "A", "text": excerpt[:middle]},
            {"key": "B", "text": excerpt[middle:]},
            {"key": "C", "text": "该资料没有提供任何文字"},
        ]
        answers = ["A", "B"]
        explanation = "前两项均摘自提供的资料原文；资料并非空白。该模拟题只核对原文。"
    else:
        stem = f"【模拟题】关于「{node_name}」，下列哪项是提供的资料原文？"
        options = [{"key": "A", "text": excerpt}, {"key": "B", "text": "该资料没有提供任何文字"}]
        answers = ["A"]
        explanation = "第一项摘自提供的资料原文；资料并非空白。该模拟题只核对原文。"
    return {
        "questions": [
            {
                "question_type": question_type,
                "stem": stem,
                "options": options,
                "correct_answer": answers,
                "explanation": explanation,
                "difficulty": difficulty.group(1),
                "knowledge_node_ids": [node_id],
                "source_refs": [{"material_id": material_id, "source_reference": reference.group(2)}],
            }
        ]
    }


class ExplicitMockLLMClient(LLMClient):
    """Deterministic local adapter used only when LLM_MODE=mock is explicitly selected."""

    provider = "mock"
    model = "deterministic-m2"

    def generate_structured(
        self,
        *,
        operation: str,
        messages: list[dict[str, str]],
        schema: type[T],
    ) -> GeneratedStructuredOutput:
        source = messages[-1]["content"] if messages else ""
        compact = " ".join(source.split())[:360] or "资料内容"
        references = list(dict.fromkeys(re.findall(r"^\[([^\]\n]+)\]$", source, flags=re.MULTILINE)))
        fields = schema.model_fields
        if operation == "diagnostic_question_generation" and schema is DiagnosticQuestionGenerationOutput:
            payload = _mock_diagnostic_question(source)
        elif "contains_edges" in fields and "prerequisite_edges" in fields:
            payload: dict[str, object] = {"contains_edges": [], "prerequisite_edges": []}
        elif "groups" in fields:
            payload: dict[str, object] = {"groups": []}
        elif "candidates" in fields:
            payload: dict[str, object] = {
                "candidates": (
                    [
                        {
                            "name": "核心概念",
                            "description": compact[:500],
                            "importance": "medium",
                            "difficulty": "intermediate",
                            "source_references": [references[0]],
                        }
                    ]
                    if references
                    else []
                )
            }
        elif "cards" in fields:
            payload: dict[str, object] = {
                "cards": [
                    {
                        "question": f"这份资料的第 {index + 1} 个重点是什么？",
                        "answer": compact[:240],
                        "knowledge_hint": "基于当前资料内容复习。",
                        "source_reference": references[0] if references else None,
                    }
                    for index in range(5)
                ]
            }
        elif "sufficient_evidence" in fields:
            payload = {"answer": compact, "sufficient_evidence": True, "references": references[:4]}
        elif {"answer", "mode", "citations", "insufficient_evidence"}.issubset(fields):
            joined = "\n".join(message.get("content", "") for message in messages)
            mode_match = re.search(r"TEACHING_MODE=([a-z_]+)", joined)
            source_match = re.search(
                r'<source material_id="(\d+)" reference="([^"]+)"',
                joined,
            )
            payload = {
                "answer": f"Mock tutor: {compact}",
                "mode": mode_match.group(1) if mode_match else "guided_question",
                "citations": (
                    [
                        {
                            "material_id": int(source_match.group(1)),
                            "source_reference": source_match.group(2),
                        }
                    ]
                    if source_match
                    else []
                ),
                "insufficient_evidence": source_match is None,
            }
        else:
            payload = {
                "overview": f"Mock summary: {compact}",
                "key_concepts": ["核心概念"],
                "important_points": ["重要内容"],
                "common_mistakes": [],
                "review_suggestions": ["结合资料原文复习。"],
            }
        logger.warning("llm_operation operation=%s provider=mock model=%s success=true", operation, self.model)
        return GeneratedStructuredOutput(schema.model_validate(payload), self.provider, self.model)


def get_llm_client(settings: Settings) -> LLMClient:
    if settings.llm_mode == "mock":
        return ExplicitMockLLMClient()
    return OpenAICompatibleLLMClient(settings)
