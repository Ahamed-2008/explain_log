# explain-log

A CLI tool that takes system or application logs as input and outputs a clear diagnosis and actionable fixes using AI.

---

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/Ahamed-2008/explain-log.git
cd explain-log
cd explain_log
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

### 4. Set your Groq API key

**Linux / macOS**
```bash
export GROQ_API_KEY=your_api_key_here
```

**Windows (Command Prompt)**
```bash
set GROQ_API_KEY=your_api_key_here
```

**Windows (PowerShell)**
```powershell
$env:GROQ_API_KEY="your_api_key_here"
```

Get a free key at: https://console.groq.com/keys

### 5. Set LLM
**Linux / macOS**
```bash
export EXPLAIN_LOG_MODEL=your_model
```
**Windows (Command Prompt)**
```bash
set EXPLAIN_LOG_MODEL=yout_model
```
**Windows (PowerShell)**
```powershell
$env:EXPLAIN_LOG_MODEL="your_model"
```

The Default Model is llama-3.3-70b-versatile

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
- Sends logs to Groq AI (llama-3.3-70b-versatile) for diagnosis
- Outputs a clear summary and actionable fixes in the terminal
- Supports terminal, JSON, and markdown output formats

---

## Project Structure
explain-log/
.
├── explain_log/
│   ├── __init__.py
│   ├── ai.py
│   ├── cli.py
│   ├── formatter.py
│   └── parser.py
├── samples/
│   ├── git_error.log
│   ├── python_error.log
│   └── system_error.log
└── pyproject.toml

---

## Requirements

- Python 3.13+
- Groq API key (free at https://console.groq.com/keys)
