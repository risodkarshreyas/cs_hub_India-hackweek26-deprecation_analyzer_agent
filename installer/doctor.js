const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { validateSkillSource } = require("./manifest");

function commandExists(command, args) {
  const result = spawnSync(command, args, { encoding: "utf8", shell: false });
  return {
    ok: result.status === 0,
    output: (result.stdout || result.stderr || "").trim(),
  };
}

function runDoctor({ sourceDir = path.join(__dirname, "..") } = {}) {
  const checks = [];

  const nodeMajor = Number.parseInt(process.versions.node.split(".")[0], 10);
  checks.push({
    name: "node",
    ok: nodeMajor >= 20,
    message: `Node ${process.versions.node}`,
  });

  try {
    const manifest = validateSkillSource(sourceDir);
    checks.push({
      name: "skill",
      ok: true,
      message: `Found ${manifest.name}`,
    });
  } catch (error) {
    checks.push({
      name: "skill",
      ok: false,
      message: error.message,
    });
  }

  const python = commandExists("python", ["--version"]);
  checks.push({
    name: "python",
    ok: python.ok,
    message: python.output || "python --version failed",
  });

  checks.push({
    name: "package",
    ok: fs.existsSync(path.join(sourceDir, "package.json")),
    message: "package.json present",
  });

  return {
    ok: checks.every((check) => check.ok),
    checks,
  };
}

module.exports = {
  runDoctor,
};
