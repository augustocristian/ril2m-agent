/**
 * Client that spawns the ril2m Python CLI and parses its JSON output.
 */

import { spawn } from "child_process";
import * as vscode from "vscode";
import { AnalyzeResult, PrResult } from "./types";

/**
 * Build the command + args to invoke the ril2m CLI.
 */
function getCommand(): { cmd: string; baseArgs: string[] } {
  const config = vscode.workspace.getConfiguration("ril2m");
  const pythonPath = config.get<string>("pythonPath", "python");
  const agentPath = config.get<string>("agentPath", "");

  if (agentPath) {
    // Run as a module from the agent project directory
    return { cmd: pythonPath, baseArgs: ["-m", "agent.cli"] };
  }
  // Assume ril2m is installed and on PATH
  return { cmd: "ril2m", baseArgs: [] };
}

/**
 * Build environment variables to forward Ollama settings to the agent.
 */
function getEnv(): NodeJS.ProcessEnv {
  const config = vscode.workspace.getConfiguration("ril2m");
  return {
    ...process.env,
    OLLAMA_BASE_URL: config.get<string>("ollamaBaseUrl", "http://localhost:11434"),
    OLLAMA_LLM_MODEL: config.get<string>("ollamaModel", "llama3.2"),
    OLLAMA_EMBED_MODEL: config.get<string>("ollamaEmbedModel", "nomic-embed-text"),
  };
}

/**
 * Run a ril2m CLI command and return parsed JSON.
 */
function runCli<T>(args: string[], cwd: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const { cmd, baseArgs } = getCommand();
    const config = vscode.workspace.getConfiguration("ril2m");
    const agentPath = config.get<string>("agentPath", "");
    const spawnCwd = agentPath || cwd;

    const proc = spawn(cmd, [...baseArgs, ...args], {
      cwd: spawnCwd,
      env: getEnv(),
      shell: true,
    });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (data: Buffer) => {
      stdout += data.toString();
    });

    proc.stderr.on("data", (data: Buffer) => {
      stderr += data.toString();
    });

    proc.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(`ril2m exited with code ${code}:\n${stderr}`));
        return;
      }
      try {
        // The JSON output may be preceded by Rich markup — find the first '{'
        const jsonStart = stdout.indexOf("{");
        if (jsonStart === -1) {
          reject(new Error(`No JSON in ril2m output:\n${stdout}`));
          return;
        }
        const json = stdout.substring(jsonStart);
        resolve(JSON.parse(json) as T);
      } catch (e) {
        reject(new Error(`Failed to parse ril2m JSON output:\n${stdout}`));
      }
    });

    proc.on("error", (err) => {
      reject(
        new Error(
          `Failed to start ril2m (is it installed?):\n${err.message}`
        )
      );
    });
  });
}

/**
 * Analyze a Maven project and return annotation suggestions.
 */
export async function analyzeProject(
  projectPath: string
): Promise<AnalyzeResult> {
  return runCli<AnalyzeResult>(
    ["analyze", projectPath, "--json", "--log-level", "WARNING"],
    projectPath
  );
}

/**
 * Analyze a Maven project, apply annotations, and create a GitHub PR.
 */
export async function analyzeAndCreatePR(
  projectPath: string
): Promise<PrResult> {
  return runCli<PrResult>(
    ["analyze", projectPath, "--json", "--pr", "--log-level", "WARNING"],
    projectPath
  );
}
