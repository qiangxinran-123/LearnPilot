from __future__ import annotations


class AIServiceError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)


def knowledge_build_provider_message(code: str) -> str | None:
    """Return safe, actionable feedback for recoverable knowledge-build failures."""
    return {
        "AI_TIMEOUT": "本次知识结构生成超时，请稍后重试。",
        "AI_RATE_LIMITED": "AI 服务请求较多，请稍后重试。",
        "AI_AUTHENTICATION_FAILED": "AI 服务认证失败，请检查服务配置。",
        "AI_NOT_CONFIGURED": "AI 服务尚未配置，请检查服务配置。",
    }.get(code)
