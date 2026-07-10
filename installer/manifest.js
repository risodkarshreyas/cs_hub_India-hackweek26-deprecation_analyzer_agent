const fs = require("node:fs");
const path = require("node:path");

function parseFrontmatter(text) {
  const match = text.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n/);
  if (!match) {
    throw new Error("SKILL.md must start with YAML frontmatter");
  }

  const metadata = {};
  for (const rawLine of match[1].split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }
    const separator = line.indexOf(":");
    if (separator === -1) {
      continue;
    }
    const key = line.slice(0, separator).trim();
    let value = line.slice(separator + 1).trim();
    value = value.replace(/^["']|["']$/g, "");
    metadata[key] = value;
  }

  return metadata;
}

function readSkillManifest(sourceDir) {
  const skillPath = path.join(sourceDir, "SKILL.md");
  if (!fs.existsSync(skillPath)) {
    throw new Error(`Missing required file: ${skillPath}`);
  }

  const metadata = parseFrontmatter(fs.readFileSync(skillPath, "utf8"));
  if (!metadata.name) {
    throw new Error("SKILL.md frontmatter must include name");
  }
  if (!/^[a-z0-9-]+$/.test(metadata.name)) {
    throw new Error(`Invalid skill name: ${metadata.name}`);
  }
  if (!metadata.description) {
    throw new Error("SKILL.md frontmatter must include description");
  }

  return {
    name: metadata.name,
    description: metadata.description,
    skillPath,
  };
}

function validateSkillSource(sourceDir) {
  const manifest = readSkillManifest(sourceDir);
  for (const required of ["scripts", "references"]) {
    const requiredPath = path.join(sourceDir, required);
    if (!fs.existsSync(requiredPath) || !fs.statSync(requiredPath).isDirectory()) {
      throw new Error(`Missing required directory: ${requiredPath}`);
    }
  }
  return manifest;
}

module.exports = {
  parseFrontmatter,
  readSkillManifest,
  validateSkillSource,
};
