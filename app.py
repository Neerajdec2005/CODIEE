import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPOS_DIR = DATA_DIR / "repos"
INDEX_FILE = DATA_DIR / "repos.json"
EXPLANATIONS_DIR = DATA_DIR / "explanations"

MAX_FILE_SIZE = 200_000
EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    "target",
    "out",
    ".cache",
    ".pytest_cache",
}

LANGUAGE_MAP = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".java": "Java",
    ".cs": "C#",
    ".rs": "Rust",
    ".cpp": "C++",
    ".c": "C",
    ".html": "HTML",
    ".css": "CSS",
    ".json": "JSON",
    ".md": "Markdown",
}

DATA_DIR.mkdir(parents=True, exist_ok=True)
REPOS_DIR.mkdir(parents=True, exist_ok=True)
EXPLANATIONS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Repo Deep Dive Explainer")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def load_index() -> Dict[str, Dict]:
    if not INDEX_FILE.exists():
        return {}
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_index(index: Dict[str, Dict]) -> None:
    INDEX_FILE.write_text(json.dumps(index, indent=2), encoding="utf-8")


def load_repo_state(repo_id: str) -> Dict:
    state_file = DATA_DIR / f"{repo_id}.state.json"
    if not state_file.exists():
        return {
            "repo_id": repo_id,
            "status": "pending",
            "processed": 0,
            "total": 0,
            "current_file": "",
            "updated_at": int(time.time()),
        }
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "repo_id": repo_id,
            "status": "error",
            "processed": 0,
            "total": 0,
            "current_file": "",
            "updated_at": int(time.time()),
        }


def save_repo_state(repo_id: str, state: Dict) -> None:
    state["updated_at"] = int(time.time())
    state_file = DATA_DIR / f"{repo_id}.state.json"
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


def create_repo_id(git_url: str) -> str:
    seed = f"{git_url}-{time.time()}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]


def detect_language(path: Path) -> str:
    return LANGUAGE_MAP.get(path.suffix.lower(), "Unknown")


