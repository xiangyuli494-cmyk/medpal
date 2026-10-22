"""LLM 适配器：配置、OpenAI-compatible 实现与测试假实现。"""
from .base import (
    LlmClient,
    LlmConfigError,
    LlmDisabled,
    LlmError,
    LlmResponseError,
)
from .config import LlmConfig, is_placeholder, load_env_file
from .fakes import FakeLlm
from .openai_compat import OpenAICompatibleLlm

__all__ = [
    "FakeLlm",
    "LlmClient",
    "LlmConfig",
    "LlmConfigError",
    "LlmDisabled",
    "LlmError",
    "LlmResponseError",
    "OpenAICompatibleLlm",
    "is_placeholder",
    "load_env_file",
]
