const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { resolveTargets } = require("./agents");
const { copyRuntimeAssets } = require("./copy");
const { validateSkillSource } = require("./manifest");

function buildCopilotAdapter(manifest) {
  return `# UiPath Deprecation Analyzer Compatibility adapter

This file adapts the \`${manifest.name}\` skill instructions for coding agents that do not expose a native SKILL.md global registry.

When the user asks to analyze UiPath deprecation risk, use the installed skill folder and follow its SKILL.md instructions. The deterministic analyzer entrypoint is:

\`\`\`bash
python scripts/uipath_deprecation_analyzer.py --input <path> --output <reports> --mode auto --format markdown,json,html
\`\`\`

Always load \`references/common_analysis_rules.md\` before producing findings. Load route-specific references from the skill only when relevant.
`;
}

function writeAdapter({ targetPath, manifest, dryRun = false, force = false }) {
  if (fs.existsSync(targetPath) && !force) {
    throw new Error(`Install target already exists: ${targetPath}. Use --force to replace it.`);
  }

  if (!dryRun) {
    fs.mkdirSync(path.dirname(targetPath), { recursive: true });
    fs.writeFileSync(targetPath, buildCopilotAdapter(manifest), "utf8");
  }

  return [targetPath];
}

function installSkill({
  sourceDir,
  agents = [],
  env = process.env,
  homeDir = os.homedir(),
  dryRun = false,
  force = false,
  strict = false,
} = {}) {
  const root = path.resolve(sourceDir || path.join(__dirname, ".."));
  const manifest = validateSkillSource(root);
  const targets = resolveTargets({ agents, env, homeDir, skillName: manifest.name });

  if (targets.length === 0) {
    if (strict) {
      throw new Error("No supported coding agents detected. Rerun with --agent <name>.");
    }
    return { manifest, installs: [] };
  }

  const installs = targets.map((target) => {
    const plannedFiles =
      target.agent === "copilot"
        ? writeAdapter({ targetPath: target.targetPath, manifest, dryRun, force })
        : copyRuntimeAssets({
            sourceDir: root,
            targetPath: target.targetPath,
            skillName: manifest.name,
            dryRun,
            force,
          });

    return {
      ...target,
      plannedFiles,
    };
  });

  return { manifest, installs };
}

module.exports = {
  buildCopilotAdapter,
  installSkill,
};
