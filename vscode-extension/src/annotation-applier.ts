/**
 * Applies a suggested @AccessMode annotation to a Java source file.
 */

import * as vscode from "vscode";
import { Suggestion } from "./types";

/**
 * Apply a single annotation suggestion by editing the source file.
 * Inserts the annotation line above the @Test annotation of the method.
 */
export async function applySuggestion(
  suggestion: Suggestion
): Promise<boolean> {
  const uri = vscode.Uri.file(suggestion.file);

  let doc: vscode.TextDocument;
  try {
    doc = await vscode.workspace.openTextDocument(uri);
  } catch {
    vscode.window.showErrorMessage(
      `Cannot open file: ${suggestion.file}`
    );
    return false;
  }

  const text = doc.getText();

  // Find the method declaration
  const methodPattern = new RegExp(
    `void\\s+${escapeRegex(suggestion.method)}\\s*\\(`,
    "m"
  );
  const methodMatch = methodPattern.exec(text);
  if (!methodMatch || methodMatch.index === undefined) {
    vscode.window.showErrorMessage(
      `Cannot find method ${suggestion.method} in ${suggestion.file}`
    );
    return false;
  }

  const methodPos = doc.positionAt(methodMatch.index);

  // Walk backwards to find @Test (or first annotation above the method)
  let insertLine = methodPos.line;
  for (let i = methodPos.line - 1; i >= 0; i--) {
    const line = doc.lineAt(i).text.trim();
    if (line.startsWith("@")) {
      insertLine = i;
    } else if (line === "") {
      break;
    } else {
      break;
    }
  }

  // Determine indentation from the @Test line
  const indent = doc.lineAt(insertLine).text.match(/^(\s*)/)?.[1] ?? "    ";

  // Check if the annotation already exists
  const annotationLine = `${indent}${suggestion.suggested_annotation}`;
  for (let i = insertLine; i <= methodPos.line; i++) {
    if (doc.lineAt(i).text.includes("@AccessMode")) {
      vscode.window.showInformationMessage(
        `${suggestion.method} already has an @AccessMode annotation.`
      );
      return false;
    }
  }

  // Ensure the AccessMode import exists
  const edit = new vscode.WorkspaceEdit();

  if (!text.includes("import") || !text.includes("AccessMode")) {
    // Find the last import statement and add after it
    const importPattern = /^import\s+[^;]+;/gm;
    let lastImportEnd = -1;
    let match: RegExpExecArray | null;
    while ((match = importPattern.exec(text)) !== null) {
      lastImportEnd = match.index + match[0].length;
    }
    if (lastImportEnd > 0) {
      const importPos = doc.positionAt(lastImportEnd);
      edit.insert(
        uri,
        new vscode.Position(importPos.line + 1, 0),
        "import giis.visualassert.portable.AccessMode;\n"
      );
    }
  }

  // Insert the annotation
  edit.insert(
    uri,
    new vscode.Position(insertLine, 0),
    annotationLine + "\n"
  );

  const success = await vscode.workspace.applyEdit(edit);
  if (success) {
    // Save the file
    const editor = await vscode.window.showTextDocument(doc);
    await editor.document.save();
  }

  return success;
}

/**
 * Apply all suggestions sequentially.
 */
export async function applyAllSuggestions(
  suggestions: Suggestion[]
): Promise<number> {
  let applied = 0;
  for (const s of suggestions) {
    if (await applySuggestion(s)) {
      applied++;
    }
  }
  return applied;
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
