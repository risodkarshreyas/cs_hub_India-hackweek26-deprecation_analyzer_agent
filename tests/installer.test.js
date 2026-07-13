const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const ROOT = path.resolve(__dirname, "..");

test("parses the skill manifest from SKILL.md", () => {
  const { readSkillManifest } = require("../installer/manifest");

  const manifest = readSkillManifest(ROOT);

  assert.equal(manifest.name, "uipath-deprecation-analyzer");
  assert.match(manifest.description, /UiPath deprecation risk/);
});

test("resolves Codex target from CODEX_HOME before home fallback", () => {
  const { resolveTargets } = require("../installer/agents");
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "skill-installer-"));
  const codexHome = path.join(temp, "custom-codex");

  const targets = resolveTargets({
    agents: ["codex"],
    env: { CODEX_HOME: codexHome },
    homeDir: path.join(temp, "home"),
    skillName: "uipath-deprecation-analyzer",
  });

  assert.equal(targets.length, 1);
  assert.equal(
    targets[0].targetPath,
    path.join(codexHome, "skills", "uipath-deprecation-analyzer"),
  );
});

test("detects Copilot from COPILOT_HOME or the default home directory", () => {
  const { detectAgents } = require("../installer/agents");
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "skill-installer-"));
  const defaultHome = path.join(temp, "default-home");
  fs.mkdirSync(path.join(defaultHome, ".copilot"), { recursive: true });

  assert.deepEqual(detectAgents({ env: {}, homeDir: defaultHome }), ["copilot"]);
  assert.deepEqual(
    detectAgents({ env: { COPILOT_HOME: path.join(temp, "custom-copilot") }, homeDir: temp }),
    ["copilot"],
  );
});

test("resolves Copilot native skill target from COPILOT_HOME", () => {
  const { resolveTargets } = require("../installer/agents");
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "skill-installer-"));
  const copilotHome = path.join(temp, "custom-copilot");

  const [target] = resolveTargets({
    agents: ["copilot"],
    env: { COPILOT_HOME: copilotHome },
    homeDir: path.join(temp, "home"),
    skillName: "uipath-deprecation-analyzer",
  });

  assert.equal(target.mode, "native skill");
  assert.equal(target.targetPath, path.join(copilotHome, "skills", "uipath-deprecation-analyzer"));
});

test("dry-run install reports writes without creating files", () => {
  const { installSkill } = require("../installer/install");
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "skill-installer-"));
  const codexHome = path.join(temp, "codex");

  const result = installSkill({
    sourceDir: ROOT,
    agents: ["codex"],
    env: { CODEX_HOME: codexHome },
    homeDir: path.join(temp, "home"),
    dryRun: true,
  });

  assert.equal(result.installs.length, 1);
  assert.equal(result.installs[0].agent, "codex");
  assert.equal(fs.existsSync(codexHome), false);
  assert.ok(result.installs[0].plannedFiles.some((file) => file.endsWith("SKILL.md")));
});

test("dry-run previews an existing install without requiring force", () => {
  const { installSkill } = require("../installer/install");
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "skill-installer-"));
  const codexHome = path.join(temp, "codex");
  const options = {
    sourceDir: ROOT,
    agents: ["codex"],
    env: { CODEX_HOME: codexHome },
    homeDir: path.join(temp, "home"),
  };

  installSkill(options);
  const skillPath = path.join(codexHome, "skills", "uipath-deprecation-analyzer", "SKILL.md");
  const before = fs.readFileSync(skillPath, "utf8");
  const preview = installSkill({ ...options, dryRun: true });

  assert.ok(preview.installs[0].plannedFiles.includes(skillPath));
  assert.equal(fs.readFileSync(skillPath, "utf8"), before);
});

test("install copies runtime assets and excludes development artifacts", () => {
  const { installSkill } = require("../installer/install");
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "skill-installer-"));
  const codexHome = path.join(temp, "codex");

  const result = installSkill({
    sourceDir: ROOT,
    agents: ["codex"],
    env: { CODEX_HOME: codexHome },
    homeDir: path.join(temp, "home"),
  });

  const target = result.installs[0].targetPath;
  assert.equal(fs.existsSync(path.join(target, "SKILL.md")), true);
  assert.equal(fs.existsSync(path.join(target, "scripts", "uipath_deprecation_analyzer.py")), true);
  assert.equal(fs.existsSync(path.join(target, "references", "common_analysis_rules.md")), true);
  assert.equal(fs.existsSync(path.join(target, "agents", "openai.yaml")), true);
  assert.equal(fs.existsSync(path.join(target, "tests")), false);
  assert.equal(fs.existsSync(path.join(target, ".git")), false);
});

test("existing install requires force before replacement", () => {
  const { installSkill } = require("../installer/install");
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "skill-installer-"));
  const codexHome = path.join(temp, "codex");
  const options = {
    sourceDir: ROOT,
    agents: ["codex"],
    env: { CODEX_HOME: codexHome },
    homeDir: path.join(temp, "home"),
  };

  installSkill(options);
  assert.throws(() => installSkill(options), /already exists/);

  const forced = installSkill({ ...options, force: true });
  assert.equal(fs.existsSync(path.join(forced.installs[0].targetPath, "SKILL.md")), true);
});

test("Copilot install copies the complete native skill", () => {
  const { installSkill } = require("../installer/install");
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "skill-installer-"));

  const result = installSkill({
    sourceDir: ROOT,
    agents: ["copilot"],
    env: {},
    homeDir: temp,
  });

  const target = result.installs[0].targetPath;
  assert.equal(target, path.join(temp, ".copilot", "skills", "uipath-deprecation-analyzer"));
  assert.equal(fs.existsSync(path.join(target, "SKILL.md")), true);
  assert.equal(fs.existsSync(path.join(target, "scripts", "uipath_deprecation_analyzer.py")), true);
  assert.equal(fs.existsSync(path.join(target, "references", "common_analysis_rules.md")), true);
});

test("doctor prefers python3 and accepts Python 3.10 or newer", () => {
  const { runDoctor } = require("../installer/doctor");
  const calls = [];
  const result = runDoctor({
    sourceDir: ROOT,
    commandChecker(command) {
      calls.push(command);
      return { ok: true, output: "Python 3.10.0" };
    },
  });

  assert.deepEqual(calls, ["python3"]);
  assert.equal(result.checks.find((check) => check.name === "python").ok, true);
});

test("doctor falls back to python and rejects versions older than 3.10", () => {
  const { runDoctor } = require("../installer/doctor");
  const calls = [];
  const result = runDoctor({
    sourceDir: ROOT,
    commandChecker(command) {
      calls.push(command);
      return command === "python3"
        ? { ok: false, output: "" }
        : { ok: true, output: "Python 3.9.18" };
    },
  });

  assert.deepEqual(calls, ["python3", "python"]);
  const pythonCheck = result.checks.find((check) => check.name === "python");
  assert.equal(pythonCheck.ok, false);
  assert.match(pythonCheck.message, /Python 3\.9\.18/);
});
