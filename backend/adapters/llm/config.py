"""LLM 配置：从环境变量或 .env 读取，不引入额外依赖。"""
from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen-flash"


def load_env_file(
    path: str | Path, env: MutableMapping[str, str] | None = None
) -> dict[str, str]:
    """把简单的 KEY=VALUE .env 文件读进 env；已存在的键不覆盖。"""
    target = env if env is not None else os.environ
    file_path = Path(path)
    if not file_path.is_file():
        return dict(target)

    for raw in file_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in target:
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        else:
            value = value.split("#", 1)[0].strip()
        target[key] = value

    return dict(target)


def _env(env: Mapping[str, str], key: str) -> str | None:
    value = env.get(key)
    if value is None:
        return None
    value = value.strip()
    return value or None


def is_placeholder(value: str | None) -> bool:
    """识别 .env 里的占位 Key，避免「看起来配了其实没配」。"""
    if not value:
        return True
    if len(value) < 20:
        return True
    lowered = value.lower()
    markers = ("your-", "your_", "placeholder", "change-me", "changeme", "example", "sk-x")
    return any(marker in lowered for marker in markers)


def _float(value: str | None, default: float) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class LlmConfig:
    api_key: str | None = None
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout: float = 60.0
    enabled: bool = True

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        env_file: str | Path | None = None,
    ) -> LlmConfig:
        source = dict(os.environ if env is None else env)
        if env_file is None and env is None:
            default_file = Path.cwd() / ".env"
            if default_file.is_file():
                env_file = default_file
        if env_file is not None:
            load_env_file(env_file, env=source)

        api_key = (
            _env(source, "LLM_API_KEY")
            or _env(source, "DASHSCOPE_API_KEY")
            or _env(source, "OPENAI_API_KEY")
        )
        if is_placeholder(api_key):
            api_key = None

        base_url = (
            _env(source, "LLM_BASE_URL")
            or _env(source, "DASHSCOPE_API_BASE")
            or DEFAULT_BASE_URL
        ).rstrip("/")
        model = (
            _env(source, "LLM_MODEL_FAST")
            or _env(source, "LLM_MODEL_STANDARD")
            or _env(source, "LLM_MODEL_MAIN")
            or _env(source, "LLM_MODEL")
            or DEFAULT_MODEL
        )
        enabled = (_env(source, "LLM_ENABLED") or "true").lower() not in (
            "false",
            "0",
            "no",
            "off",
        )
        timeout = _float(_env(source, "LLM_TIMEOUT"), 60.0)

        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
            enabled=enabled,
        )

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.enabled:
            problems.append("LLM_ENABLED=False")
        if not self.api_key:
            problems.append("缺少 LLM_API_KEY")
        if not self.base_url:
            problems.append("缺少 LLM_BASE_URL")
        if not self.model:
            problems.append("缺少 LLM_MODEL_FAST")
        return problems
