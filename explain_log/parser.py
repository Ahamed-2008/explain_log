import re
import sys
from typing import Optional


# ── log type detection patterns ───────────────────────────────────────────────

LOG_TYPE_PATTERNS = {
    "nginx":    [r"nginx", r"\[error\]", r"upstream", r"GET |POST |PUT |DELETE ", r"HTTP/1"],
    "systemd":  [r"systemd\[", r"\.service:", r"Started |Stopped |Failed ", r"journalctl"],
    "python":   [r"Traceback \(most recent call last\)", r"^\s+File \"", r"Error:", r"Exception:"],
    "kernel":   [r"kernel:", r"\[\s*\d+\.\d+\]", r"Out of memory", r"segfault at", r"oom_reaper"],
    "apache":   [r"apache2?", r"\[warn\]", r"\[crit\]", r"AH\d{5}"],
    "postgres": [r"postgres", r"LOG:", r"FATAL:", r"pg_ctl", r"PANIC:"],
    "ssh":      [r"sshd\[", r"Failed password", r"Invalid user", r"Accepted publickey"],
    "docker":   [r"dockerd", r"containerd", r"container \w+ died", r"OCI runtime"],
}

# Lines matching these are errors/warnings worth keeping
ERROR_PATTERNS = [
    r"\b(error|err)\b",
    r"\b(warn|warning)\b",
    r"\bcritical\b",
    r"\bfatal\b",
    r"\bfailed?\b",
    r"\bpanic\b",
    r"\bexception\b",
    r"\btraceback\b",
    r"\bkilled\b",
    r"\bsegfault\b",
    r"\bcore dumped\b",
    r"\boom\b",
    r"\bdenied\b",
    r"\brefused\b",
    r"\btimeout\b",
    r"\bcrash\b",
    r"\babort\b",
    r"\bcannot\b",
    r"\bunable to\b",
    r"\bno such file\b",
    r"\bpermission denied\b",
    r"\bconnection refused\b",
    r"\baddress already in use\b",
]

# Compile once at module load — don't recompile on every line
_ERROR_RE   = re.compile("|".join(ERROR_PATTERNS), re.IGNORECASE)
_TYPE_RES   = {
    log_type: [re.compile(p, re.IGNORECASE) for p in patterns]
    for log_type, patterns in LOG_TYPE_PATTERNS.items()
}

# Lines that are pure noise — skip entirely
_NOISE_RE = re.compile(
    r"^\s*$"                          # blank lines
    r"|--+ (BEGIN|END) --+"           # delimiter lines
    r"|\[\s*ok\s*\]"                  # systemd OK lines
    r"|Started.*\.$"                  # systemd "Started X." success lines
    r"|Reached target"                # systemd target milestones
    r"|systemd\[1\]: Starting ",      # systemd "Starting X..." (pre-start, not useful)
    re.IGNORECASE
)


# ── public api ────────────────────────────────────────────────────────────────

def preprocess(
    raw_text: str,
    last_n:     Optional[int] = None,
    max_tokens: int           = 3000,
) -> dict:
    """
    Parses raw log text and returns a dict ready for ai.py.

    Returns:
    {
        "lines":      [str, ...],   # filtered, relevant lines
        "log_type":   str,          # detected log type
        "line_count": int,          # original line count before filtering
        "truncated":  bool          # True if we had to cut lines for token budget
    }

    Raises:
        EmptyLogError   — input was empty or had no content after stripping
    """
    if not raw_text or not raw_text.strip():
        raise EmptyLogError("Log input is empty. Pipe a log file or use --file.")

    all_lines = raw_text.splitlines()
    original_count = len(all_lines)

    # Honor --last N before anything else
    if last_n is not None:
        all_lines = all_lines[-last_n:]

    log_type  = _detect_log_type(all_lines)
    filtered  = _filter_lines(all_lines)

    # If filter strips everything (e.g. a fully healthy log), fall back to
    # last 30 raw lines so the AI can still say "no errors found"
    if not filtered:
        filtered = [l for l in all_lines[-30:] if not _NOISE_RE.search(l)]

    filtered, truncated = _apply_token_budget(filtered, max_tokens)

    return {
        "lines":      filtered,
        "log_type":   log_type,
        "line_count": original_count,
        "truncated":  truncated,
    }


# ── internals ─────────────────────────────────────────────────────────────────

def _detect_log_type(lines: list[str]) -> str:
    """
    Score each log type by how many of its patterns match across the first
    200 lines. Return the highest scorer, or "unknown".
    """
    sample = lines[:200]
    sample_text = "\n".join(sample)

    scores = {}
    for log_type, patterns in _TYPE_RES.items():
        score = sum(1 for p in patterns if p.search(sample_text))
        if score:
            scores[log_type] = score

    if not scores:
        return "unknown"

    return max(scores, key=scores.__getitem__)


def _filter_lines(lines: list[str]) -> list[str]:
    """
    Keep lines that:
      - match at least one error/warning pattern
      - are not pure noise
    Also keep up to 1 line of context after each matching line (the next
    line often contains the actual error message or stack frame).
    """
    kept    = []
    keep_next = False   # context carry-forward flag

    for line in lines:
        if _NOISE_RE.search(line):
            keep_next = False
            continue

        if keep_next:
            kept.append(line)
            keep_next = False
            continue

        if _ERROR_RE.search(line):
            kept.append(line)
            keep_next = True   # grab the line after too

    return kept


def _apply_token_budget(lines: list[str], max_tokens: int) -> tuple[list[str], bool]:
    """
    Rough token budget: 1 token ≈ 4 chars.
    If the filtered lines exceed the budget, keep the LAST N lines
    (most recent errors are more useful than old ones).
    Returns (lines, truncated_bool).
    """
    char_budget = max_tokens * 4
    total_chars = sum(len(l) for l in lines)

    if total_chars <= char_budget:
        return lines, False

    # Walk backwards, accumulating lines until budget is full
    kept = []
    chars = 0
    for line in reversed(lines):
        if chars + len(line) > char_budget:
            break
        kept.append(line)
        chars += len(line)

    return list(reversed(kept)), True


# ── custom exceptions ─────────────────────────────────────────────────────────

class ExplainLogError(Exception):
    pass

class EmptyLogError(ExplainLogError):
    pass


# ── quick test (run directly: python parser.py) ───────────────────────────────

if __name__ == "__main__":
    sample = """
Apr 03 03:40:11 systemd[1]: Starting PostgreSQL Database Server...
Apr 03 03:40:11 systemd[1]: Started PostgreSQL Database Server.
Apr 03 03:41:12 kernel: Out of memory: Killed process 1842 (postgres) score 920 or sacrifice child
Apr 03 03:41:12 kernel: oom_reaper: reaped process 1842 (postgres), now anon-rss:0kB
Apr 03 03:41:13 systemd[1]: postgresql.service: Main process exited, code=killed, status=9/KILL
Apr 03 03:41:13 systemd[1]: postgresql.service: Failed with result 'oom-kill'.
Apr 03 03:41:13 systemd[1]: Failed to start PostgreSQL Database Server.
Apr 03 03:41:14 systemd[1]: Reached target Multi-User System.
"""

    import json
    result = preprocess(sample)
    print(json.dumps(result, indent=2))