import json
import os
import sys
from pathlib import Path

PROVIDERS = ("openai", "ollama", "anthropic", "gemini", "groq")

DEFAULT_MODELS = {
    "openai":    "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-20241022",
    "gemini":    "gemini-2.0-flash",
    "ollama":    "llama3",
    "groq":      "llama-3.3-70b-versatile",
}

# Legacy Gemini model IDs → current API names
GEMINI_MODEL_ALIASES = {
    "gemini-1.5-flash":      "gemini-2.0-flash",
    "gemini-1.5-flash-8b":   "gemini-2.0-flash",
    "gemini-1.5-flash-latest": "gemini-2.0-flash",
    "gemini-1.5-pro":        "gemini-2.0-flash",
    "gemini-1.5-pro-latest": "gemini-2.0-flash",
    "gemini-pro":            "gemini-2.0-flash",
}

API_KEY_ENV = {
    "openai":    "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini":    "GEMINI_API_KEY",
    "groq":      "GROQ_API_KEY",
}

API_KEY_HELP = {
    "openai": (
        "export OPENAI_API_KEY=your_key_here\n"
        "Get a key at: https://platform.openai.com/api-keys"
    ),
    "anthropic": (
        "export ANTHROPIC_API_KEY=your_key_here\n"
        "Get a key at: https://console.anthropic.com/settings/keys"
    ),
    "gemini": (
        "export GEMINI_API_KEY=your_key_here\n"
        "Get a key at: https://aistudio.google.com/apikey"
    ),
    "groq": (
        "export GROQ_API_KEY=your_key_here\n"
        "Get a free key at: https://console.groq.com/keys"
    ),
}

MENU_LABELS = [
    ("openai",    "OpenAI"),
    ("ollama",    "Ollama (local)"),
    ("anthropic", "Anthropic"),
    ("gemini",    "Gemini"),
    ("groq",      "Groq"),
]


def config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "explain-log" / "config.json"


def load_config() -> dict | None:
    path = config_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if data.get("provider") not in PROVIDERS:
        return None
    return data


def save_config(provider: str, model: str, base_url: str | None = None) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {"provider": provider, "model": model}
    if provider == "ollama" and base_url:
        data["base_url"] = base_url
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def run_setup_wizard() -> dict:
    print("\nexplain-log — choose your API provider\n")
    for i, (_, label) in enumerate(MENU_LABELS, 1):
        print(f"  {i}. {label}")
    print()

    valid = {str(i) for i in range(1, len(MENU_LABELS) + 1)}
    while True:
        choice = input(f"Enter choice [1-{len(MENU_LABELS)}]: ").strip()
        if choice in valid:
            provider = MENU_LABELS[int(choice) - 1][0]
            break
        print(f"  Invalid choice. Enter 1 through {len(MENU_LABELS)}.")

    default_model = DEFAULT_MODELS[provider]
    model_input = input(f"Model [{default_model}]: ").strip()
    model = model_input or default_model

    base_url = None
    if provider == "ollama":
        default_url = "http://localhost:11434"
        url_input = input(f"Ollama base URL [{default_url}]: ").strip()
        base_url = url_input or default_url

    cfg: dict = {"provider": provider, "model": model}
    if base_url:
        cfg["base_url"] = base_url

    save_config(provider, model, base_url)
    print(f"\nSaved → {config_path()}")
    print(f"  provider: {provider}")
    print(f"  model:    {model}")
    if base_url:
        print(f"  base_url: {base_url}")

    if provider != "ollama":
        ensure_api_key(provider)
    else:
        print("\nOllama needs no API key. Make sure Ollama is running locally.")

    print("\nSetup complete. Run explain-log with a log file to analyze.\n")
    return cfg


def normalize_api_key(key: str) -> str:
    """Strip whitespace and accidental 'Bearer ' prefix from pasted keys."""
    key = key.strip().strip('"').strip("'")
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    return key


def get_api_key(provider: str) -> str | None:
    env_var = API_KEY_ENV.get(provider)
    if not env_var:
        return None
    raw = os.environ.get(env_var)
    if not raw:
        return None
    normalized = normalize_api_key(raw)
    return normalized or None


def ensure_api_key(provider: str) -> None:
    if provider == "ollama":
        return
    env_var = API_KEY_ENV.get(provider)
    if not env_var:
        return
    if get_api_key(provider):
        return
    print(f"\nerror: {env_var} is not set or is empty.\n")
    print(API_KEY_HELP[provider])
    print("\nSet the variable in your shell, then retry.")
    sys.exit(1)
