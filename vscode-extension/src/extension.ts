/**
 * RIL2M Agent – VS Code extension entry point.
 *
 * Activates when a workspace contains a pom.xml and provides:
 *  - Sidebar tree view with annotation suggestions
 *  - Summary webview panel
 *  - CodeLens above unannotated test methods
 *  - Diagnostics (warnings) for missing @AccessMode
 *  - Commands to analyze, apply, and create PRs
 */

import * as vscode from "vscode";
import { analyzeProject, analyzeAndCreatePR } from "./agent-client";
import {
  applySuggestion as applyOne,
  applyAllSuggestions,
} from "./annotation-applier";
import { AccessModeCodeLensProvider } from "./codelens-provider";
import { DiagnosticsManager } from "./diagnostics";
import { SuggestionsProvider } from "./suggestions-provider";
import { SummaryViewProvider } from "./summary-view";
import { Suggestion } from "./types";

// ─── Shared state ───────────────────────────────────────────────────

let suggestionsProvider: SuggestionsProvider;
let summaryProvider: SummaryViewProvider;
let codeLensProvider: AccessModeCodeLensProvider;
let diagnosticsManager: DiagnosticsManager;

// ─── Helpers ────────────────────────────────────────────────────────

function getProjectPath(): string | undefined {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    vscode.window.showErrorMessage(
      "RIL2M: Open a Maven project workspace first."
    );
    return undefined;
  }
  return folders[0].uri.fsPath;
}

function filterByConfidence(suggestions: Suggestion[]): Suggestion[] {
  const threshold = vscode.workspace
    .getConfiguration("ril2m")
    .get<number>("confidenceThreshold", 0.5);
  return suggestions.filter((s) => s.confidence >= threshold);
}

// ─── Commands ───────────────────────────────────────────────────────

async function cmdAnalyzeProject(): Promise<void> {
  const projectPath = getProjectPath();
  if (!projectPath) {
    return;
  }

  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: "RIL2M: Analyzing project…",
      cancellable: false,
    },
    async (progress) => {
      progress.report({ message: "Scanning test files…" });

      try {
        const result = await analyzeProject(projectPath);

        if (result.errors.length > 0) {
          for (const err of result.errors) {
            vscode.window.showWarningMessage(`RIL2M: ${err}`);
          }
        }

        const filtered = filterByConfidence(result.suggestions);

        suggestionsProvider.setSuggestions(filtered);
        summaryProvider.setSuggestions(filtered, result.errors);
        codeLensProvider.setSuggestions(filtered);
        await diagnosticsManager.setSuggestions(filtered);

        if (filtered.length === 0) {
          vscode.window.showInformationMessage(
            "RIL2M: All test methods already have @AccessMode annotations."
          );
        } else {
          vscode.window.showInformationMessage(
            `RIL2M: Found ${filtered.length} test method(s) missing @AccessMode.`
          );
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`RIL2M analysis failed: ${msg}`);
      }
    }
  );
}

async function cmdApplySuggestion(suggestion?: Suggestion): Promise<void> {
  if (!suggestion) {
    vscode.window.showErrorMessage("RIL2M: No suggestion selected.");
    return;
  }

  const success = await applyOne(suggestion);
  if (success) {
    suggestionsProvider.removeSuggestion(suggestion);
    codeLensProvider.removeSuggestion(suggestion);
    diagnosticsManager.removeSuggestion(suggestion);
    vscode.window.showInformationMessage(
      `Applied ${suggestion.suggested_annotation} to ${suggestion.class}.${suggestion.method}`
    );
  }
}

async function cmdApplyAll(): Promise<void> {
  const suggestions = suggestionsProvider.suggestions;
  if (suggestions.length === 0) {
    vscode.window.showInformationMessage("RIL2M: No suggestions to apply.");
    return;
  }

  const answer = await vscode.window.showWarningMessage(
    `Apply ${suggestions.length} annotation(s)?`,
    { modal: true },
    "Apply All"
  );
  if (answer !== "Apply All") {
    return;
  }

  const applied = await applyAllSuggestions(suggestions);
  suggestionsProvider.clear();
  codeLensProvider.clear();
  diagnosticsManager.clear();
  vscode.window.showInformationMessage(
    `RIL2M: Applied ${applied} annotation(s).`
  );
}

