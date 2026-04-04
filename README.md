# explain-log

A CLI tool that takes system or application logs as input and outputs a clear diagnosis and actionable fixes using Claude AI.

---

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/Ahamed-2008/explain-log.git
cd explain-log
```

### 2. Create a virtual environment
```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install the tool
```bash
pip install -e .
```

### 4. Set your Anthropic API key
```bash
set GROQ_API_KEY=your_api_key_here
```

---

## Usage

### Analyze a log file
```bash
explain-log --file samples/python_error.log
```

### Pipe logs directly
```bash
cat app.log | explain-log
```

### Analyze last N lines of a log
```bash
explain-log --file app.log --last 50
```

---

## Features

- Reads logs from a file or stdin
- Filters out noise and focuses on ERROR and WARN lines
- Sends logs to Claude AI for diagnosis
- Outputs a clear summary and actionable fixes in the terminal

---

## Project Structure
explain_log/
├── explain_log/
│   ├── cli.py        # handles CLI input
│   ├── parser.py     # filters and cleans logs
│   ├── ai.py         # sends logs to Claude AI
│   └── formatter.py  # formats output in terminal
├── samples/
│   ├── python_error.log
│   ├── git_error.log
│   └── system_error.log
└── pyproject.toml

---

## Requirements

- Python 3.13+
- Anthropic API key