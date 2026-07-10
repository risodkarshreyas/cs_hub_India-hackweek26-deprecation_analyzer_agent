const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const SUPPORTED_AGENTS = new Set(["codex", "claude", "copilot"]);

function normalizeAgents(agents) {
  if (!agents || agents.length === 0) {
    return [];
  }

  const normalized = [];
  for (const item of agents) {
    for (const agent of String(item).split(",")) {
      const trimmed = agent.trim().toLowerCase();
      if (!trimmed) {
        continue;
      }
      if (trimmed === "all") {
        return Array.from(SUPPORTED_AGENTS);
      }
      if (!SUPPORTED_AGENTS.has(trimmed)) {
        throw new Error(`Unsupported agent: ${trimmed}`);
      }
      if (!normalized.includes(trimmed)) {
        normalized.push(trimmed);
      }
    }
  }
  return normalized;
}

function detectAgents({ env = process.env, homeDir = os.homedir() } = {}) {
  const detected = [];
  if (env.CODEX_HOME || fs.existsSync(path.join(homeDir, ".codex"))) {
    detected.push("codex");
  }
  if (fs.existsSync(path.join(homeDir, ".claude"))) {
    detected.push("claude");
  }
  return detected;
}

function resolveTargets({ agents = [], env = process.env, homeDir = os.homedir(), skillName }) {
  const selected = normalizeAgents(agents);
  const resolvedAgents = selected.length > 0 ? selected : detectAgents({ env, homeDir });

  return resolvedAgents.map((agent) => {
    if (agent === "codex") {
      const codexRoot = env.CODEX_HOME || path.join(homeDir, ".codex");
      return {
        agent,
        mode: "native skill",
        targetPath: path.join(codexRoot, "skills", skillName),
      };
    }

    if (agent === "claude") {
      return {
        agent,
        mode: "native skill",
        targetPath: path.join(homeDir, ".claude", "skills", skillName),
      };
    }

    return {
      agent,
      mode: "compatibility adapter",
      targetPath: path.join(homeDir, ".config", "uipath-deprecation-skill", "copilot", `${skillName}.md`),
    };
  });
}

module.exports = {
  SUPPORTED_AGENTS,
  detectAgents,
  normalizeAgents,
  resolveTargets,
};
