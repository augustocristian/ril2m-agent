/**
 * Types shared across the VS Code extension.
 */

/** A single annotation suggestion returned by the agent CLI. */
export interface Suggestion {
  class: string;
  method: string;
  file: string;
  suggested_annotation: string;
  confidence: number;
  reasoning: string;
}

/** Full JSON output from `ril2m analyze --json`. */
export interface AnalyzeResult {
  suggestions: Suggestion[];
  pr_url: string;
  errors: string[];
}

/** JSON output from `ril2m analyze --json --pr`. */
export interface PrResult {
  suggestions: Suggestion[];
  pr_url: string;
  errors: string[];
}
