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

function parsePythonVersion(output) {
  const match = String(output).match(/Python\s+(\d+)\.(\d+)(?:\.(\d+))?/i);
  if (!match) {
    return null;
  }
  return {
    major: Number.parseInt(match[1], 10),
    minor: Number.parseInt(match[2], 10),
    patch: Number.parseInt(match[3] || "0", 10),
  };
}

function resolvePython(commandChecker = commandExists) {
  for (const command of ["python3", "python"]) {
    const result = commandChecker(command, ["--version"]);
    if (result.ok) {
      return { command, ...result, version: parsePythonVersion(result.output) };
    }
  }
  return null;
}

function runDoctor({ sourceDir = path.join(__dirname, ".."), commandChecker = commandExists } = {}) {
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

  const python = resolvePython(commandChecker);
  const pythonVersionOk =
    python?.version &&
    (python.version.major > 3 || (python.version.major === 3 && python.version.minor >= 10));
  checks.push({
    name: "python",
    ok: Boolean(pythonVersionOk),
    message: python
      ? `${python.command}: ${python.output || "unrecognized version"} (requires Python >= 3.10)`
      : "python3 and python were not found (requires Python >= 3.10)",
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
  parsePythonVersion,
  resolvePython,
  runDoctor,
};
