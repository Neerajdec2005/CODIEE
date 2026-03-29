# CODIEE

CODIEE is a Flask-based code explanation tool that helps users understand code line-by-line with LLM support, plus a separate architecture view rendered with Mermaid.

It is designed for practical learning and fast code comprehension:
- Analyze one line at a time
- Navigate with Previous/Next across non-empty lines
- Generate architecture diagrams in a separate page
- Show rich explanation formatting (including markdown tables)

## Features

- Line-by-line explanation pipeline
  - What the line is
  - Part-by-part breakdown
  - Why it matters in context
  - Where the concept comes from
- Single-line mode by line number to reduce latency and token usage
- Architecture view in a separate screen
- Mermaid diagram rendering with normalization for escaped newlines
- Persistent architecture snapshots written to build output files
- Sprite-based interactive assistant UI
- Rate-limit-aware LLM fallback strategy

## Tech Stack

- Backend: Flask
- LLM: LangChain + Groq
- Frontend: HTML, CSS, JavaScript
- Diagram: Mermaid

## Project Structure

- app.py: Flask routes and API endpoints
- agents.py: Multi-agent analysis pipeline
- llm_client.py: LLM integration and fallback handling
- templates/editor.html: Main editor UI
- templates/architecture.html: Architecture view UI
- static/image/: Sprite animation frames used by UI
- build/: Generated architecture artifacts

## Prerequisites

- Python 3.10+
- A Groq API key
- Optional: uv for environment and execution convenience

## Installation

### Option A: Using uv (recommended)

1. Install dependencies:

```bash
uv pip install -r requirements.txt
```

2. Create environment file:

```bash
cp .env.example .env
```

If .env.example does not exist yet, create .env manually as shown below in Configuration.

3. Run the app:

```bash
uv run python app.py
```

### Option B: Using venv + pip

1. Create and activate virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run:

```bash
python app.py
```

## Configuration

Create a .env file in project root with:

```env
GPT_OSS=your_groq_api_key_here
```

Notes:
- The app reads GPT_OSS for LLM access.
- LLM model selection and fallback are handled in llm_client.py.

## Running the App

Default local URL:

- http://localhost:5001

Main pages:
- Editor: /
- Architecture: /architecture

## How to Use

1. Open the editor page.
2. Paste code or upload a file.
3. Click Analyze (in the explanation box) to explain the selected line.
4. Use Previous/Next to move through non-empty lines.
5. Open Architecture to view diagram and layers.

## API Endpoints

### POST /api/analyze

Analyzes code using the multi-agent pipeline.

Single-line mode:
- Provide line_number to analyze only that line.

Example request:

```json
{
  "code": "import os\nprint('x')",
  "filename": "sample.py",
  "line_number": 1
}
```

### POST /api/analyze-file

Form upload endpoint.
- Field name: code_file

### GET /api/architecture-latest

Returns latest persisted architecture JSON and generated file names.

## Architecture Artifacts

Generated under build/:
- latest_architecture.json
- latest_architecture.mmd

These files are runtime outputs and can be regenerated.

## Troubleshooting

### 1) Port already in use (5001)

If startup fails due to port conflicts, stop existing process and rerun:

```bash
pkill -f "uv run python app.py"
uv run python app.py
```

### 2) LLM errors or empty explanations

- Verify .env has valid GPT_OSS key.
- Check API quota and model availability.
- Retry with shorter input.

### 3) Mermaid parse errors in architecture view

The app normalizes escaped newlines before rendering. If you still see errors, rerun analysis and refresh architecture page.

## Development Notes

- Use .gitignore to keep local, generated, test, and debug artifacts out of commits.
- Keep static/image folder: it is required for sprite UI rendering.

## Production Considerations

For production deployment:
- Disable Flask debug mode
- Run behind a production WSGI server (for example, gunicorn)
- Store secrets using a secure secret manager
- Add request rate limiting and error monitoring
