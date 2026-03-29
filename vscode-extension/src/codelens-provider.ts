/**
 * CodeLens provider — shows inline "Apply @AccessMode(…)" lenses above
 * unannotated test methods.
 */

import * as vscode from "vscode";
import { Suggestion } from "./types";

export class AccessModeCodeLensProvider implements vscode.CodeLensProvider {
  private _onDidChangeCodeLenses = new vscode.EventEmitter<void>();
  readonly onDidChangeCodeLenses = this._onDidChangeCodeLenses.event;

  private suggestions: Suggestion[] = [];

  setSuggestions(suggestions: Suggestion[]): void {
    this.suggestions = suggestions;
    this._onDidChangeCodeLenses.fire();
  }

  clear(): void {
    this.suggestions = [];
    this._onDidChangeCodeLenses.fire();
  }

  removeSuggestion(suggestion: Suggestion): void {
    this.suggestions = this.suggestions.filter(
      (s) =>
        !(s.file === suggestion.file && s.method === suggestion.method)
    );
    this._onDidChangeCodeLenses.fire();
  }

  provideCodeLenses(
    document: vscode.TextDocument,
    _token: vscode.CancellationToken
  ): vscode.CodeLens[] {
    const filePath = document.uri.fsPath;
    const fileSuggestions = this.suggestions.filter(
      (s) => this.normalizePath(s.file) === this.normalizePath(filePath)
    );

    if (fileSuggestions.length === 0) {
      return [];
    }

    const lenses: vscode.CodeLens[] = [];
    const text = document.getText();

    for (const s of fileSuggestions) {
      const range = this.findMethodRange(document, text, s.method);
      if (!range) {
        continue;
      }

      // "Apply" lens
      lenses.push(
        new vscode.CodeLens(range, {
          title: `$(check) Apply ${s.suggested_annotation}`,
          command: "ril2m.applySuggestion",
          arguments: [s],
          tooltip: `${s.reasoning} (${Math.round(s.confidence * 100)}% confidence)`,
        })
      );

      // "Info" lens
      lenses.push(
        new vscode.CodeLens(range, {
          title: `$(info) ${Math.round(s.confidence * 100)}% — ${s.reasoning}`,
          command: "",
          tooltip: `Confidence: ${Math.round(s.confidence * 100)}%`,
        })
      );
    }

    return lenses;
  }

  private findMethodRange(
    doc: vscode.TextDocument,
    text: string,
    methodName: string
  ): vscode.Range | null {
    // Find void methodName( to locate the method declaration line
    const pattern = new RegExp(
      `void\\s+${this.escapeRegex(methodName)}\\s*\\(`,
      "m"
    );
    const match = pattern.exec(text);
    if (!match || match.index === undefined) {
      return null;
    }

    const pos = doc.positionAt(match.index);

    // Walk backwards to find the first annotation line (e.g. @Test)
    let startLine = pos.line;
    while (startLine > 0) {
      const prevLine = doc.lineAt(startLine - 1).text.trim();
      if (prevLine.startsWith("@") || prevLine === "") {
        startLine--;
        if (prevLine === "") {
          break;
        }
      } else {
        break;
      }
    }

    return new vscode.Range(startLine, 0, pos.line, 0);
  }

  private escapeRegex(s: string): string {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  private normalizePath(p: string): string {
    return p.replace(/\\/g, "/").toLowerCase();
  }
}
