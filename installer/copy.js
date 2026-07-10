const fs = require("node:fs");
const path = require("node:path");

const RUNTIME_ENTRIES = ["SKILL.md", "agents", "references", "scripts", "assets"];
const EXCLUDED_NAMES = new Set([
  ".git",
  ".venv",
  "venv",
  "__pycache__",
  "node_modules",
  "tests",
  "reports",
  "dist",
  "build",
]);

function shouldExclude(name) {
  return EXCLUDED_NAMES.has(name) || name.endsWith(".pyc") || name.endsWith(".pyo");
}

function listRuntimeFiles(sourceDir) {
  const files = [];

  function visit(relativePath) {
    const absolutePath = path.join(sourceDir, relativePath);
    if (!fs.existsSync(absolutePath)) {
      return;
    }
    const name = path.basename(relativePath);
    if (shouldExclude(name)) {
      return;
    }
    const stat = fs.statSync(absolutePath);
    if (stat.isDirectory()) {
      for (const child of fs.readdirSync(absolutePath)) {
        visit(path.join(relativePath, child));
      }
    } else if (stat.isFile()) {
      files.push(relativePath);
    }
  }

  for (const entry of RUNTIME_ENTRIES) {
    visit(entry);
  }

  return files.sort();
}

function assertSafeTarget(targetPath, skillName) {
  if (path.basename(targetPath) !== skillName) {
    throw new Error(`Refusing to replace unexpected target: ${targetPath}`);
  }
}

function copyRuntimeAssets({ sourceDir, targetPath, skillName, dryRun = false, force = false }) {
  const plannedFiles = listRuntimeFiles(sourceDir).map((relativePath) => path.join(targetPath, relativePath));

  if (fs.existsSync(targetPath)) {
    if (!force) {
      throw new Error(`Install target already exists: ${targetPath}. Use --force to replace it.`);
    }
    assertSafeTarget(targetPath, skillName);
    if (!dryRun) {
      fs.rmSync(targetPath, { recursive: true, force: true });
    }
  }

  if (dryRun) {
    return plannedFiles;
  }

  for (const relativePath of listRuntimeFiles(sourceDir)) {
    const from = path.join(sourceDir, relativePath);
    const to = path.join(targetPath, relativePath);
    fs.mkdirSync(path.dirname(to), { recursive: true });
    fs.copyFileSync(from, to);
  }

  return plannedFiles;
}

module.exports = {
  RUNTIME_ENTRIES,
  copyRuntimeAssets,
  listRuntimeFiles,
};
