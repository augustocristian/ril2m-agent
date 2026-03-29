# RIL2M Agent – Claude Code Project Context

## What is this project?

A LangGraph + MCP agent that suggests `@AccessMode` annotations for Java Maven test cases.
It uses Ollama (local LLM + embeddings), ChromaDB for vector storage, and can create GitHub PRs.

## Tech stack

- **Python 3.12+** with type hints
- **LangGraph** – agent workflow orchestration
- **LangChain** – LLM/embedding abstractions
- **Ollama** – local LLM (`llama3.2`) and embeddings (`nomic-embed-text`)
- **ChromaDB** – vector store for RAG
- **MCP (FastMCP)** – Model Context Protocol server (stdio transport)
- **PyGithub + GitPython** – PR creation
- **Typer + Rich** – CLI
- **Pydantic Settings** – configuration from `.env`
- **pytest** – testing

## Project layout

```
agent/              # Main package
  cli.py            # CLI entry point (typer app)
  config.py         # Settings (pydantic-settings, reads .env)
  state.py          # Dataclasses: TestCase, AnnotationSuggestion, AgentState
  graph.py          # LangGraph workflow (scan → parse → rag → annotate → pr)
  nodes/
    scanner.py      # Finds .java test files in Maven src/test/java
    parser.py       # Regex-based Java parser, classifies @AccessMode presence
    rag.py          # Ollama embeddings → ChromaDB, similarity retrieval
    annotator.py    # Ollama LLM prompting with RAG context
    pr_creator.py   # Applies annotations to files, git commit, GitHub PR
  mcp/
    server.py       # FastMCP server with 3 tools
tests/              # pytest tests (scanner, parser, rag helpers)
```

## Key conventions

- **State is a dataclass** (`AgentState`) with `Annotated[list, operator.add]` fields for LangGraph reducer semantics.
- Each node function takes `AgentState` and returns a `dict` of state updates.
- Config comes from `.env` via `pydantic-settings` (`agent.config.get_settings()`).
- The parser uses **regex** (not a full Java AST) to extract test methods — simpler but handles standard patterns.
- The RAG corpus stores annotated test bodies **without** the `@AccessMode` annotation so retrieval is based on code semantics.

## Running locally

```bash
pip install ".[dev]"          # install with dev deps
ollama pull llama3.2          # pull LLM model
ollama pull nomic-embed-text  # pull embedding model
cp .env.example .env          # configure
ril2m analyze /path/to/project  # run
```

## Tests

```bash
pytest                        # scanner + parser + rag helper tests (no Ollama needed)
pytest -v tests/test_scanner.py
```

## Common tasks

- **Add a new node**: Create `agent/nodes/new_node.py`, add it to `agent/graph.py`, update state if needed.
- **Change LLM prompt**: Edit `_SYSTEM_PROMPT` / `_USER_PROMPT` in `agent/nodes/annotator.py`.
- **Add MCP tool**: Add `@mcp.tool()` function in `agent/mcp/server.py`.
- **Change Ollama model**: Update `OLLAMA_LLM_MODEL` or `OLLAMA_EMBED_MODEL` in `.env`.

## Gotchas

- The parser regex expects standard JUnit 5 patterns (`@Test`, `@ParameterizedTest`). Unusual formatting may be missed.
- ChromaDB vector store is persisted to `chroma_db/` — delete it to rebuild the index.
- The PR creator modifies files in-place; it works on the actual project checkout. Make sure the project path is a git repo with a remote named `origin`.
