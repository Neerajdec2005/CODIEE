import json
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from agents import run_multi_agent_pipeline

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
BUILD_DIR = BASE_DIR / 'build'
ARCH_JSON_PATH = BUILD_DIR / 'latest_architecture.json'
ARCH_MMD_PATH = BUILD_DIR / 'latest_architecture.mmd'


def _persist_architecture_files(result: dict) -> None:
    architecture = result.get('architecture', {}) if isinstance(result, dict) else {}
    if not architecture:
        return

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    ARCH_JSON_PATH.write_text(json.dumps(architecture, indent=2), encoding='utf-8')
    ARCH_MMD_PATH.write_text(str(architecture.get('diagram_mermaid', '')), encoding='utf-8')

@app.route('/')
def home():
    return render_template('editor.html')


@app.route('/editor')
def editor_page():
    return render_template('editor.html')


@app.route('/architecture')
def architecture_page():
    return render_template('architecture.html')

@app.route('/test')
def test():
    return render_template('test.html')


@app.route('/api/analyze', methods=['POST'])
def analyze_text():
    payload = request.get_json(silent=True) or {}
    code = payload.get('code', '')
    filename = payload.get('filename', 'snippet.txt')
    requested_line = payload.get('line_number')
    use_llm = True
    use_better_architecture = True

    if not code.strip():
        return jsonify({'error': 'No code content provided.'}), 400

    # Single-line mode: analyze only the requested line and skip architecture generation.
    if requested_line is not None:
        try:
            requested_line = int(requested_line)
        except (TypeError, ValueError):
            return jsonify({'error': 'line_number must be an integer.'}), 400

        lines = code.splitlines()
        if requested_line < 1 or requested_line > max(1, len(lines)):
            return jsonify({'error': 'line_number is out of range for the provided code.'}), 400

        selected_line = lines[requested_line - 1]
        result = run_multi_agent_pipeline(
            code=selected_line,
            filename=filename,
            use_llm=use_llm,
            use_better_architecture=False,
        )

        explanations = result.get('line_explanations', {}).get('explanations', [])
        if explanations:
            explanations[0]['line'] = requested_line
            explanations[0]['code'] = selected_line

        # Keep the response shape stable while avoiding unnecessary architecture LLM calls.
        result['architecture'] = {
            'agent': 'architecture-agent',
            'diagram_mermaid': '',
            'layers': [],
            'notes': ['Architecture skipped for single-line mode'],
            'view_mode': 'single-line',
        }
        return jsonify(result)

    result = run_multi_agent_pipeline(
        code=code,
        filename=filename,
        use_llm=use_llm,
        use_better_architecture=use_better_architecture,
    )
    _persist_architecture_files(result)
    return jsonify(result)


@app.route('/api/analyze-file', methods=['POST'])
def analyze_file():
    if 'code_file' not in request.files:
        return jsonify({'error': 'Missing file field: code_file'}), 400

    uploaded_file = request.files['code_file']
    if uploaded_file.filename == '':
        return jsonify({'error': 'Please choose a code file.'}), 400

    use_llm = True
    use_better_architecture = True

    raw = uploaded_file.read()
    try:
        code = raw.decode('utf-8')
    except UnicodeDecodeError:
        code = raw.decode('latin-1')

    if not code.strip():
        return jsonify({'error': 'Uploaded file is empty.'}), 400

    result = run_multi_agent_pipeline(
        code=code,
        filename=uploaded_file.filename,
        use_llm=use_llm,
        use_better_architecture=use_better_architecture,
    )
    _persist_architecture_files(result)
    return jsonify(result)


@app.route('/api/architecture-latest', methods=['GET'])
def architecture_latest():
    if not ARCH_JSON_PATH.exists():
        return jsonify({'error': 'No architecture file available yet. Analyze code first.'}), 404

    try:
        data = json.loads(ARCH_JSON_PATH.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return jsonify({'error': 'Stored architecture file is invalid.'}), 500

    return jsonify(
        {
            'architecture': data,
            'files': {
                'json': str(ARCH_JSON_PATH.name),
                'mermaid': str(ARCH_MMD_PATH.name),
            },
        }
    )

if __name__ == '__main__':
    app.run(debug=True, port=5001)
