from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llm_client import LLMService


PYTHON_LIBRARY_GUIDE: dict[str, dict[str, str]] = {
    "flask": {
        "what": "Flask is a lightweight Python web framework for routing HTTP requests and returning responses.",
        "example": "from flask import Flask\napp = Flask(__name__)\n@app.route('/health')\ndef health():\n    return {'ok': True}",
        "other_uses": "Build REST APIs, render HTML templates, handle forms, and compose microservices.",
    },
    "os": {
        "what": "The os module provides operating-system interfaces such as environment variables and file path operations.",
        "example": "import os\nbase = os.getenv('APP_HOME', '/tmp')",
        "other_uses": "Manage paths, inspect directories, spawn subprocesses, and read process settings.",
    },
    "pygame": {
        "what": "pygame provides multimedia primitives for building games, rendering sprites, and handling input.",
        "example": "import pygame\npygame.init()\nscreen = pygame.display.set_mode((640, 480))",
        "other_uses": "2D animation, event loops, keyboard handling, audio playback, and educational simulations.",
    },
}


PYTHON_BUILTIN_GUIDE: dict[str, dict[str, str]] = {
    "print": {
        "what": "print outputs values to standard output.",
        "example": "print('Hello')",
        "other_uses": "Format values with sep/end, quick debugging, and CLI progress messages.",
    },
    "len": {
        "what": "len returns the number of items in a collection.",
        "example": "len([1, 2, 3])",
        "other_uses": "Validate non-empty input, loop boundaries, and size checks.",
    },
    "range": {
        "what": "range creates an immutable sequence of integers, commonly used in loops.",
        "example": "for i in range(3):\n    print(i)",
        "other_uses": "Index-based iteration, arithmetic progressions, and slicing helpers.",
    },
    "open": {
        "what": "open creates a file handle for reading or writing files.",
        "example": "with open('data.txt', 'r', encoding='utf-8') as f:\n    data = f.read()",
        "other_uses": "Log writing, JSON parsing, CSV handling, and config loading.",
    },
}


JS_LIBRARY_GUIDE: dict[str, dict[str, str]] = {
    "react": {
        "what": "React is a UI library for building component-based interfaces with state and props.",
        "example": "function App() { return <h1>Hello</h1>; }",
        "other_uses": "Dynamic dashboards, SPA routing, reusable design systems, and state-driven updates.",
    },
}


JS_BUILTIN_GUIDE: dict[str, dict[str, str]] = {
    "console.log": {
        "what": "console.log writes diagnostic output to the browser or runtime console.",
        "example": "console.log('value:', value)",
        "other_uses": "Inspect payloads, profile flow, and log intermediate values.",
    },
    "map": {
        "what": "Array.prototype.map transforms each array element and returns a new array.",
        "example": "const doubled = [1,2,3].map(n => n * 2);",
        "other_uses": "Project object lists, UI rendering loops, and normalization of API results.",
    },
    "filter": {
        "what": "Array.prototype.filter returns a new array containing elements that pass a condition.",
        "example": "const active = users.filter(u => u.active);",
        "other_uses": "Search filtering, validation pipelines, and feature-flagged lists.",
    },
}


@dataclass
class ParsedCode:
    language: str
    filename: str
    code: str
    lines: list[str]


def detect_language(filename: str, code: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".py"}:
        return "python"
    if suffix in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}:
        return "javascript"

    trimmed = code.lstrip()
    if "def " in code or "import " in code or "from " in code:
        return "python"
    if "function " in code or "const " in code or "=>" in code:
        return "javascript"
    if trimmed.startswith("<"):
        return "markup"
    return "text"


