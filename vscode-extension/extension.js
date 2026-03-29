/**
 * RIL2M VS Code extension – thin JS shim that spawns the Python LSP server.
 * All logic lives in Python (agent/lsp/server.py).
 */

const { LanguageClient, TransportKind } = require("vscode-languageclient/node");
const vscode = require("vscode");

let client;

function activate(context) {
  const config = vscode.workspace.getConfiguration("ril2m");
  const pythonPath = config.get("pythonPath", "python");

  const serverOptions = {
    command: pythonPath,
    args: ["-m", "agent.lsp.server"],
    options: {
      env: {
        ...process.env,
        OLLAMA_BASE_URL: config.get("ollamaBaseUrl", "http://localhost:11434"),
        OLLAMA_LLM_MODEL: config.get("ollamaModel", "llama3.2"),
        OLLAMA_EMBED_MODEL: config.get("ollamaEmbedModel", "nomic-embed-text"),
      },
    },
    transport: TransportKind.stdio,
  };

  const clientOptions = {
    documentSelector: [{ scheme: "file", language: "java" }],
  };

  client = new LanguageClient(
    "ril2m",
    "RIL2M Agent",
    serverOptions,
    clientOptions
  );

  context.subscriptions.push(client.start());

  // Auto-analyze on activation if configured
  if (config.get("autoAnalyze", false)) {
    client.onReady().then(() => {
      vscode.commands.executeCommand("ril2m.analyzeProject");
    });
  }
}

function deactivate() {
  return client ? client.stop() : undefined;
}

module.exports = { activate, deactivate };
