const os = require("node:os");
const path = require("node:path");
const { resolveTargets } = require("./agents");
const { copyRuntimeAssets } = require("./copy");
const { validateSkillSource } = require("./manifest");

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
    const plannedFiles = copyRuntimeAssets({
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
  installSkill,
};