class CodeAnalysisAgent:
    def run(self, parsed: ParsedCode) -> dict[str, Any]:
        language = parsed.language
        lines = parsed.lines
        non_empty = [line for line in lines if line.strip()]

        analysis: dict[str, Any] = {
            "agent": "analysis-agent",
            "filename": parsed.filename,
            "language": language,
            "metrics": {
                "total_lines": len(lines),
                "non_empty_lines": len(non_empty),
                "comment_lines": self._comment_line_count(lines, language),
            },
            "imports": [],
            "functions": [],
            "classes": [],
            "configs": [],
            "important_keywords": [],
        }

        if language == "python":
            analysis.update(self._analyze_python(parsed.code))
        elif language == "javascript":
            analysis.update(self._analyze_javascript(parsed.code))

        analysis["summary"] = self._build_summary(analysis)
        return analysis

    def _comment_line_count(self, lines: list[str], language: str) -> int:
        comment_markers = {
            "python": "#",
            "javascript": "//",
        }
        marker = comment_markers.get(language)
        if not marker:
            return 0
        return sum(1 for line in lines if line.strip().startswith(marker))

    def _analyze_python(self, code: str) -> dict[str, Any]:
        imports: list[str] = []
        functions: dict[str, dict[str, Any]] = {}
        classes: list[str] = []
        configs: list[str] = []
        important_keywords: list[str] = []

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {
                "imports": imports,
                "functions": list(functions.keys()),
                "classes": classes,
                "configs": configs,
                "important_keywords": important_keywords,
                "summary": "Code has syntax issues, so analysis used a safe fallback mode.",
            }

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imported = ", ".join(alias.name for alias in node.names)
                imports.append(f"{module}: {imported}")
            elif isinstance(node, ast.FunctionDef):
                params = [arg.arg for arg in node.args.args]
                # Simple computation detection
                computations = []
                for stmt in node.body:
                    if isinstance(stmt, ast.Assign):
                        computations.append("assignment")
                    elif isinstance(stmt, ast.Return):
                        computations.append("return")
                    elif isinstance(stmt, ast.Call):
                        computations.append("function call")
                functions[node.name] = {
                    "params": params,
                    "computations": list(set(computations))
                }
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, ast.Call):
                name = self._node_name(node.func)
                if name in {"Flask", "app.run", "render_template", "pygame.display.set_mode"}:
                    important_keywords.append(name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        configs.append(target.id)

        return {
            "imports": sorted(set(imports)),
            "functions": list(functions.keys()),
            "function_details": functions,
            "classes": sorted(set(classes)),
            "configs": sorted(set(configs)),
            "important_keywords": sorted(set(important_keywords)),
        }

    def _node_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            left = self._node_name(node.value)
            return f"{left}.{node.attr}" if left else node.attr
        return ""

    def _analyze_javascript(self, code: str) -> dict[str, Any]:
        imports = re.findall(r"^\s*import\s+.+?from\s+['\"](.+?)['\"]", code, re.MULTILINE)
        require_imports = re.findall(r"require\(['\"](.+?)['\"]\)", code)
        functions = re.findall(r"function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", code)
        arrow_assigned = re.findall(r"(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\(?.*?\)?\s*=>", code)
        classes = re.findall(r"class\s+([A-Za-z_][A-Za-z0-9_]*)", code)

        configs = []
        if "process.env" in code:
            configs.append("process.env")
        if "module.exports" in code:
            configs.append("module.exports")

        important = []
        for keyword in ["fetch", "Promise", "console.log", "map", "filter"]:
            if keyword in code:
                important.append(keyword)

        return {
            "imports": sorted(set(imports + require_imports)),
            "functions": sorted(set(functions + arrow_assigned)),
            "classes": sorted(set(classes)),
            "configs": sorted(set(configs)),
            "important_keywords": sorted(set(important)),
        }

    def _build_summary(self, analysis: dict[str, Any]) -> str:
        parts = [
            f"Detected language: {analysis['language']}",
            f"Imports: {len(analysis['imports'])}",
            f"Functions: {len(analysis['functions'])}",
            f"Classes: {len(analysis['classes'])}",
        ]
        return " | ".join(parts)


class ArchitectureAgent:
    def __init__(self, llm: LLMService) -> None:
        self.llm = llm

    def run(self, parsed: ParsedCode, analysis: dict[str, Any], use_better_view: bool = False) -> dict[str, Any]:
        imports = analysis.get("imports", [])
        functions = analysis.get("functions", [])
        classes = analysis.get("classes", [])
        configs = analysis.get("configs", [])
        keywords = analysis.get("important_keywords", [])

        layers = [
            {
                "id": "input",
                "title": "Input Layer",
                "detail": (
                    f"Receives source file {parsed.filename}, normalizes line endings, and prepares language-specific parsing. "
                    f"Key normalization keywords: splitlines, strip, suffix-detection."
                ),
            },
            {
                "id": "analysis",
                "title": "Code Analysis Agent",
                "detail": (
                    "Extracts imports, functions, classes, configs, and operational keywords. "
                    f"Imports: {', '.join(imports) if imports else 'none detected'}."
                ),
            },
            {
                "id": "architecture",
                "title": "Architecture Agent",
                "detail": (
                    "Builds structural components and relationships, including runtime entrypoints and configuration surfaces. "
                    f"Configs: {', '.join(configs) if configs else 'none detected'}; Keywords: {', '.join(keywords) if keywords else 'none detected'}."
                ),
            },
            {
                "id": "line",
                "title": "Line Explanation Agent",
                "detail": (
                    "Creates line-level semantic commentary including built-in or library descriptions, usage examples, "
                    "and alternative patterns for practical reuse."
                ),
            },
            {
                "id": "output",
                "title": "Presentation Layer",
                "detail": (
                    "Shows a step-through UI with next/previous navigation, architecture diagram rendering, and analysis summaries. "
                    f"Surface functions: {', '.join(functions) if functions else 'none'}; classes: {', '.join(classes) if classes else 'none'}."
                ),
            },
        ]

        mermaid = self._build_mermaid(layers)
        architecture_result = {
            "agent": "architecture-agent",
            "layers": layers,
            "diagram_mermaid": mermaid,
            "view_mode": "standard",
            "notes": [],
        }

        if use_better_view and self.llm.enabled:
            better = self.llm.build_better_architecture(
                filename=parsed.filename,
                analysis=analysis,
                code=parsed.code,
            )
            if better:
                architecture_result = {
                    "agent": "architecture-agent",
                    "layers": better["layers"],
                    "diagram_mermaid": better["diagram_mermaid"],
                    "view_mode": "better-llm",
                    "notes": better.get("notes", []),
                }
            else:
                architecture_result["notes"].append(
                    "Better architecture generation failed; showing standard architecture view."
                )

        return architecture_result

    def _build_mermaid(self, layers: list[dict[str, str]]) -> str:
        def safe(text: str) -> str:
            return text.replace('"', "'")

        lines = ["flowchart TD"]
        for layer in layers:
            node_label = f"{layer['title']}\\n{safe(layer['detail'])}"
            lines.append(f"    {layer['id']}[\"{node_label}\"]")

        lines.extend(
            [
                "    input --> analysis",
                "    analysis --> architecture",
                "    analysis --> line",
                "    architecture --> output",
                "    line --> output",
            ]
        )
        return "\n".join(lines)


class LineExplanationAgent:
    def __init__(self, llm: LLMService) -> None:
        self.llm = llm

    def run(self, parsed: ParsedCode, analysis: dict[str, Any], use_llm: bool = True) -> dict[str, Any]:
        language = parsed.language
        explanations: list[dict[str, Any]] = []
        import_roots = self._import_roots(analysis.get("imports", []), language)

        llm_explanations_by_line: dict[int, dict[str, Any]] = {}
        if use_llm and self.llm.enabled:
            llm_explanations = self.llm.explain_lines(language, parsed.filename, parsed.lines)
            if llm_explanations:
                for item in llm_explanations:
                    line_number = item.get("line")
                    if isinstance(line_number, int):
                        llm_explanations_by_line[line_number] = item

        for idx, raw_line in enumerate(parsed.lines, start=1):
            line = raw_line.rstrip("\n")
            stripped = line.strip()

            if idx in llm_explanations_by_line:
                llm_item = llm_explanations_by_line[idx]
                explanations.append(
                    {
                        "line": idx,
                        "code": line,
                        "what_is_this_line": str(llm_item.get("what_is_this_line", "This line contributes to the program flow.")),
                        "breakdown": str(llm_item.get("breakdown", "N/A")),
                        "related_to_code": str(llm_item.get("related_to_code", "Use similar patterns in related contexts.")),
                        "where_from": str(llm_item.get("where_from", "None")),
                    }
                )
                continue

            if not stripped:
                explanations.append(
                    {
                        "line": idx,
                        "code": line,
                        "what_it_does": "This is an empty line used for readability and logical grouping.",
                        "library_or_builtin": "None",
                        "example": "N/A",
                        "other_uses": "Spacing helps maintainability and visual scanning.",
                    }
                )
                continue

            entity = self._detect_entity(stripped, language, import_roots)
            guidance = self._entity_guidance(entity, language)

            explanations.append(
                {
                    "line": idx,
                    "code": line,
                    "what_it_does": self._line_summary(stripped, language),
                    "library_or_builtin": guidance["what"],
                    "example": guidance["example"],
                    "other_uses": guidance["other_uses"],
                }
            )

        return {
            "agent": "line-explanation-agent",
            "total_lines": len(parsed.lines),
            "explanations": explanations,
        }

    def _import_roots(self, imports: list[str], language: str) -> set[str]:
        roots = set()
        if language == "python":
            for item in imports:
                root = item.split(":", 1)[0].split(".")[0].strip()
                if root:
                    roots.add(root)
        elif language == "javascript":
            for item in imports:
                root = item.split("/")[0].strip()
                if root:
                    roots.add(root)
        return roots

    def _detect_entity(self, line: str, language: str, import_roots: set[str]) -> str:
        if language == "python":
            for name in sorted(PYTHON_BUILTIN_GUIDE.keys(), key=len, reverse=True):
                if re.search(rf"\b{name}\s*\(", line):
                    return name
            for root in import_roots:
                if re.search(rf"\b{re.escape(root)}\b", line):
                    return root
        elif language == "javascript":
            for name in sorted(JS_BUILTIN_GUIDE.keys(), key=len, reverse=True):
                if name in line:
                    return name
            for root in import_roots:
                if re.search(rf"\b{re.escape(root)}\b", line):
                    return root
        return "generic"

    def _entity_guidance(self, entity: str, language: str) -> dict[str, str]:
        if language == "python":
            if entity in PYTHON_BUILTIN_GUIDE:
                data = PYTHON_BUILTIN_GUIDE[entity]
                return {
                    "what": f"Built-in: {entity}. {data['what']}",
                    "example": data["example"],
                    "other_uses": data["other_uses"],
                }
            if entity in PYTHON_LIBRARY_GUIDE:
                data = PYTHON_LIBRARY_GUIDE[entity]
                return {
                    "what": f"Library: {entity}. {data['what']}",
                    "example": data["example"],
                    "other_uses": data["other_uses"],
                }
        elif language == "javascript":
            if entity in JS_BUILTIN_GUIDE:
                data = JS_BUILTIN_GUIDE[entity]
                return {
                    "what": f"Built-in API: {entity}. {data['what']}",
                    "example": data["example"],
                    "other_uses": data["other_uses"],
                }
            if entity in JS_LIBRARY_GUIDE:
                data = JS_LIBRARY_GUIDE[entity]
                return {
                    "what": f"Library: {entity}. {data['what']}",
                    "example": data["example"],
                    "other_uses": data["other_uses"],
                }

        return {
            "what": "No direct built-in or external library reference is detected in this line.",
            "example": "N/A",
            "other_uses": "Use this line's pattern as a structural template in related blocks.",
        }

    def _line_summary(self, line: str, language: str) -> str:
        if language == "python":
            if line.startswith("import ") or line.startswith("from "):
                return "This line imports dependencies so the file can use external modules or symbols."
            if line.startswith("def "):
                return "This line declares a function and defines a reusable behavior block."
            if line.startswith("class "):
                return "This line declares a class as a blueprint for objects and methods."
            if line.startswith("if __name__ == '__main__':"):
                return "This line ensures the following block runs only when this file is executed directly."
            if "=" in line and "==" not in line:
                return "This line assigns a value to a variable for later use."
            if line.startswith("return "):
                return "This line returns a value from the current function."
        elif language == "javascript":
            if line.startswith("import "):
                return "This line imports a module dependency for use in this file."
            if line.startswith("function "):
                return "This line declares a named function for reusable logic."
            if line.startswith("class "):
                return "This line declares a class for object-oriented structure."
            if "=>" in line:
                return "This line uses an arrow function, a concise function expression syntax."
            if line.startswith("return "):
                return "This line returns a value from the current function."

        return "This line contributes to the control flow or data setup of the program."


def run_multi_agent_pipeline(
    code: str,
    filename: str,
    use_llm: bool = True,
    use_better_architecture: bool = False,
) -> dict[str, Any]:
    parsed = ParsedCode(
        language=detect_language(filename, code),
        filename=filename,
        code=code,
        lines=code.splitlines(),
    )

    llm = LLMService()

    analysis_agent = CodeAnalysisAgent()
    architecture_agent = ArchitectureAgent(llm=llm)
    line_agent = LineExplanationAgent(llm=llm)

    analysis_result = analysis_agent.run(parsed)
    architecture_result = architecture_agent.run(
        parsed,
        analysis_result,
        use_better_view=use_better_architecture,
    )
    line_result = line_agent.run(
        parsed,
        analysis_result,
        use_llm=use_llm,
    )

    return {
        "pipeline": [
            "analysis-agent",
            "architecture-agent",
            "line-explanation-agent",
        ],
        "llm": {
            "enabled": llm.enabled,
            "model": llm.current_model or llm.primary_model,
            "line_explanations_with_llm": use_llm and llm.enabled,
            "better_architecture_with_llm": use_better_architecture and llm.enabled,
        },
        "analysis": analysis_result,
        "architecture": architecture_result,
        "line_explanations": line_result,
    }