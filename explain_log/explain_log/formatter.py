import json
from rich.console import Console
from rich.panel import Panel

console = Console()


# =========================
# ERROR CLASSES
# =========================

class ExplainLogError(Exception):
    pass


class EmptyLogError(ExplainLogError):
    pass


class APIError(ExplainLogError):
    pass


class TokenBudgetError(ExplainLogError):
    pass


# =========================
# MAIN FUNCTION
# =========================

def render(result: dict, fmt: str = "terminal", save_path: str = None):
    try:
        if not result:
            raise EmptyLogError("No analysis available")

        severity = result.get("severity", "info").lower()
        diagnosis = result.get("diagnosis", "No diagnosis available")
        fixes = result.get("fixes", [])

        # 🎨 Severity color
        color = (
            "red" if severity == "critical"
            else "yellow" if severity == "warn"
            else "green"
        )

        # =========================
        # JSON OUTPUT
        # =========================
        if fmt == "json":
            print(json.dumps(result, indent=2))
            return

        # =========================
        # MARKDOWN OUTPUT
        # =========================
        if fmt == "markdown":
            if not save_path:
                console.print("[red]❌ No save path provided[/red]")
                return

            with open(save_path, "w", encoding="utf-8") as f:
                f.write("# Log Analysis\n\n")
                f.write(f"## Severity\n{severity.upper()}\n\n")
                f.write(f"## Diagnosis\n{diagnosis}\n\n")
                f.write("## Fixes\n")

                if fixes:
                    for i, fix in enumerate(fixes, 1):
                        f.write(f"{i}. {fix}\n")
                else:
                    f.write("No fixes available\n")

            console.print(f"[green]✅ Report saved to {save_path}[/green]")
            return

        # =========================
        # TERMINAL OUTPUT
        # =========================
        console.rule("[bold cyan]🚀 explain-log AI Analysis")

        console.print(
            f"\n[bold {color}]🚨 Severity: {severity.upper()}[/bold {color}]\n")

        console.print(
            Panel(
                diagnosis,
                title="🔍 Diagnosis",
                border_style=color
            )
        )

        fixes_text = (
            "\n".join([f"{i}. {fix}" for i, fix in enumerate(fixes, 1)])
            if fixes else "No fixes available"
        )

        console.print(
            Panel(
                fixes_text,
                title="🔧 Suggested Fixes",
                border_style=color
            )
        )

    # =========================
    # ERROR HANDLING
    # =========================

    except EmptyLogError as e:
        console.print(f"[yellow]⚠ {e}[/yellow]")

    except APIError as e:
        console.print("[bold red]🚫 API Error[/bold red]")
        console.print(f"[yellow]{e}[/yellow]")
        console.print("[dim]Try again later or upgrade your API plan.[/dim]")

    except TokenBudgetError as e:
        console.print("[bold red]🚫 Token Limit Exceeded[/bold red]")
        console.print(f"[yellow]{e}[/yellow]")

    except Exception as e:
        console.print("[bold red]🚫 Unexpected Error[/bold red]")
        console.print(f"[yellow]{e}[/yellow]")


# =========================
# TEST BLOCK
# =========================

if __name__ == "__main__":
    sample = {
        "severity": "critical",
        "diagnosis": "Connection refused while connecting to backend server.",
        "fixes": [
            "Check if backend service is running",
            "Verify port configuration",
            "Restart the server"
        ]
    }

    render(sample, "terminal")
    render(sample, "json")
    render(sample, "markdown", "sample_report.md")
