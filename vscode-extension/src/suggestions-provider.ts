/**
 * TreeDataProvider that displays annotation suggestions in the sidebar.
 */

import * as vscode from "vscode";
import { Suggestion } from "./types";

// ─── Tree item types ────────────────────────────────────────────────

export class SuggestionFileItem extends vscode.TreeItem {
  constructor(
    public readonly filePath: string,
    public readonly suggestions: SuggestionItem[]
  ) {
    const fileName = filePath.split(/[/\\]/).pop() ?? filePath;
    super(fileName, vscode.TreeItemCollapsibleState.Expanded);
    this.tooltip = filePath;
    this.iconPath = new vscode.ThemeIcon("file");
    this.description = `${suggestions.length} suggestion(s)`;
    this.contextValue = "file";
  }
}

export class SuggestionItem extends vscode.TreeItem {
  constructor(public readonly suggestion: Suggestion) {
    super(
      `${suggestion.method}`,
      vscode.TreeItemCollapsibleState.None
    );

    const pct = Math.round(suggestion.confidence * 100);
    this.description = `${suggestion.suggested_annotation} (${pct}%)`;
    this.tooltip = new vscode.MarkdownString(
      `**${suggestion.class}.${suggestion.method}**\n\n` +
        `Suggested: \`${suggestion.suggested_annotation}\`\n\n` +
        `Confidence: ${pct}%\n\n` +
        `Reasoning: ${suggestion.reasoning}`
    );

    this.iconPath = this.getConfidenceIcon(suggestion.confidence);
    this.contextValue = "suggestion";

    // Click to open the file
    this.command = {
      command: "ril2m.openSuggestionFile",
      title: "Open File",
      arguments: [suggestion],
    };
  }

  private getConfidenceIcon(confidence: number): vscode.ThemeIcon {
    if (confidence >= 0.8) {
      return new vscode.ThemeIcon(
        "pass-filled",
        new vscode.ThemeColor("testing.iconPassed")
      );
    }
    if (confidence >= 0.5) {
      return new vscode.ThemeIcon(
        "warning",
        new vscode.ThemeColor("list.warningForeground")
      );
    }
    return new vscode.ThemeIcon(
      "question",
      new vscode.ThemeColor("list.deemphasizedForeground")
    );
  }
}

type TreeElement = SuggestionFileItem | SuggestionItem;

// ─── Provider ───────────────────────────────────────────────────────

export class SuggestionsProvider
  implements vscode.TreeDataProvider<TreeElement>
{
  private _onDidChangeTreeData = new vscode.EventEmitter<
    TreeElement | undefined | void
  >();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private fileItems: SuggestionFileItem[] = [];
  private _suggestions: Suggestion[] = [];

  get suggestions(): Suggestion[] {
    return this._suggestions;
  }

  /** Replace the entire suggestions list and refresh the tree. */
  setSuggestions(suggestions: Suggestion[]): void {
    this._suggestions = suggestions;

    // Group by file
    const byFile = new Map<string, Suggestion[]>();
    for (const s of suggestions) {
      const key = s.file;
      if (!byFile.has(key)) {
        byFile.set(key, []);
      }
      byFile.get(key)!.push(s);
    }

    this.fileItems = [];
    for (const [filePath, fileSuggestions] of byFile) {
      const items = fileSuggestions.map((s) => new SuggestionItem(s));
      this.fileItems.push(new SuggestionFileItem(filePath, items));
    }

    this._onDidChangeTreeData.fire();
  }

  /** Clear all suggestions. */
  clear(): void {
    this._suggestions = [];
    this.fileItems = [];
    this._onDidChangeTreeData.fire();
  }

  /** Remove a single suggestion (after applying it). */
  removeSuggestion(suggestion: Suggestion): void {
    this._suggestions = this._suggestions.filter(
      (s) =>
        !(s.file === suggestion.file && s.method === suggestion.method)
    );
    this.setSuggestions(this._suggestions);
  }

  getTreeItem(element: TreeElement): vscode.TreeItem {
    return element;
  }

  getChildren(element?: TreeElement): TreeElement[] {
    if (!element) {
      return this.fileItems;
    }
    if (element instanceof SuggestionFileItem) {
      return element.suggestions;
    }
    return [];
  }
}
