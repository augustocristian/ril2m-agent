# RIL2M Agent

**LangGraph + MCP agent that suggests `@AccessMode` annotations for Java Maven test cases using RAG and Ollama.**

The agent scans Java Maven projects, identifies test methods missing `@AccessMode` annotations, uses a RAG pipeline (Ollama embeddings + ChromaDB) to find similar already-annotated tests, and prompts an LLM to suggest the correct annotation. It can also create a GitHub Pull Request with the changes applied.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    LangGraph Workflow                    │
│                                                         │
│  ┌──────┐   ┌───────┐   ┌─────────┐   ┌───────────┐   │
│  │ Scan ├──►│ Parse ├──►│Build RAG├──►│ Annotate  │   │
│  └──────┘   └───────┘   └─────────┘   └─────┬─────┘   │
│                                              │         │
│                                        ┌─────▼─────┐   │
│                                        │ Create PR │   │
│                                        └───────────┘   │
└─────────────────────────────────────────────────────────┘
         │                        │
    ┌────▼────┐            ┌──────▼──────┐
    │  Ollama │            │   GitHub    │
    │ LLM +   │            │   API       │
    │ Embed   │            └─────────────┘
    └─────────┘
```

### Pipeline Steps

1. **Scanner** – Recursively finds `.java` test files under `src/test/java` in Maven projects (supports multi-module projects).
2. **Parser** – Extracts test methods using regex, classifies them as annotated (has `@AccessMode`) or non-annotated.
3. **RAG Index** – Embeds annotated test method bodies (without the annotation) into ChromaDB using Ollama embeddings (`nomic-embed-text`).
4. **Annotator** – For each non-annotated test, retrieves the *k* most similar annotated tests from the vector store, then prompts the Ollama LLM to suggest the correct `@AccessMode` value.
5. **PR Creator** *(optional)* – Applies the annotations to source files, commits, pushes a branch, and opens a GitHub PR.

## Prerequisites

- **Python 3.12+**
- **Ollama** running locally (or remotely) with the required models pulled:
  ```bash
  ollama pull llama3.2
  ollama pull nomic-embed-text
  ```
- **Git** (for PR creation)
- **GitHub token** (only if you want automatic PR creation)

## Installation

```bash
# Clone the repository
git clone https://github.com/augustocristian/ril2m-agent.git
cd ril2m-agent

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

# Install the package with dependencies
pip install .

# For development (includes pytest, flake8, etc.)
pip install ".[dev]"
```

## Configuration

Copy the example environment file and edit it:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_LLM_MODEL` | `llama3.2` | LLM model for annotation suggestion |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Embedding model for RAG |
| `GITHUB_TOKEN` | *(empty)* | GitHub personal access token (for PR creation) |
| `GITHUB_OWNER` | *(empty)* | GitHub repository owner |
| `GITHUB_REPO` | *(empty)* | GitHub repository name |
| `GITHUB_BASE_BRANCH` | `main` | Base branch for PRs |
| `CHROMA_PERSIST_DIR` | `./chroma_db` | ChromaDB persistence directory |
| `CHROMA_COLLECTION_NAME` | `annotated_tests` | ChromaDB collection name |
| `LOG_LEVEL` | `INFO` | Logging level |

## Usage

### CLI – Analyze a project

```bash
# Suggest annotations (output as a table)
ril2m analyze /path/to/maven-project

# Suggest annotations (JSON output)
ril2m analyze /path/to/maven-project --json

# Suggest annotations AND create a GitHub PR
ril2m analyze /path/to/maven-project --pr

# Change log level
ril2m analyze /path/to/maven-project --log-level DEBUG
```

### MCP Server

The agent exposes its capabilities as an MCP server (stdio transport), so it can be used by any MCP-compatible client (e.g., Claude Desktop, Claude Code).

```bash
# Start the MCP server
ril2m serve
# or
python -m agent.mcp.server
```

#### MCP Client Configuration

Add the following to your MCP client configuration:

```json
{
  "mcpServers": {
    "ril2m-agent": {
      "command": "python",
      "args": ["-m", "agent.mcp.server"],
      "cwd": "/path/to/ril2m-agent"
    }
  }
}
```

#### Available MCP Tools

