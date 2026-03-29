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
- **Jinja2** – prompt templates (`agent/prompts/*.jinja`)
- **pygls** – Python LSP server for VS Code integration
- **Pydantic Settings** – configuration from `.env`
- **pytest** – testing

## Project layout

```
agent/              # Main package
  cli.py            # CLI entry point (typer app)
  config.py         # Settings (pydantic-settings, reads .env)
  state.py          # Dataclasses: TestCase, AnnotationSuggestion, AgentState
  graph.py          # LangGraph workflow (scan → parse → rag → annotate → pr)
  prompts/
    __init__.py     # Jinja2 template loader (load_prompt helper)
    annotator_system.jinja  # System prompt for LLM role + output format
    annotator_user.jinja    # User prompt with similar cases + target test
  nodes/
    scanner.py      # Finds .java test files in Maven src/test/java
    parser.py       # Regex-based Java parser, classifies @AccessMode presence
    rag.py          # Ollama embeddings → ChromaDB, similarity retrieval
    annotator.py    # Ollama LLM prompting with RAG context (uses Jinja templates)
    pr_creator.py   # Applies annotations to files, git commit, GitHub PR
  lsp/
    __init__.py     # LSP package init
    __main__.py     # python -m agent.lsp entry
    server.py       # pygls LSP server (diagnostics, code lens, code actions, commands)
    analyzer.py     # Bridge: runs LangGraph pipeline → list[SuggestionResult]
  mcp/
    server.py       # FastMCP server with 3 tools
tests/              # pytest tests (scanner, parser, rag helpers)
vscode-extension/   # VS Code extension (thin JS shim — NO TypeScript)
  extension.js      # ~20 lines: spawns Python LSP via stdio
  package.json      # Extension manifest, commands, settings schema
```

## Key conventions

- **State is a dataclass** (`AgentState`) with `Annotated[list, operator.add]` fields for LangGraph reducer semantics.
- Each node function takes `AgentState` and returns a `dict` of state updates.
- Config comes from `.env` via `pydantic-settings` (`agent.config.get_settings()`).
- **Prompts are Jinja2 templates** in `agent/prompts/*.jinja`, loaded via `agent.prompts.load_prompt()`. The annotator renders them at runtime — edit the `.jinja` files to tweak LLM behavior without touching Python code.
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
- **Change LLM prompt**: Edit the `.jinja` files in `agent/prompts/` — no Python changes needed.
- **Add MCP tool**: Add `@mcp.tool()` function in `agent/mcp/server.py`.
- **Change Ollama model**: Update `OLLAMA_LLM_MODEL` or `OLLAMA_EMBED_MODEL` in `.env`.
- **Add VS Code command**: Add to `contributes.commands` in `vscode-extension/package.json`, implement handler in `agent/lsp/server.py` with `@server.command()`.
- **Build extension**: `cd vscode-extension && npm install && npm run package`.

## VS Code extension

The extension is **100% Python logic** — all VS Code features (diagnostics, code lens, code actions, commands) are implemented in the pygls LSP server at `agent/lsp/server.py`. The `vscode-extension/` folder contains only:

- **extension.js** (~20 lines of JS) — thin shim that spawns `python -m agent.lsp.server` over stdio. This is the minimum VS Code requires; it contains zero logic.
- **package.json** — extension manifest declaring commands and settings.

Key architecture of the Python LSP server:
- `server.py` uses **pygls** `LanguageServer` with `@server.command()` for commands, `@server.feature(TEXT_DOCUMENT_CODE_ACTION)` for quick fixes, `@server.feature(TEXT_DOCUMENT_CODE_LENS)` for inline lenses.
- `analyzer.py` bridges the LSP server to the LangGraph pipeline — runs the graph and returns lightweight `SuggestionResult` dataclasses.
- Suggestions are cached in-memory (`dict[uri, list[SuggestionResult]]`) and published as diagnostics.
- `_insert_annotation()` edits Java files server-side (same logic as `pr_creator.py`).

## Gotchas

- The parser regex expects standard JUnit 5 patterns (`@Test`, `@ParameterizedTest`). Unusual formatting may be missed.
- ChromaDB vector store is persisted to `chroma_db/` — delete it to rebuild the index.
- The PR creator modifies files in-place; it works on the actual project checkout. Make sure the project path is a git repo with a remote named `origin`.
- The VS Code extension requires `ril2m-agent` installed in the Python environment pointed to by `ril2m.pythonPath`. It spawns `python -m agent.lsp.server`.
