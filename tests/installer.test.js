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

test("copilot adapter is generated as compatibility instructions", () => {
  const { installSkill } = require("../installer/install");
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "skill-installer-"));

  const result = installSkill({
    sourceDir: ROOT,
    agents: ["copilot"],
    env: {},
    homeDir: temp,
  });

  const target = result.installs[0].targetPath;
  const text = fs.readFileSync(target, "utf8");
  assert.match(text, /Compatibility adapter/);
  assert.match(text, /uipath-deprecation-analyzer/);
  assert.match(text, /scripts\/uipath_deprecation_analyzer\.py/);
});
