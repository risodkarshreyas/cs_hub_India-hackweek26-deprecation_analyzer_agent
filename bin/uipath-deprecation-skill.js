#!/usr/bin/env node

const path = require("node:path");
const { installSkill } = require("../installer/install");
const { runDoctor } = require("../installer/doctor");

function printHelp() {
  console.log(`UiPath Deprecation Analyzer Skill Installer

Usage:
  uipath-deprecation-skill install [--agent <codex|claude|copilot|all>] [--dry-run] [--force]
  uipath-deprecation-skill doctor
  uipath-deprecation-skill help

Options:
  --agent <name>   Target agent. Repeatable. Defaults to detected agents.
  --dry-run        Show planned writes without changing files.
  --force          Replace an existing installed skill target.
  --strict         Fail instead of warning when no install targets are available.
  --source <path>  Source skill folder. Defaults to this package root.
`);
}

function parseArgs(argv) {
  const args = {
    command: argv[0] || "help",
    agents: [],
    dryRun: false,
    force: false,
    strict: false,
    sourceDir: path.resolve(__dirname, ".."),
  };

  for (let index = 1; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--agent") {
      const agent = argv[index + 1];
      if (!agent) {
        throw new Error("--agent requires a value");
      }
      args.agents.push(agent);
      index += 1;
    } else if (value === "--dry-run") {
      args.dryRun = true;
    } else if (value === "--force") {
      args.force = true;
    } else if (value === "--strict") {
      args.strict = true;
    } else if (value === "--source") {
      const source = argv[index + 1];
      if (!source) {
        throw new Error("--source requires a value");
      }
      args.sourceDir = path.resolve(source);
      index += 1;
    } else {
      throw new Error(`Unknown option: ${value}`);
    }
  }

  return args;
}

function main() {
  const args = parseArgs(process.argv.slice(2));

  if (args.command === "help" || args.command === "--help" || args.command === "-h") {
    printHelp();
    return 0;
  }

  if (args.command === "doctor") {
    const result = runDoctor({ sourceDir: args.sourceDir });
    for (const check of result.checks) {
      console.log(`${check.ok ? "ok" : "fail"} ${check.name}: ${check.message}`);
    }
    return result.ok ? 0 : 1;
  }

  if (args.command === "install") {
    const result = installSkill({
      sourceDir: args.sourceDir,
      agents: args.agents,
      dryRun: args.dryRun,
      force: args.force,
      strict: args.strict,
    });

    if (result.installs.length === 0) {
      console.log("No install targets were selected.");
      return args.strict ? 1 : 0;
    }

    for (const item of result.installs) {
      const action = args.dryRun ? "Would install" : "Installed";
      console.log(`${action} ${item.agent} ${item.mode} at ${item.targetPath}`);
    }
    return 0;
  }

  throw new Error(`Unknown command: ${args.command}`);
}

try {
  process.exitCode = main();
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
