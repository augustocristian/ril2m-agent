/**
 * Webview provider for the Analysis Summary panel.
 */

import * as vscode from "vscode";
import { Suggestion } from "./types";

export class SummaryViewProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "ril2m.summary";

  private view?: vscode.WebviewView;
  private suggestions: Suggestion[] = [];
  private errors: string[] = [];
  private prUrl = "";

  constructor(private readonly extensionUri: vscode.Uri) {}

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): void {
    this.view = webviewView;
    webviewView.webview.options = { enableScripts: true };
    this.updateContent();
  }

  setSuggestions(
    suggestions: Suggestion[],
    errors: string[] = [],
    prUrl = ""
  ): void {
    this.suggestions = suggestions;
    this.errors = errors;
    this.prUrl = prUrl;
    this.updateContent();
  }

  clear(): void {
    this.suggestions = [];
    this.errors = [];
    this.prUrl = "";
    this.updateContent();
  }

  private updateContent(): void {
    if (!this.view) {
      return;
    }

    const total = this.suggestions.length;
    const highConf = this.suggestions.filter((s) => s.confidence >= 0.8).length;
    const medConf = this.suggestions.filter(
      (s) => s.confidence >= 0.5 && s.confidence < 0.8
    ).length;
    const lowConf = this.suggestions.filter((s) => s.confidence < 0.5).length;

    const uniqueFiles = new Set(this.suggestions.map((s) => s.file)).size;

    const errorHtml = this.errors.length
      ? `<div class="errors">${this.errors
          .map((e) => `<p class="error">${this.escapeHtml(e)}</p>`)
          .join("")}</div>`
      : "";

    const prHtml = this.prUrl
      ? `<div class="pr"><a href="${this.escapeHtml(this.prUrl)}">View Pull Request</a></div>`
      : "";

    this.view.webview.html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body {
    font-family: var(--vscode-font-family);
    color: var(--vscode-foreground);
    padding: 12px;
    font-size: 13px;
  }
  .stat-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: 16px;
  }
  .stat {
    background: var(--vscode-editor-background);
    border: 1px solid var(--vscode-panel-border);
    border-radius: 6px;
    padding: 10px;
    text-align: center;
  }
  .stat .value {
    font-size: 22px;
    font-weight: bold;
    display: block;
  }
  .stat .label {
    font-size: 11px;
    opacity: 0.7;
    margin-top: 2px;
  }
  .stat.high .value { color: var(--vscode-testing-iconPassed); }
  .stat.med .value { color: var(--vscode-list-warningForeground); }
  .stat.low .value { color: var(--vscode-list-deemphasizedForeground); }
  .errors { margin: 10px 0; }
  .error {
    color: var(--vscode-errorForeground);
    background: var(--vscode-inputValidation-errorBackground);
    padding: 6px 10px;
    border-radius: 4px;
    margin: 4px 0;
  }
  .pr {
    margin-top: 12px;
    padding: 8px;
    background: var(--vscode-editor-background);
    border: 1px solid var(--vscode-panel-border);
    border-radius: 6px;
    text-align: center;
  }
  .pr a {
    color: var(--vscode-textLink-foreground);
    text-decoration: none;
  }
  .empty {
    text-align: center;
    opacity: 0.5;
    margin-top: 40px;
  }
</style>
</head>
<body>
${
  total === 0
    ? '<div class="empty"><p>No analysis results yet.</p><p>Run <strong>RIL2M: Analyze Project</strong> to start.</p></div>'
    : `
  <div class="stat-grid">
    <div class="stat">
      <span class="value">${total}</span>
      <span class="label">Total suggestions</span>
    </div>
    <div class="stat">
      <span class="value">${uniqueFiles}</span>
      <span class="label">Files affected</span>
    </div>
    <div class="stat high">
      <span class="value">${highConf}</span>
      <span class="label">High confidence</span>
    </div>
    <div class="stat med">
      <span class="value">${medConf}</span>
      <span class="label">Medium confidence</span>
    </div>
  </div>
  ${lowConf > 0 ? `<p style="opacity:0.7">${lowConf} low-confidence suggestion(s) — review manually.</p>` : ""}
  ${errorHtml}
  ${prHtml}
`
}
</body>
</html>`;
  }

  private escapeHtml(s: string): string {
    return s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
}
