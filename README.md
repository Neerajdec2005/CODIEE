# Repo Deep Dive Explainer

Web app for exploring a GitHub repository and generating line-by-line explanations.

## What it does

- Clone a GitHub repo and build a file tree
- Browse files and show line numbers
- Generate a fast, heuristic line-by-line explanation for any file

## Run locally

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install fastapi uvicorn
uvicorn app:app --reload
```

Open `http://127.0.0.1:8000`.

## Notes

- The explainer uses simple heuristics for now and is designed to be swapped with an LLM pipeline.
- Large files are capped at 200 KB for deep dive explanations.
