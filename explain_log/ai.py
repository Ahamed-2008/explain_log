import json
import os
import re
import sys

import httpx

from explain_log.config import (
    API_KEY_ENV,
    API_KEY_HELP,
    DEFAULT_MODELS,
    GEMINI_MODEL_ALIASES,
    get_api_key,
    load_config,
)

# ── prompt ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert Linux/systems engineer and debugger.
Given a log excerpt, respond ONLY with a valid JSON object — no markdown, no explanation outside the JSON.

Schema:
{
  "diagnosis": "2-3 sentence plain-English explanation of the root cause",
  "fixes": ["fix 1", "fix 2", "fix 3"],
  "severity": "critical | warn | info"
}

Rules:
- severity is "critical" if the system crashed, OOM killed, or service failed
- severity is "warn" for recoverable errors or high-frequency warnings  
- severity is "info" if there are no real errors
- fixes must be specific and actionable — no generic advice like "check your config"
- if there are no errors in the log, set diagnosis to "No errors found." and fixes to []
"""


def _build_user_message(parsed: dict) -> str:
    log_type = parsed.get("log_type", "unknown")
    lines = parsed.get("lines", [])
    truncated = parsed.get("truncated", False)

    header = f"Log type: {log_type}\n"
    if truncated:
        header += f"(Log was truncated to {len(lines)} most relevant lines)\n"
    header += "\n--- LOG START ---\n"

    return header + "\n".join(lines) + "\n--- LOG END ---"


def _messages(user_message: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]


def _resolve_model(cfg: dict) -> str:
    model = cfg.get("model") or DEFAULT_MODELS[cfg["provider"]]
    if cfg["provider"] == "gemini":
        replacement = GEMINI_MODEL_ALIASES.get(model)
        if replacement:
            print(
                f"  note: Gemini model '{model}' is deprecated; using '{replacement}'",
                file=sys.stderr,
            )
            return replacement
    return model


def _require_api_key(provider: str) -> str:
    env_var = API_KEY_ENV[provider]
    key = get_api_key(provider)
    if not key:
        help_text = API_KEY_HELP.get(provider, f"export {env_var}=your_key_here")
        raise EnvironmentError(
            f"{env_var} is not set or is empty.\n"
            f"{help_text}"
        )
    return key


def _read_response_body(response: httpx.Response) -> bytes:
    """Read body from regular or streaming httpx responses."""
    try:
        return response.content
    except httpx.ResponseNotRead:
        return response.read()


def _http_error_detail(response: httpx.Response) -> str:
    raw = _read_response_body(response)
    if not raw:
        return response.reason_phrase or ""
    try:
        body = json.loads(raw)
        err = body.get("error", body)
        if isinstance(err, dict):
            return err.get("message", str(err))
        return str(err)
    except json.JSONDecodeError:
        return raw.decode("utf-8", errors="replace").strip()[:300]


def _raise_for_status(response: httpx.Response, provider: str, *, model: str = "") -> None:
    if response.is_success:
        return
    detail = _http_error_detail(response)
    if response.status_code == 401:
        env_var = API_KEY_ENV.get(provider, "API_KEY")
        help_text = API_KEY_HELP.get(provider, "")
        raise APIError(
            f"Authentication failed for {provider} (401 Unauthorized).\n"
            f"Your {env_var} was rejected — check for typos, expired keys, or extra quotes.\n"
            + (f"{help_text}\n" if help_text else "")
            + (f"API message: {detail}" if detail else "")
        )
    if response.status_code == 404 and provider == "gemini":
        suggested = DEFAULT_MODELS["gemini"]
        raise APIError(
            f"Gemini model not found (404): {model or 'unknown'}\n"
            f"This model may be deprecated. Try: explain-log --change-api\n"
            f"Suggested model: {suggested}\n"
            + (f"API message: {detail}" if detail else "")
        )
    raise APIError(
        f"API call failed ({response.status_code}): {detail or response.reason_phrase}"
    )


def _check_stream_response(response: httpx.Response, provider: str, *, model: str = "") -> None:
    if response.is_error:
        response.read()
        _raise_for_status(response, provider, model=model)


# ── provider calls ────────────────────────────────────────────────────────────

def _call_chat_completions(
    messages: list[dict],
    model: str,
    api_key: str,
    stream: bool,
    *,
    api_url: str,
    provider: str,
) -> str:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1024,
        "stream": stream,
    }

    if not stream:
        r = httpx.post(api_url, json=payload, headers=headers, timeout=120)
        _raise_for_status(r, provider)
        return r.json()["choices"][0]["message"]["content"]

    full_text = ""
    with httpx.stream("POST", api_url, json=payload, headers=headers, timeout=120) as r:
        _check_stream_response(r, provider)
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data.strip() == "[DONE]":
                break
            chunk = json.loads(data)
            token = chunk["choices"][0]["delta"].get("content")
            if token:
                full_text += token
                print(".", end="", file=sys.stderr, flush=True)
    return full_text


def _call_openai(messages: list[dict], model: str, api_key: str, stream: bool) -> str:
    return _call_chat_completions(
        messages, model, api_key, stream,
        api_url="https://api.openai.com/v1/chat/completions",
        provider="openai",
    )


def _call_groq(messages: list[dict], model: str, api_key: str, stream: bool) -> str:
    return _call_chat_completions(
        messages, model, api_key, stream,
        api_url="https://api.groq.com/openai/v1/chat/completions",
        provider="groq",
    )


def _call_anthropic(messages: list[dict], model: str, api_key: str, stream: bool) -> str:
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    user_content = next(m["content"] for m in messages if m["role"] == "user")
    system_content = next(m["content"] for m in messages if m["role"] == "system")
    payload = {
        "model": model,
        "max_tokens": 1024,
        "system": system_content,
        "messages": [{"role": "user", "content": user_content}],
        "stream": stream,
    }

    if not stream:
        r = httpx.post(url, json=payload, headers=headers, timeout=120)
        _raise_for_status(r, "anthropic", model=model)
        return r.json()["content"][0]["text"]

    full_text = ""
    with httpx.stream("POST", url, json=payload, headers=headers, timeout=120) as r:
        _check_stream_response(r, "anthropic", model=model)
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            data = json.loads(line[6:])
            if data.get("type") == "content_block_delta":
                token = data["delta"].get("text", "")
                if token:
                    full_text += token
                    print(".", end="", file=sys.stderr, flush=True)
    return full_text


def _call_gemini(messages: list[dict], model: str, api_key: str, stream: bool) -> str:
    user_content = next(m["content"] for m in messages if m["role"] == "user")
    system_content = next(m["content"] for m in messages if m["role"] == "system")

    if not stream:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        payload = {
            "system_instruction": {"parts": [{"text": system_content}]},
            "contents": [{"parts": [{"text": user_content}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024},
        }
        r = httpx.post(url, json=payload, timeout=120)
        _raise_for_status(r, "gemini", model=model)
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:streamGenerateContent?key={api_key}&alt=sse"
    )
    payload = {
        "system_instruction": {"parts": [{"text": system_content}]},
        "contents": [{"parts": [{"text": user_content}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024},
    }
    full_text = ""
    with httpx.stream("POST", url, json=payload, timeout=120) as r:
        _check_stream_response(r, "gemini", model=model)
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            chunk = json.loads(line[6:])
            for candidate in chunk.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    token = part.get("text", "")
                    if token:
                        full_text += token
                        print(".", end="", file=sys.stderr, flush=True)
    return full_text


def _call_ollama(
    messages: list[dict],
    model: str,
    base_url: str,
    stream: bool,
) -> str:
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "options": {"temperature": 0.2},
    }

    if not stream:
        r = httpx.post(url, json=payload, timeout=180)
        _raise_for_status(r, "ollama", model=model)
        return r.json()["message"]["content"]

    full_text = ""
    with httpx.stream("POST", url, json=payload, timeout=180) as r:
        _check_stream_response(r, "ollama", model=model)
        for line in r.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            token = chunk.get("message", {}).get("content", "")
            if token:
                full_text += token
                print(".", end="", file=sys.stderr, flush=True)
    return full_text


def _dispatch(cfg: dict, messages: list[dict], stream: bool) -> str:
    provider = cfg["provider"]
    model = _resolve_model(cfg)

    if provider == "openai":
        key = _require_api_key("openai")
        return _call_openai(messages, model, key, stream)

    if provider == "anthropic":
        key = _require_api_key("anthropic")
        return _call_anthropic(messages, model, key, stream)

    if provider == "gemini":
        key = _require_api_key("gemini")
        return _call_gemini(messages, model, key, stream)

    if provider == "groq":
        key = _require_api_key("groq")
        return _call_groq(messages, model, key, stream)

    if provider == "ollama":
        base_url = cfg.get("base_url") or os.environ.get(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        )
        return _call_ollama(messages, model, base_url, stream)

    raise ValueError(f"Unknown provider '{provider}'")


# ── core ──────────────────────────────────────────────────────────────────────

def analyze(parsed: dict, stream: bool = True, config: dict | None = None) -> dict:
    """
    Takes parser.py output dict, returns:
    {
        "diagnosis": str,
        "fixes":     [str, ...],
        "severity":  "critical" | "warn" | "info"
    }
    """
    cfg = config or load_config()
    if not cfg:
        raise EnvironmentError(
            "No API provider configured. Run explain-log once to set up, "
            "or use: explain-log --change-api"
        )

    user_message = _build_user_message(parsed)
    messages = _messages(user_message)

    try:
        if stream:
            print("  analyzing", end="", file=sys.stderr, flush=True)
            try:
                raw = _dispatch(cfg, messages, stream=True)
            except Exception:
                print(file=sys.stderr)  # newline after "analyzing"
                raise
            print(" done", file=sys.stderr, flush=True)
        else:
            raw = _dispatch(cfg, messages, stream=False)
        return _parse_response(raw)

    except EnvironmentError:
        raise
    except APIError:
        raise
    except RateLimitError:
        raise
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            raise RateLimitError(
                "API rate limit hit. Wait a moment and retry, "
                "or switch provider with: explain-log --change-api"
            ) from e
        provider = cfg.get("provider", "api")
        model = _resolve_model(cfg)
        try:
            _read_response_body(e.response)
        except Exception:
            pass
        _raise_for_status(e.response, provider, model=model)
    except Exception as e:
        err_str = str(e).lower()
        if any(kw in err_str for kw in ("rate limit", "429", "quota", "too many requests")):
            raise RateLimitError(
                "API rate limit hit. Wait a moment and retry, "
                "or switch provider with: explain-log --change-api"
            ) from e
        raise APIError(f"API call failed: {e}") from e


def _parse_response(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in model output:\n{raw}")

    cleaned = match.group(0)

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Model returned non-JSON response.\n"
            f"Raw output:\n{raw}\n"
            f"Parse error: {e}"
        )

    return {
        "diagnosis": result.get("diagnosis", "Could not determine root cause."),
        "fixes": result.get("fixes", []),
        "severity": result.get("severity", "warn")
        if result.get("severity") in ("critical", "warn", "info")
        else "warn",
    }


# ── custom exceptions ─────────────────────────────────────────────────────────

class ExplainLogError(Exception):
    pass


class APIError(ExplainLogError):
    pass


class RateLimitError(ExplainLogError):
    """Raised when an API provider rate limit is exceeded."""
    pass
