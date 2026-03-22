const repoList = document.getElementById("repo-list");
const repoStatus = document.getElementById("repo-status");
const repoMeta = document.getElementById("repo-meta");
const fileTree = document.getElementById("file-tree");
const fileTitle = document.getElementById("file-title");
const codeView = document.getElementById("code-view");
const explainView = document.getElementById("explain-view");
const explainButton = document.getElementById("explain-btn");

let activeRepo = null;
let activePath = null;
let statusTimer = null;

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.json();
}

function setStatus(message, type = "") {
  repoStatus.textContent = message;
  repoStatus.className = `status ${type}`.trim();
}

function renderRepoList(repos) {
  repoList.innerHTML = "";
  if (!repos.length) {
    repoList.innerHTML = "<p class=\"placeholder\">No repos analyzed yet.</p>";
    return;
  }
  repos.forEach((repo) => {
    const card = document.createElement("div");
    card.className = `repo-card ${activeRepo === repo.id ? "active" : ""}`;
    const languageCount = Object.keys(repo.language_stats || {}).length;
    card.innerHTML = `
      <h3>${repo.git_url}</h3>
      <p>${repo.file_count} files</p>
      <div class="badge">${languageCount} languages</div>
    `;
    card.addEventListener("click", () => selectRepo(repo));
    repoList.appendChild(card);
  });
}

function renderTree(tree, container) {
  container.innerHTML = "";
  tree.forEach((node) => {
    const item = document.createElement("div");
    item.className = "tree-item";
    const label = document.createElement("div");
    label.className = "label";
    label.innerHTML = node.type === "dir" ? "📁" : "📄";
    const text = document.createElement("span");
    text.textContent = node.name;
    if (node.type === "file") {
      text.classList.add("file");
    }
    label.appendChild(text);
    item.appendChild(label);
    container.appendChild(item);

    if (node.type === "dir") {
      const children = document.createElement("div");
      children.className = "tree-children";
      renderTree(node.children || [], children);
      item.appendChild(children);
    } else {
      label.addEventListener("click", () => selectFile(node.path));
    }
  });
}

function renderCode(content) {
  const lines = content.split("\n");
  codeView.innerHTML = "";
  lines.forEach((line, idx) => {
    const row = document.createElement("div");
    row.className = "line";
    const lineNumber = document.createElement("span");
    lineNumber.className = "line-number";
    lineNumber.textContent = idx + 1;
    const lineText = document.createElement("span");
    lineText.textContent = line || " ";
    row.appendChild(lineNumber);
    row.appendChild(lineText);
    codeView.appendChild(row);
  });
}

function renderExplanation(payload) {
  explainView.innerHTML = "";
  const overview = document.createElement("div");
  overview.className = "explain-block";
  overview.innerHTML = `
    <h4>File Overview</h4>
    <p>Language: ${payload.overview.language}</p>
    <p>Lines: ${payload.overview.line_count}</p>
    <p>Functions: ${payload.overview.functions.join(", ") || "None"}</p>
    <p>Classes: ${payload.overview.classes.join(", ") || "None"}</p>
  `;
  explainView.appendChild(overview);

  payload.lines.forEach((line) => {
    const block = document.createElement("div");
    block.className = "explain-line";
    block.textContent = `${line.line}. ${line.explanation}`;
    explainView.appendChild(block);
  });
}

function renderStatus(state) {
  if (!state) {
    repoMeta.textContent = "";
    return;
  }
  const percent = state.total ? Math.round((state.processed / state.total) * 100) : 0;
  const current = state.current_file ? ` · ${state.current_file}` : "";
  repoMeta.textContent = `${state.status} · ${state.processed}/${state.total} (${percent}%)${current}`;
}

async function selectRepo(repo) {
  activeRepo = repo.id;
  activePath = null;
  fileTitle.textContent = "File Viewer";
  codeView.textContent = "";
  explainView.innerHTML = "<div class=\"placeholder\">Select a file and click Explain to get a deep dive breakdown.</div>";
  explainButton.disabled = true;
  repoMeta.textContent = `${repo.file_count} files · ${Object.keys(repo.language_stats || {}).length} languages`;
  renderRepoList(await loadRepos());
  const tree = await fetchJSON(`/api/repos/${repo.id}/tree`);
  renderTree(tree, fileTree);
  await refreshStatus();
  startStatusPolling();
}

async function selectFile(path) {
  if (!activeRepo) {
    return;
  }
  activePath = path;
  fileTitle.textContent = path;
  explainButton.disabled = false;
  const payload = await fetchJSON(`/api/repos/${activeRepo}/file?path=${encodeURIComponent(path)}`);
  renderCode(payload.content);
  explainView.innerHTML = "<div class=\"placeholder\">Click Explain to get line-level notes.</div>";
}

async function explainFile() {
  if (!activeRepo || !activePath) {
    return;
  }
  explainView.innerHTML = "<div class=\"placeholder\">Generating explanation...</div>";
  const payload = await fetchJSON(`/api/repos/${activeRepo}/explain?path=${encodeURIComponent(activePath)}`);
  renderExplanation(payload);
}

async function refreshStatus() {
  if (!activeRepo) {
    return;
  }
  try {
    const state = await fetchJSON(`/api/repos/${activeRepo}/status`);
    renderStatus(state);
  } catch (error) {
    renderStatus(null);
  }
}

function startStatusPolling() {
  if (statusTimer) {
    clearInterval(statusTimer);
  }
  statusTimer = setInterval(refreshStatus, 3000);
}

async function loadRepos() {
  const data = await fetchJSON("/api/repos");
  return data.repos || [];
}

async function addRepo() {
  const input = document.getElementById("repo-url");
  const gitUrl = input.value.trim();
  if (!gitUrl) {
    setStatus("Enter a GitHub URL.", "error");
    return;
  }
  setStatus("Cloning repository...", "");
  try {
    const repo = await fetchJSON("/api/repos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ git_url: gitUrl }),
    });
    setStatus("Repo analyzed.", "success");
    input.value = "";
    const repos = await loadRepos();
    renderRepoList(repos);
    selectRepo(repo);
  } catch (error) {
    setStatus(error.message || "Failed to analyze repo", "error");
  }
}

document.getElementById("add-repo").addEventListener("click", addRepo);
document.getElementById("explain-btn").addEventListener("click", explainFile);

loadRepos().then(renderRepoList).catch(() => renderRepoList([]));
