"""LLM 配置与 OpenAI-compatible 适配器测试，不联网。"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from backend.adapters.llm import (
    LlmConfig,
    LlmConfigError,
    LlmDisabled,
    LlmError,
    LlmResponseError,
    OpenAICompatibleLlm,
    is_placeholder,
    load_env_file,
)

VALID_KEY = "sk-" + "a" * 30


def test_from_env_reads_llm_keys() -> None:
    config = LlmConfig.from_env(
        {
            "LLM_API_KEY": VALID_KEY,
            "LLM_BASE_URL": "https://example.com/v1/",
            "LLM_MODEL_FAST": "qwen-flash",
            "LLM_TIMEOUT": "12.5",
        }
    )

    assert config.api_key == VALID_KEY
    assert config.base_url == "https://example.com/v1"
    assert config.model == "qwen-flash"
    assert config.timeout == 12.5
    assert config.enabled is True
    assert config.validate() == []


def test_from_env_falls_back_to_dashscope_key() -> None:
    config = LlmConfig.from_env({"DASHSCOPE_API_KEY": VALID_KEY})

    assert config.api_key == VALID_KEY
    assert config.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_from_env_falls_back_to_main_model() -> None:
    config = LlmConfig.from_env({"LLM_MODEL_MAIN": "qwen3.8-flash"})

    assert config.model == "qwen3.8-flash"


def test_placeholder_key_is_ignored() -> None:
    config = LlmConfig.from_env({"LLM_API_KEY": "sk-your-real-api-key-here"})

    assert config.api_key is None
    assert "缺少 LLM_API_KEY" in config.validate()


def test_llm_disabled() -> None:
    config = LlmConfig.from_env({"LLM_ENABLED": "false", "LLM_API_KEY": VALID_KEY})

    assert config.enabled is False
    assert "LLM_ENABLED=False" in config.validate()


def test_load_env_file_parses_and_does_not_override(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "# comment\n"
        "FOO=from-file\n"
        'BAR="quoted value"\n'
        "BAZ=value # trailing comment\n"
        "export QUX=exported\n",
        encoding="utf-8",
    )
    env = {"FOO": "existing"}

    load_env_file(path, env=env)

    assert env["FOO"] == "existing"
    assert env["BAR"] == "quoted value"
    assert env["BAZ"] == "value"
    assert env["QUX"] == "exported"


def test_from_env_file(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        f"LLM_API_KEY={VALID_KEY}\nLLM_MODEL_FAST=test-model\n",
        encoding="utf-8",
    )

    config = LlmConfig.from_env(env={}, env_file=path)

    assert config.api_key == VALID_KEY
    assert config.model == "test-model"


def test_from_env_autoloads_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / ".env"
    path.write_text(f"LLM_API_KEY={VALID_KEY}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    config = LlmConfig.from_env()

    assert config.api_key == VALID_KEY


def test_is_placeholder() -> None:
    assert is_placeholder(None) is True
    assert is_placeholder("short") is True
    assert is_placeholder("sk-your-real-api-key-here") is True
    assert is_placeholder(VALID_KEY) is False


def test_openai_compatible_llm_posts_tool_payload() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OpenAICompatibleLlm(
        LlmConfig(api_key=VALID_KEY, base_url="https://example.com/v1", model="qwen-flash"),
        client=client,
    )
    tools = [{"type": "function", "function": {"name": "search_nodes"}}]

    message = llm.chat([{"role": "user", "content": "腿疼"}], tools)

    assert message["content"] == "ok"
    assert captured["url"] == "https://example.com/v1/chat/completions"
    assert captured["auth"] == f"Bearer {VALID_KEY}"
    assert captured["payload"]["model"] == "qwen-flash"
    assert captured["payload"]["tools"] == tools
    assert captured["payload"]["tool_choice"] == "auto"


def test_openai_compatible_llm_omits_tools_when_empty() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OpenAICompatibleLlm(LlmConfig(api_key=VALID_KEY), client=client)

    llm.chat([{"role": "user", "content": "hi"}], [])

    assert "tools" not in captured["payload"]


def test_openai_compatible_llm_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OpenAICompatibleLlm(LlmConfig(api_key=VALID_KEY), client=client)

    with pytest.raises(LlmError, match="HTTP 500"):
        llm.chat([{"role": "user", "content": "hi"}], [])


def test_openai_compatible_llm_bad_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OpenAICompatibleLlm(LlmConfig(api_key=VALID_KEY), client=client)

    with pytest.raises(LlmResponseError):
        llm.chat([{"role": "user", "content": "hi"}], [])


def test_openai_compatible_llm_config_errors() -> None:
    with pytest.raises(LlmConfigError):
        OpenAICompatibleLlm(LlmConfig(api_key=None)).chat([], [])
    with pytest.raises(LlmDisabled):
        OpenAICompatibleLlm(LlmConfig(api_key=VALID_KEY, enabled=False)).chat([], [])