def safe_join(root: Path, rel_path: str) -> Path:
    target = (root / rel_path).resolve()
    if not str(target).startswith(str(root.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    return target


def build_file_tree(root: Path, base: Optional[Path] = None) -> List[Dict]:
    if base is None:
        base = root
    entries = []
    for item in sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if item.name in EXCLUDE_DIRS:
            continue
        rel_path = str(item.relative_to(base)).replace("\\", "/")
        if item.is_dir():
            entries.append(
                {
                    "type": "dir",
                    "name": item.name,
                    "path": rel_path,
                    "children": build_file_tree(item, base),
                }
            )
        else:
            entries.append(
                {
                    "type": "file",
                    "name": item.name,
                    "path": rel_path,
                    "size": item.stat().st_size,
                    "language": detect_language(item),
                }
            )
    return entries


def collect_language_stats(root: Path) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            language = detect_language(path)
            counts[language] = counts.get(language, 0) + 1
    return counts


def file_overview(path: Path) -> Dict:
    content = path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    ext = path.suffix.lower()
    functions: List[str] = []
    classes: List[str] = []

    if ext == ".py":
        functions = re.findall(r"^def\s+([a-zA-Z_][\w]*)", content, re.MULTILINE)
        classes = re.findall(r"^class\s+([a-zA-Z_][\w]*)", content, re.MULTILINE)
    elif ext in {".js", ".ts", ".tsx", ".jsx"}:
        functions = re.findall(r"function\s+([a-zA-Z_][\w]*)", content)
        classes = re.findall(r"class\s+([a-zA-Z_][\w]*)", content)

    return {
        "path": str(path),
        "line_count": len(lines),
        "language": detect_language(path),
        "functions": functions[:20],
        "classes": classes[:20],
    }


def explain_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return "Blank line for spacing and readability."
    if stripped.startswith("#") or stripped.startswith("//"):
        return "Comment providing context or intent."
    if re.match(r"^import\s+", stripped) or re.match(r"^from\s+.+\s+import\s+", stripped):
        return "Imports a dependency needed in this file."
    if re.match(r"^class\s+", stripped):
        return "Defines a class type used in this module."
    if re.match(r"^def\s+", stripped) or re.match(r"^function\s+", stripped):
        return "Defines a function for reuse in this module."
    if "=" in stripped:
        return "Assigns a value to a name for later use."
    if stripped.endswith(":"):
        return "Starts a new block or scope."
    if stripped.startswith("return "):
        return "Returns a value from the current function."
    return "Performs a small step in the current flow."


def explain_file(path: Path) -> Dict:
    if path.stat().st_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large for deep dive")
    content = path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    explanations = []
    for idx, line in enumerate(lines, start=1):
        explanations.append(
            {
                "line": idx,
                "content": line,
                "explanation": explain_line(line),
            }
        )
    return {
        "overview": file_overview(path),
        "lines": explanations,
    }


def enumerate_files(root: Path) -> List[str]:
    files: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            rel_path = str(path.relative_to(root)).replace("\\", "/")
            files.append(rel_path)
    return sorted(files)


def explanation_cache_path(repo_id: str, rel_path: str) -> Path:
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", rel_path)
    return EXPLANATIONS_DIR / f"{repo_id}__{safe_name}.json"


def build_repo_explanations(repo_id: str) -> None:
    index = load_index()
    if repo_id not in index:
        return
    repo_path = Path(index[repo_id]["path"])
    file_list = enumerate_files(repo_path)
    state = {
        "repo_id": repo_id,
        "status": "running",
        "processed": 0,
        "total": len(file_list),
        "current_file": "",
        "updated_at": int(time.time()),
    }
    save_repo_state(repo_id, state)
    for rel_path in file_list:
        state["current_file"] = rel_path
        save_repo_state(repo_id, state)
        target = safe_join(repo_path, rel_path)
        if not target.exists() or target.is_dir():
            state["processed"] += 1
            continue
        if target.stat().st_size > MAX_FILE_SIZE:
            state["processed"] += 1
            continue
        try:
            explanation = explain_file(target)
            explanation["repo_id"] = repo_id
            explanation["path"] = rel_path
            explanation_cache_path(repo_id, rel_path).write_text(
                json.dumps(explanation, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass
        state["processed"] += 1
    state["status"] = "completed"
    state["current_file"] = ""
    save_repo_state(repo_id, state)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/repos")
async def list_repos():
    index = load_index()
    return {"repos": list(index.values())}


@app.post("/api/repos")
async def add_repo(payload: Dict, background_tasks: BackgroundTasks):
    git_url = payload.get("git_url", "").strip()
    if not git_url:
        raise HTTPException(status_code=400, detail="git_url required")

    repo_id = create_repo_id(git_url)
    repo_path = REPOS_DIR / repo_id

    result = subprocess.run(
        ["git", "clone", "--depth", "1", git_url, str(repo_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=result.stderr.strip() or "Clone failed")

    tree = build_file_tree(repo_path)
    language_stats = collect_language_stats(repo_path)

    index = load_index()
    record = {
        "id": repo_id,
        "git_url": git_url,
        "created_at": int(time.time()),
        "path": str(repo_path),
        "language_stats": language_stats,
        "file_count": sum(language_stats.values()),
    }
    index[repo_id] = record
    save_index(index)

    (DATA_DIR / f"{repo_id}.tree.json").write_text(
        json.dumps(tree, indent=2),
        encoding="utf-8",
    )

    save_repo_state(
        repo_id,
        {
            "repo_id": repo_id,
            "status": "queued",
            "processed": 0,
            "total": 0,
            "current_file": "",
            "updated_at": int(time.time()),
        },
    )
    background_tasks.add_task(build_repo_explanations, repo_id)

    return record


@app.get("/api/repos/{repo_id}")
async def get_repo(repo_id: str):
    index = load_index()
    if repo_id not in index:
        raise HTTPException(status_code=404, detail="Repo not found")
    return index[repo_id]


@app.get("/api/repos/{repo_id}/tree")
async def get_tree(repo_id: str):
    tree_file = DATA_DIR / f"{repo_id}.tree.json"
    if not tree_file.exists():
        raise HTTPException(status_code=404, detail="Tree not found")
    return JSONResponse(content=json.loads(tree_file.read_text(encoding="utf-8")))


@app.get("/api/repos/{repo_id}/status")
async def get_status(repo_id: str):
    index = load_index()
    if repo_id not in index:
        raise HTTPException(status_code=404, detail="Repo not found")
    return load_repo_state(repo_id)


@app.get("/api/repos/{repo_id}/file")
async def get_file(repo_id: str, path: str = Query("")):
    index = load_index()
    if repo_id not in index:
        raise HTTPException(status_code=404, detail="Repo not found")
    repo_path = Path(index[repo_id]["path"])
    target = safe_join(repo_path, path)
    if not target.exists() or target.is_dir():
        raise HTTPException(status_code=404, detail="File not found")
    if target.stat().st_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large to load")
    content = target.read_text(encoding="utf-8", errors="replace")
    return {"path": path, "content": content}


@app.get("/api/repos/{repo_id}/explain")
async def get_explanation(repo_id: str, path: str = Query("")):
    index = load_index()
    if repo_id not in index:
        raise HTTPException(status_code=404, detail="Repo not found")
    repo_path = Path(index[repo_id]["path"])
    target = safe_join(repo_path, path)
    if not target.exists() or target.is_dir():
        raise HTTPException(status_code=404, detail="File not found")
    cached = explanation_cache_path(repo_id, path)
    if cached.exists():
        return JSONResponse(content=json.loads(cached.read_text(encoding="utf-8")))
    explanation = explain_file(target)
    explanation["repo_id"] = repo_id
    explanation["path"] = path
    cached.write_text(json.dumps(explanation, indent=2), encoding="utf-8")
    return explanation
