import argparse
import sys
import os

from explain_log.parser import preprocess, EmptyLogError
from explain_log.ai     import analyze, APIError, RateLimitError

try:
    from rich.console import Console
    from rich.panel   import Panel
    from rich.text    import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


console = Console(stderr=True)   # progress/errors → stderr, clean stdout for --format json


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    args = _build_parser().parse_args()

    # ── read input ────────────────────────────────────────────────────────────
    try:
        raw = _read_input(args)
    except FileNotFoundError as e:
        _die(f"File not found: {e}")
    except IsADirectoryError:
        _die(f"'{args.file}' is a directory, not a log file.")

    # ── parse ─────────────────────────────────────────────────────────────────
    try:
        parsed = preprocess(
            raw_text   = raw,
            last_n     = args.last,
            max_tokens = 3000,
        )
    except EmptyLogError as e:
        _die(str(e))

    # override auto-detected log type if user passed --log-type
    if args.log_type:
        parsed["log_type"] = args.log_type 

    # ── show parse summary on stderr so user knows what's being sent ──────────
    if not args.quiet:
        console.print(
            f"[dim]  log type:[/dim] [cyan]{parsed['log_type']}[/cyan]  "
            f"[dim]lines:[/dim] [cyan]{len(parsed['lines'])}[/cyan] / {parsed['line_count']}"
            + (" [yellow](truncated)[/yellow]" if parsed['truncated'] else ""),
        )

    # ── analyze ───────────────────────────────────────────────────────────────
    try:
        result = analyze(parsed, stream=not args.no_stream)
    except EnvironmentError as e:
        _die(str(e))
    except RateLimitError as e:
        _die(str(e), code=429)
    except APIError as e:
        _die(str(e))
    except ValueError as e:
        _die(f"Failed to parse model response:\n{e}")

    # ── output ────────────────────────────────────────────────────────────────
    fmt = args.format.lower()

    if fmt == "json":
        import json
        print(json.dumps(result, indent=2))

    elif fmt == "markdown":
        md = _render_markdown(result, parsed)
        if args.save:
            _save_file(args.save, md)
        else:
            print(md)

    else:  # terminal (default)
        if RICH_AVAILABLE:
            _render_rich(result, parsed)
        else:
            _render_plain(result, parsed)
        if args.save:
            _save_file(args.save, _render_markdown(result, parsed))
            console.print(f"[dim]  saved →[/dim] {args.save}")


# ── argument parser ───────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog        = "explain-log",
        description = "Pipe any log into this tool and get an AI-powered diagnosis.",
        epilog      = (
            "examples:\n"
            "  cat /var/log/syslog | explain-log\n"
            "  explain-log --file nginx.log\n"
            "  journalctl -n 200 | explain-log --last 50\n"
            "  explain-log --file app.log --format json | jq\n"
            "  explain-log --file crash.log --save report.md"
        ),
        formatter_class = argparse.RawDescriptionHelpFormatter,
    )

    # input
    input_group = p.add_mutually_exclusive_group()
    input_group.add_argument(
        "--file", "-f",
        metavar = "PATH",
        help    = "path to log file (default: read from stdin)",
    )

    # filtering
    p.add_argument(
        "--last", "-n",
        type    = int,
        metavar = "N",
        help    = "only analyze the last N lines",
    )
    p.add_argument(
        "--log-type",
        metavar = "TYPE",
        choices = ["nginx", "systemd", "python", "kernel", "apache", "postgres", "ssh", "docker", "unknown"],
        help    = "override auto-detected log type (hint sent to AI)",
    )

    # output
    p.add_argument(
        "--format",
        default = "terminal",
        choices = ["terminal", "json", "markdown"],
        help    = "output format (default: terminal)",
    )
    p.add_argument(
        "--save", "-o",
        metavar = "PATH",
        help    = "save markdown report to file (works with any --format)",
    )

    # behaviour
    p.add_argument(
        "--no-stream",
        action  = "store_true",
        help    = "disable streaming (wait for full response before printing)",
    )
    p.add_argument(
        "--quiet", "-q",
        action  = "store_true",
        help    = "suppress progress output on stderr",
    )

    return p


# ── input reading ─────────────────────────────────────────────────────────────

def _read_input(args) -> str:
    if args.file:
        with open(args.file, "r", errors="replace") as f:
            return f.read()

    # stdin — check it's not a bare terminal (user forgot to pipe)
    if sys.stdin.isatty():
        _die(
            "No input. Pipe a log file or use --file:\n\n"
            "  cat /var/log/syslog | explain-log\n"
            "  explain-log --file app.log"
        )

    return sys.stdin.read()


# ── renderers ─────────────────────────────────────────────────────────────────

_SEVERITY_COLOR = {
    "critical": "red",
    "warn":     "yellow",
    "info":     "green",
}

def _render_rich(result: dict, parsed: dict):
    severity = result["severity"]
    color    = _SEVERITY_COLOR.get(severity, "white")

    title = Text()
    title.append("● ", style=f"bold {color}")
    title.append(severity.upper(), style=f"bold {color}")
    title.append(f"  ·  {parsed['log_type']} log", style="dim")

    body = Text()
    body.append("Diagnosis\n", style="bold white")
    body.append(result["diagnosis"] + "\n", style="white")

    if result["fixes"]:
        body.append("\nSuggested fixes\n", style="bold white")
        for i, fix in enumerate(result["fixes"], 1):
            body.append(f"  {i}. ", style="dim")
            body.append(fix + "\n", style="white")

    console_out = Console()   # stdout console for the actual result
    console_out.print(Panel(body, title=title, border_style=color, padding=(1, 2)))


def _render_plain(result: dict, parsed: dict):
    """Fallback when rich isn't installed."""
    sep = "─" * 60
    print(sep)
    print(f"  SEVERITY : {result['severity'].upper()}")
    print(f"  LOG TYPE : {parsed['log_type']}")
    print(sep)
    print(f"\nDIAGNOSIS\n{result['diagnosis']}\n")
    if result["fixes"]:
        print("SUGGESTED FIXES")
        for i, fix in enumerate(result["fixes"], 1):
            print(f"  {i}. {fix}")
    print(sep)


def _render_markdown(result: dict, parsed: dict) -> str:
    lines = [
        f"# explain-log report",
        f"",
        f"**Severity:** `{result['severity'].upper()}`  ",
        f"**Log type:** `{parsed['log_type']}`  ",
        f"**Lines analyzed:** {len(parsed['lines'])} / {parsed['line_count']}",
        f"",
        f"## Diagnosis",
        f"",
        result["diagnosis"],
        f"",
    ]
    if result["fixes"]:
        lines += ["## Suggested fixes", ""]
        for i, fix in enumerate(result["fixes"], 1):
            lines.append(f"{i}. {fix}")
    return "\n".join(lines)


# ── helpers ───────────────────────────────────────────────────────────────────

def _save_file(path: str, content: str):
    with open(path, "w") as f:
        f.write(content)


def _die(msg: str, code: int = 1):
    if RICH_AVAILABLE:
        Console(stderr=True).print(f"[red]error:[/red] {msg}")
    else:
        print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


if __name__ == "__main__":
    main()