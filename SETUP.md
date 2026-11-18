# Setup: mcp-workflow-agent

Repo to create (empty, no README): https://github.com/harkaransingh44-stack/mcp-workflow-agent

This folder is a complete git repo with history once you unzip it. You only need to add the GitHub remote and push. Do not run `git init` again.

## 1. Confirm it runs locally

```bash
cd mcp-workflow-agent
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest
python -m ticketflow.agent_cli --provider mock --out reports/summary.md
```

The tests and the mock run do not need an Anthropic API key or network access to Claude. Open `reports/summary.md` and `reports/report.html` to review the output.

Optional — live Claude (only if you have a key you are willing to use):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python -m ticketflow.agent_cli --provider anthropic --out reports/summary-live.md
```

## 2. Create the GitHub repo and push

1. Open https://github.com/new
2. Repository name: `mcp-workflow-agent`
3. Leave it **empty** — do not add a README, .gitignore, or license (this folder already has them)
4. Create the repository

Then, from this folder:

```bash
git remote add origin https://github.com/harkaransingh44-stack/mcp-workflow-agent.git
git branch -M main
git push -u origin main
```

If `origin` already exists, use `git remote set-url origin https://github.com/harkaransingh44-stack/mcp-workflow-agent.git` instead of `git remote add`.

If Git asks for a password, GitHub will not accept your account password. Use one of these:

- `brew install gh && gh auth login`, then push again, or
- a Personal Access Token: GitHub > Settings > Developer settings > Fine-grained tokens, with *Contents: read & write* on this repo only. Paste the token when Git asks for a password.

After the push, open the **Actions** tab and confirm the `tests` workflow is green.

## 3. After it is live

For job forms that ask for GitHub, you can also link this repo alongside the API test framework:

`https://github.com/harkaransingh44-stack/mcp-workflow-agent`

To use it from Claude Desktop, follow the config snippet in the README. Use absolute paths to this repo and to `.venv/bin/python`.

## What to say about this in interviews

Keep this factual and tied to what is in the repo. This is a public portfolio project. It is not a description of internal tools from an employer.

- **What it is.** An MCP server that exposes a local ticket tracker (create, list, update status, summarize) and a batch agent that reads a sample inbox, classifies each request, files tickets, and writes a summary.
- **Why MCP.** The tools are the contract. Claude Desktop can call them over stdio; the batch agent uses the same SQLite store without needing a desktop host. That split is the point of the architecture diagram in the README.
- **Mock vs live.** The default path is a deterministic mock classifier, so CI and local demos run without an API key. The Anthropic provider is a thin wrapper around `messages.create` and is optional.
- **Retries and logs.** Classifier calls go through exponential backoff. Logs are JSON on stderr, with request id, attempt, and error fields, so a failed run is traceable.
- **How the tests work.** Store tests hit SQLite. MCP tests use the official in-memory `Client` against the server object — no subprocess and no port. Workflow tests inject `MockProvider` and `FlakyProvider` to cover the happy path, dry-run, and retries.
- **What not to say.** Do not claim this is production software from Amazon or any other employer. Do not describe it as a multi-tenant product. Do not say you trained a model; classification here is either a keyword mock or a hosted Claude API call. AI workflow work in this repo started as a portfolio project, not as a claim of years of production agent experience.
