import os
import json
import sys

try:
    from groq import Groq
except ImportError:
    print("Error: groq not installed. Run: pip install groq")
    sys.exit(1)


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


# ── core ──────────────────────────────────────────────────────────────────────

def _get_client() -> Groq:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GROQ_API_KEY not set. Export it with:\n"
            "  export GROQ_API_KEY=your_key_here\n"
            "Get a free key at: https://console.groq.com/keys"
        )
    return Groq(api_key=api_key)


def analyze(parsed: dict, stream: bool = True) -> dict:
    """
    Takes parser.py output dict, returns:
    {
        "diagnosis": str,
        "fixes":     [str, ...],
        "severity":  "critical" | "warn" | "info"
    }
    Raises:
        EnvironmentError  — missing API key
        RateLimitError    — Groq free tier quota exceeded
        APIError          — API call failed
        ValueError        — response wasn't valid JSON
    """
    client = _get_client()
    user_message = _build_user_message(parsed)

    try:
        if stream:
            return _analyze_streaming(client, user_message)
        else:
            return _analyze_blocking(client, user_message)

    except EnvironmentError:
        raise
    except RateLimitError:
        raise
    except Exception as e:
        err_str = str(e).lower()
        if any(kw in err_str for kw in ("rate limit", "429", "quota", "too many requests")):
            raise RateLimitError(
                "Groq free tier rate limit hit.\n"
                "Options:\n"
                "  1. Wait ~30 seconds and retry (per-minute token limit)\n"
                "  2. Switch model with EXPLAIN_LOG_MODEL env var (see below)\n"
                "  3. Upgrade at https://console.groq.com"
            ) from e
        raise APIError(f"Groq API call failed: {e}") from e


def _analyze_blocking(client: Groq, user_message: str) -> dict:
    model = os.environ.get("EXPLAIN_LOG_MODEL", "llama-3.3-70b-versatile")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        temperature=0.2,
        max_tokens=1024,
    )
    return _parse_response(response.choices[0].message.content)


def _analyze_streaming(client: Groq, user_message: str) -> dict:
    model = os.environ.get("EXPLAIN_LOG_MODEL", "llama-3.3-70b-versatile")
    full_text = ""
    print("  analyzing", end="", file=sys.stderr, flush=True)

    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        temperature=0.2,
        max_tokens=1024,
        stream=True,
    )

    for chunk in stream:
        token = chunk.choices[0].delta.content
        if token:
            full_text += token
            print(".", end="", file=sys.stderr, flush=True)

    print(" done", file=sys.stderr, flush=True)
    return _parse_response(full_text)


def _parse_response(raw: str) -> dict:
    import re

    # Extract JSON only
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
    """Raised when Groq free tier quota is exceeded."""
    pass


# ── quick test (run directly: python ai.py) ───────────────────────────────────

if __name__ == "__main__":
    fake_parsed = {
        "log_type": "systemd",
        "truncated": False,
        "line_count": 5,
        "lines": [
            "Apr 03 03:41:12 kernel: Out of memory: Killed process 1842 (postgres) score 920 or sacrifice child",
            "Apr 03 03:41:12 kernel: oom_reaper: reaped process 1842 (postgres), now anon-rss:0kB",
            "Apr 03 03:41:13 systemd[1]: postgresql.service: Main process exited, code=killed, status=9/KILL",
            "Apr 03 03:41:13 systemd[1]: postgresql.service: Failed with result 'oom-kill'.",
            "Apr 03 03:41:13 systemd[1]: Failed to start PostgreSQL Database Server.",
        ]
    }

    result = analyze(fake_parsed, stream=True)
    print("\n--- RESULT ---")
    print(json.dumps(result, indent=2))