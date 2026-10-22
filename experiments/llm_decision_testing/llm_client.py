"""
Lightweight, standard-library LLM Client for OpenAI-compatible endpoints.

Designed for local inference servers hosting Qwen 3.5 0.8B (Ollama, llama.cpp, vLLM, LM Studio).
Uses exclusively Python standard library (urllib.request, json, time).

Guarantees:
- Zero external dependencies required.
- Structured JSON output mode (response_format: {"type": "json_object"}).
- Configurable reasoning_effort (maps to think: false in Ollama for fast, non-looping reasoning).
- Clear, actionable diagnostic errors on connection failure, timeout, truncation, or HTTP errors.
- Never hardcodes secrets or modifies server state.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class LLMConfig:
    """Configuration for connecting to an OpenAI-compatible inference server."""
    base_url: str = "http://127.0.0.1:11434/v1"
    model_name: str = "qwen3.5:0.8b"
    api_key: str = "ollama"
    timeout_seconds: float = 60.0
    temperature: float = 0.1
    max_tokens: int = 1024
    reasoning_effort: Optional[str] = "none"
    request_retries: int = 2

    @classmethod
    def load(cls, config_path: Optional[str | Path] = None) -> "LLMConfig":
        """
        Load configuration from file and/or environment variables.
        Environment variables take precedence over config files.
        """
        data: dict[str, Any] = {}

        # 1. Try specified or default config file
        resolved_path = Path(config_path) if config_path else Path(__file__).parent / "config.json"
        if resolved_path.exists():
            try:
                with open(resolved_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                print(f"[Warning] Failed to parse config file at {resolved_path}: {e}")

        # 2. Extract values with env var overrides
        base_url = os.environ.get("LLM_BASE_URL", data.get("base_url", "http://127.0.0.1:11434/v1")).rstrip("/")
        model_name = os.environ.get("LLM_MODEL_NAME", data.get("model_name", "qwen3.5:0.8b"))
        api_key = os.environ.get("LLM_API_KEY", data.get("api_key", "ollama"))

        timeout_env = os.environ.get("LLM_TIMEOUT")
        timeout_seconds = float(timeout_env) if timeout_env else float(data.get("timeout_seconds", 60.0))

        temp_env = os.environ.get("LLM_TEMPERATURE")
        temperature = float(temp_env) if temp_env else float(data.get("temperature", 0.1))

        tokens_env = os.environ.get("LLM_MAX_TOKENS")
        max_tokens = int(tokens_env) if tokens_env else int(data.get("max_tokens", 1024))

        effort_env = os.environ.get("LLM_REASONING_EFFORT")
        reasoning_effort = effort_env if effort_env is not None else data.get("reasoning_effort", "none")

        retries = int(data.get("request_retries", 2))

        return cls(
            base_url=base_url,
            model_name=model_name,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
            request_retries=retries,
        )


class LLMClient:
    """Client for querying an OpenAI-compatible local LLM endpoint."""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig.load()

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AI-CSV-Data-Analyst-DecisionTester/1.0",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def check_server_health(self) -> tuple[bool, str, list[str]]:
        """
        Check whether the local inference server is reachable and query available models.

        Returns:
            (is_healthy, status_message, list_of_available_model_ids)
        """
        models_url = f"{self.config.base_url}/models"
        req = urllib.request.Request(models_url, headers=self._build_headers(), method="GET")

        try:
            with urllib.request.urlopen(req, timeout=min(5.0, self.config.timeout_seconds)) as resp:
                if resp.status == 200:
                    body = json.loads(resp.read().decode("utf-8"))
                    models: list[str] = []
                    if isinstance(body, dict) and "data" in body and isinstance(body["data"], list):
                        models = [m.get("id", "") for m in body["data"] if isinstance(m, dict) and m.get("id")]
                    return True, "Server reachable", models
                return False, f"Server returned HTTP {resp.status}", []
        except urllib.error.HTTPError as e:
            return False, f"HTTP Error {e.code}: {e.reason}", []
        except urllib.error.URLError as e:
            return False, f"Connection failed to {self.config.base_url}: {e.reason}", []
        except Exception as e:
            return False, f"Health check failed: {str(e)}", []

    def generate_decision(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[str, float, dict[str, Any]]:
        """
        Submit prompt to the LLM and receive raw text response.

        Returns:
            (raw_text_response, latency_seconds, metadata_dict)
        """
        endpoint = f"{self.config.base_url}/chat/completions"

        payload: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": False,
        }

        # reasoning_effort controls Ollama reasoning/thinking mode (e.g. 'none' disables thinking loop)
        if self.config.reasoning_effort:
            payload["reasoning_effort"] = self.config.reasoning_effort

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data_bytes, headers=self._build_headers(), method="POST")

        start_time = time.perf_counter()
        last_error: Optional[Exception] = None

        for attempt in range(max(1, self.config.request_retries + 1)):
            try:
                with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                    elapsed = time.perf_counter() - start_time
                    if resp.status != 200:
                        raise RuntimeError(f"Server returned status {resp.status}")

                    response_body = json.loads(resp.read().decode("utf-8"))
                    raw_content = ""
                    finish_reason = None
                    if "choices" in response_body and len(response_body["choices"]) > 0:
                        choice = response_body["choices"][0]
                        msg = choice.get("message", {})
                        raw_content = msg.get("content", "")
                        finish_reason = choice.get("finish_reason")

                    meta = {
                        "model": response_body.get("model", self.config.model_name),
                        "usage": response_body.get("usage", {}),
                        "latency_seconds": round(elapsed, 4),
                        "finish_reason": finish_reason,
                        "status": "success",
                    }
                    if finish_reason == "length":
                        meta["warning"] = f"Response truncated by max_tokens limit ({self.config.max_tokens})"

                    return raw_content, elapsed, meta

            except urllib.error.HTTPError as e:
                err_body = ""
                try:
                    err_body = e.read().decode("utf-8")
                except Exception:
                    pass
                last_error = RuntimeError(f"HTTP {e.code} ({e.reason}): {err_body}")
            except urllib.error.URLError as e:
                last_error = ConnectionError(
                    f"Failed to connect to LLM server at {self.config.base_url}. "
                    f"Is Qwen 3.5 0.8B running? Details: {e.reason}"
                )
            except Exception as e:
                last_error = e

            # Brief backoff before retry if retries remaining
            if attempt < self.config.request_retries:
                time.sleep(0.5 * (attempt + 1))

        elapsed = time.perf_counter() - start_time
        meta = {
            "model": self.config.model_name,
            "error": str(last_error),
            "latency_seconds": round(elapsed, 4),
            "status": "error",
        }
        raise last_error if last_error else RuntimeError("Unknown error calling LLM")
