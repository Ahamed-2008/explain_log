# explain-log

A CLI tool that takes system or application logs as input and outputs a clear diagnosis and actionable fixes using AI.

---

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/Ahamed-2008/explain-log.git
cd explain-log
```

### 2. Create a virtual environment

**Linux / macOS**
```bash
python -m venv venv
source venv/bin/activate
```

**Windows**
```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install the tool
```bash
pip install -e .
```

### 4. First-time setup

Run explain-log once (or use `--change-api`). An interactive wizard asks you to choose a provider:

1. OpenAI
2. Ollama (local)
3. Anthropic
4. Gemini
5. Groq

Settings are saved to:

- **Linux / macOS:** `~/.config/explain-log/config.json`
- **Windows:** `%APPDATA%\explain-log\config.json`

### 5. Set your API key

API keys are read from environment variables only (never stored on disk).

| Provider | Environment variable |
|----------|---------------------|
| OpenAI | `OPENAI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |
| Gemini | `GEMINI_API_KEY` |
| Groq | `GROQ_API_KEY` |
| Ollama | none (optional: `OLLAMA_BASE_URL`) |

**Linux / macOS**
```bash
export OPENAI_API_KEY=your_key_here
```

**Windows (PowerShell)**
```powershell
$env:OPENAI_API_KEY="your_key_here"
```

### 6. Change provider later

```bash
explain-log --change-api
```

---

## Usage

### Analyze a log file

**Linux / macOS**
```bash
explain-log --file samples/python_error.log
```

**Windows**
```bash
explain-log --file samples\python_error.log
```

### Pipe logs directly

**Linux / macOS**
```bash
cat app.log | explain-log
journalctl -n 200 | explain-log
journalctl -u nginx | explain-log
```

**Windows (PowerShell)**
```powershell
Get-Content app.log | explain-log
```

### Analyze last N lines of a log
```bash
explain-log --file app.log --last 50
```

### Save a report
```bash
explain-log --file app.log --save report.md
```

### Output as JSON
```bash
explain-log --file app.log --format json
```

---

## Features

- Reads logs from a file or stdin
- Auto-detects log type (nginx, systemd, python, kernel, docker, postgres, apache, ssh)
- Filters out noise and focuses on ERROR and WARN lines
- Supports OpenAI, Anthropic, Gemini, Groq, and local Ollama
- Outputs a clear summary and actionable fixes in the terminal
- Supports terminal, JSON, and markdown output formats

---

## Project Structure
```
explain-log/
├── explain_log/
│   ├── ai.py
│   ├── cli.py
│   ├── config.py
│   ├── formatter.py
│   └── parser.py
├── samples/
│   ├── git_error.log
│   ├── python_error.log
│   └── system_error.log
└── pyproject.toml
```

---

## Requirements

- Python 3.13+
- API key for your chosen cloud provider, or a running [Ollama](https://ollama.com) instance for local use
