# RIL2M Agent – Claude Code Project Context

## What is this project?

A LangGraph + MCP agent that suggests **RETORCH** `@AccessMode` annotations for Java Maven test cases.
It uses Ollama (local LLM + embeddings), ChromaDB for vector storage, and can create GitHub PRs.

RETORCH `@AccessMode` annotations have 4 attributes: `resID`, `concurrency`, `sharing`, `accessMode`.
A test can have **multiple** `@AccessMode` annotations (one per Resource it accesses).
Resources are declared in `.retorch/<SUT_NAME>SystemResources.json` files (dict keyed by resource ID).

The agent can also **suggest new resources** not yet in the JSON file and include them in PRs.

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
  state.py          # Dataclasses: TestCase, Resource, AnnotationSuggestion, AgentState
  graph.py          # LangGraph workflow (scan → parse → rag → annotate → pr)
  resources.py      # Shared resource management (load/save/add/format for prompts)
  prompts/
    __init__.py     # Jinja2 template loader (load_prompt helper)
    annotator_system.jinja  # System prompt for LLM role + output format
    annotator_user.jinja    # User prompt with similar cases + target test
  nodes/
    scanner.py      # Finds .java test files in Maven src/test/java + .retorch/ resources
    parser.py       # Regex-based Java parser, classifies @AccessMode presence
    rag.py          # Ollama embeddings → ChromaDB, similarity retrieval
    annotator.py    # Ollama LLM prompting with RAG context (uses Jinja templates)
    pr_creator.py   # Applies annotations + new resources to files, git commit, GitHub PR
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
- **AccessMode is a dataclass** with `res_id`, `concurrency`, `sharing`, `access_mode`. A `TestCase` has a `list[AccessMode]` (zero or more). `AnnotationSuggestion` has `suggested_access_modes: list[AccessMode]` and `new_resources: list[NewResourceSuggestion]`.
- **Resource is a dataclass** matching the real RETORCH JSON format (`resource_id`, `resource_type`, `hierarchy_parent`, `replaceable`, `elasticity_model`, `minimal_capacities`, `docker_image`). Has `to_dict()`/`from_dict()` for serialization.
- **`agent/resources.py`** is the shared module for resource operations used by both the agent pipeline and the LSP server. It handles finding, loading, saving, adding resources, and formatting them for prompts.
- The parser uses **regex** (not a full Java AST) to extract test methods and parse all `@AccessMode(resID=..., concurrency=..., sharing=..., accessMode=...)` attributes.
- The scanner finds `.retorch/*SystemResources.json` files (direct or in child modules for multi-module Maven projects).
- The RAG corpus stores annotated test bodies **without** the `@AccessMode` annotations so retrieval is based on code semantics.

## Resource file location

Resources live in `.retorch/<SUT_NAME>SystemResources.json` at the project root (or child module root). The JSON format is a **dict keyed by resource ID**:
```json
{
  "loginservice": {
    "hierarchyParent": ["mysql"],
    "replaceable": [],
    "elasticityModel": { "elasticityID": "...", "elasticity": 5, "elasticityCost": 15.0 },
    "resourceType": "LOGICAL",
    "resourceID": "loginservice",
    "minimalCapacities": [{"name": "memory", "quantity": 0.3}],
    "dockerImage": "..."
  }
}
```

## New resource suggestion flow

1. **Annotator** — LLM outputs `NEW_RESOURCE: resID="..." hierarchyParent="..." reason="..."` lines when it detects a test accesses an undefined resource.
2. **`_parse_llm_response()`** — Parses `NEW_RESOURCE` lines into `NewResourceSuggestion` objects (each wrapping a `Resource` scaffold from `build_default_resource()`).
3. **PR Creator** — Calls `add_resources()` from `agent/resources.py` to write new resources to `SystemResources.json` and includes the file in the git commit.
4. **LSP Server** — Calls `_apply_new_resources_bulk()` which uses the same shared `add_resources()` when applying suggestions in VS Code.

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
- **Add new resource fields**: Update `Resource` dataclass in `state.py` and `to_dict()`/`from_dict()` methods. The shared `resources.py` module handles serialization.

## VS Code extension

The extension is **100% Python logic** — all VS Code features (diagnostics, code lens, code actions, commands) are implemented in the pygls LSP server at `agent/lsp/server.py`. The `vscode-extension/` folder contains only:

- **extension.js** (~20 lines of JS) — thin shim that spawns `python -m agent.lsp.server` over stdio. This is the minimum VS Code requires; it contains zero logic.
- **package.json** — extension manifest declaring commands and settings.

Key architecture of the Python LSP server:
- `server.py` uses **pygls** `LanguageServer` with `@server.command()` for commands, `@server.feature(TEXT_DOCUMENT_CODE_ACTION)` for quick fixes, `@server.feature(TEXT_DOCUMENT_CODE_LENS)` for inline lenses.
- `analyzer.py` bridges the LSP server to the LangGraph pipeline — runs the graph and returns lightweight `SuggestionResult` dataclasses (including `NewResourceResult`).
- Suggestions are cached in-memory (`dict[uri, list[SuggestionResult]]`) and published as diagnostics.
- `_insert_annotations()` edits Java files server-side (same logic as `pr_creator.py`).
- `_apply_new_resources_bulk()` uses the shared `agent/resources.py` to add new resources to `SystemResources.json`.

## Shared code between agent and VS Code

Both the agent pipeline and VS Code extension share:
- **`agent/resources.py`** — `find_resources_file()`, `load_resources()`, `add_resources()`, `format_resources_for_prompt()`, `build_default_resource()`
- **`agent/prompts/*.jinja`** — Jinja2 prompt templates
- **`agent/state.py`** — Data model (`AccessMode`, `Resource`, `TestCase`, etc.)
- **`agent/graph.py`** — The LangGraph workflow (LSP analyzer calls `build_graph()`)

## Gotchas

- The parser regex expects standard JUnit 5 patterns (`@Test`, `@ParameterizedTest`). Unusual formatting may be missed.
- ChromaDB vector store is persisted to `chroma_db/` — delete it to rebuild the index.
- The PR creator modifies files in-place; it works on the actual project checkout. Make sure the project path is a git repo with a remote named `origin`.
- The VS Code extension requires `ril2m-agent` installed in the Python environment pointed to by `ril2m.pythonPath`. It spawns `python -m agent.lsp.server`.
- Resources file must be in `.retorch/` directory (not `src/test/resources/`). The scanner searches `<root>/.retorch/` and `<root>/<child>/.retorch/` for multi-module projects.