| Tool | Description |
|------|-------------|
| `analyze_project` | Scan project and suggest annotations (no PR) |
| `analyze_and_create_pr` | Scan, suggest, apply, and create a GitHub PR |
| `list_unannotated_tests` | List test methods missing `@AccessMode` (no LLM) |

### Python API

```python
from agent.graph import build_graph
from agent.state import AgentState

graph = build_graph()
result = graph.invoke(
    AgentState(
        project_path="/path/to/maven-project",
        create_pr=False,
    )
)

for suggestion in result.suggestions:
    print(
        f"{suggestion.test_case.class_name}.{suggestion.test_case.method_name}: "
        f"{suggestion.suggested_annotation} ({suggestion.confidence:.0%})"
    )
```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=agent --cov-report=html

# Run a specific test file
pytest tests/test_scanner.py -v
```

> **Note:** The scanner and parser tests use fixture-generated Java files and do not require Ollama. The RAG and annotator integration tests require a running Ollama instance.

## Project Structure

```
ril2m-agent/
├── agent/
│   ├── __init__.py          # Package init
│   ├── cli.py               # Typer CLI entry point
│   ├── config.py            # Pydantic settings (env vars / .env)
│   ├── graph.py             # LangGraph workflow definition
│   ├── state.py             # State dataclasses (TestCase, AgentState, etc.)
│   ├── prompts/             # Jinja2 prompt templates
│   │   ├── __init__.py      # Template loader (load_prompt helper)
│   │   ├── annotator_system.jinja  # System prompt for annotation suggestion
│   │   └── annotator_user.jinja    # User prompt (similar cases + target test)
│   ├── nodes/
│   │   ├── scanner.py       # Find Java test files in Maven projects
│   │   ├── parser.py        # Parse test methods, classify by @AccessMode
│   │   ├── rag.py           # Build ChromaDB index, retrieve similar tests
│   │   ├── annotator.py     # LLM suggestion via Ollama
│   │   └── pr_creator.py    # Apply annotations + create GitHub PR
│   └── mcp/
│       └── server.py        # MCP server (FastMCP, stdio transport)
├── tests/
│   ├── conftest.py          # Shared fixtures (sample Maven project)
│   ├── test_scanner.py      # Scanner node tests
│   ├── test_parser.py       # Parser node tests
│   └── test_rag.py          # RAG helper tests
├── .env.example             # Environment variable template
├── pyproject.toml           # Project config and dependencies
├── CLAUDE.md                # Claude Code project context
└── README.md                # This file
```

## Customizing Prompts

All LLM prompts are stored as **Jinja2 templates** in [`agent/prompts/`](agent/prompts/):

| File | Purpose |
|------|---------|
| `annotator_system.jinja` | System prompt defining the LLM role and output format |
| `annotator_user.jinja` | User prompt with similar-case examples and the target test |

Templates use standard Jinja2 syntax (`{{ variable }}`, `{% for %}`, `{% if %}`, etc.) and are rendered at runtime by the annotator node. To customize the LLM behavior, edit the `.jinja` files directly — no Python changes needed.

To add a new prompt, create a `.jinja` file in `agent/prompts/` and load it with:

```python
from agent.prompts import load_prompt
template = load_prompt("my_new_prompt.jinja")
rendered = template.render(variable="value")
```

## How It Works

### @AccessMode Annotation

`@AccessMode` is a Java annotation used in test methods to declare the database access mode required by the test:

| Value | Meaning |
|-------|---------|
| `READONLY` | Test only reads data (SELECT queries) |
| `READWRITE` | Test reads and writes data (SELECT + INSERT/UPDATE/DELETE) |
| `WRITEONLY` | Test only writes data |
| `NOACCESS` | Test does not access the database |

### RAG Pipeline

1. Annotated test methods are embedded **without** their `@AccessMode` annotation — so the vector store captures code semantics, not the annotation text.
2. For each non-annotated test, the top-*k* most similar annotated tests are retrieved.
3. The LLM receives the similar examples (with their annotations) plus the target method and produces a structured suggestion.

This few-shot retrieval approach allows the LLM to learn the project's annotation conventions from real examples rather than relying solely on its general training data.

## License

See [LICENSE](LICENSE) for details.
