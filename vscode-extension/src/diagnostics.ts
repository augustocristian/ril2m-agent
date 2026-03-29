/**
 * Diagnostics provider — shows warnings for missing @AccessMode annotations.
 */

import * as vscode from "vscode";
import { Suggestion } from "./types";

const DIAGNOSTIC_SOURCE = "ril2m";

export class DiagnosticsManager {
  private collection: vscode.DiagnosticCollection;

  constructor() {
    this.collection =
      vscode.languages.createDiagnosticCollection(DIAGNOSTIC_SOURCE);
  }

  /**
   * Publish diagnostics for the given suggestions.
   * Each unannotated test method gets a Warning diagnostic.
   */
  async setSuggestions(suggestions: Suggestion[]): Promise<void> {
    this.collection.clear();

    // Group suggestions by file
    const byFile = new Map<string, Suggestion[]>();
    for (const s of suggestions) {
      if (!byFile.has(s.file)) {
        byFile.set(s.file, []);
      }
      byFile.get(s.file)!.push(s);
    }

    for (const [filePath, fileSuggestions] of byFile) {
      const uri = vscode.Uri.file(filePath);
      const diagnostics: vscode.Diagnostic[] = [];

      try {
        const doc = await vscode.workspace.openTextDocument(uri);

        for (const s of fileSuggestions) {
          const range = this.findMethodRange(doc, s.method);
          const diag = new vscode.Diagnostic(
            range,
            `Missing @AccessMode annotation. Suggested: ${s.suggested_annotation} (${Math.round(s.confidence * 100)}% confidence)\n${s.reasoning}`,
            vscode.DiagnosticSeverity.Warning
          );
          diag.source = DIAGNOSTIC_SOURCE;
          diag.code = s.suggested_annotation;
          diagnostics.push(diag);
        }
      } catch {
        // File may not be openable — skip
        continue;
      }

      this.collection.set(uri, diagnostics);
    }
  }

  /**
   * Find the range of a method declaration in a document.
   */
  private findMethodRange(
    doc: vscode.TextDocument,
    methodName: string
  ): vscode.Range {
    const text = doc.getText();
    // Match: void methodName(
    const pattern = new RegExp(
      `(void\\s+${this.escapeRegex(methodName)}\\s*\\()`,
      "m"
    );
    const match = pattern.exec(text);

    if (match && match.index !== undefined) {
      const pos = doc.positionAt(match.index);
      const endPos = doc.positionAt(match.index + match[0].length);
      return new vscode.Range(pos, endPos);
    }

    // Fallback: first line
    return new vscode.Range(0, 0, 0, 0);
  }

  private escapeRegex(s: string): string {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  /** Remove diagnostics for a specific file + method. */
  removeSuggestion(suggestion: Suggestion): void {
    const uri = vscode.Uri.file(suggestion.file);
    const existing = this.collection.get(uri);
    if (!existing) {
      return;
    }
    const filtered = existing.filter(
      (d) => d.code !== suggestion.suggested_annotation
    );
    this.collection.set(uri, filtered);
  }

  clear(): void {
    this.collection.clear();
  }

  dispose(): void {
    this.collection.dispose();
  }
}