async function cmdCreatePR(): Promise<void> {
  const projectPath = getProjectPath();
  if (!projectPath) {
    return;
  }

  const answer = await vscode.window.showWarningMessage(
    "This will apply annotations and create a GitHub PR. Continue?",
    { modal: true },
    "Create PR"
  );
  if (answer !== "Create PR") {
    return;
  }

  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: "RIL2M: Creating Pull Request…",
      cancellable: false,
    },
    async () => {
      try {
        const result = await analyzeAndCreatePR(projectPath);

        if (result.pr_url) {
          const action = await vscode.window.showInformationMessage(
            `RIL2M: PR created successfully!`,
            "Open PR"
          );
          if (action === "Open PR") {
            vscode.env.openExternal(vscode.Uri.parse(result.pr_url));
          }
        }

        summaryProvider.setSuggestions(
          result.suggestions,
          result.errors,
          result.pr_url
        );
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`RIL2M PR creation failed: ${msg}`);
      }
    }
  );
}

function cmdRefresh(): void {
  cmdAnalyzeProject();
}

function cmdClear(): void {
  suggestionsProvider.clear();
  summaryProvider.clear();
  codeLensProvider.clear();
  diagnosticsManager.clear();
}

async function cmdOpenSuggestionFile(suggestion: Suggestion): Promise<void> {
  const uri = vscode.Uri.file(suggestion.file);
  const doc = await vscode.workspace.openTextDocument(uri);
  const editor = await vscode.window.showTextDocument(doc);

  // Try to scroll to the method
  const text = doc.getText();
  const pattern = new RegExp(
    `void\\s+${suggestion.method.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\(`
  );
  const match = pattern.exec(text);
  if (match) {
    const pos = doc.positionAt(match.index);
    editor.revealRange(
      new vscode.Range(pos, pos),
      vscode.TextEditorRevealType.InCenter
    );
    editor.selection = new vscode.Selection(pos, pos);
  }
}

// ─── Activation ─────────────────────────────────────────────────────

export function activate(context: vscode.ExtensionContext): void {
  // Providers
  suggestionsProvider = new SuggestionsProvider();
  summaryProvider = new SummaryViewProvider(context.extensionUri);
  codeLensProvider = new AccessModeCodeLensProvider();
  diagnosticsManager = new DiagnosticsManager();

  // Tree view
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider(
      "ril2m.suggestions",
      suggestionsProvider
    )
  );

  // Webview
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      SummaryViewProvider.viewType,
      summaryProvider
    )
  );

  // CodeLens (Java files only)
  context.subscriptions.push(
    vscode.languages.registerCodeLensProvider(
      { language: "java", scheme: "file" },
      codeLensProvider
    )
  );

  // Diagnostics
  context.subscriptions.push(diagnosticsManager);

  // Commands
  context.subscriptions.push(
    vscode.commands.registerCommand("ril2m.analyzeProject", cmdAnalyzeProject),
    vscode.commands.registerCommand("ril2m.applySuggestion", cmdApplySuggestion),
    vscode.commands.registerCommand("ril2m.applyAllSuggestions", cmdApplyAll),
    vscode.commands.registerCommand("ril2m.createPR", cmdCreatePR),
    vscode.commands.registerCommand("ril2m.refreshSuggestions", cmdRefresh),
    vscode.commands.registerCommand("ril2m.clearSuggestions", cmdClear),
    vscode.commands.registerCommand(
      "ril2m.openSuggestionFile",
      cmdOpenSuggestionFile
    )
  );

  // Auto-analyze on activation if configured
  const autoAnalyze = vscode.workspace
    .getConfiguration("ril2m")
    .get<boolean>("autoAnalyze", false);
  if (autoAnalyze) {
    cmdAnalyzeProject();
  }
}

export function deactivate(): void {
  diagnosticsManager?.dispose();
}
