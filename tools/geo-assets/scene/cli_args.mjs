import { accessSync, constants, existsSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export function isExecutable(p) {
  try {
    accessSync(p, constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

export function resolveChrome() {
  if (process.env.CHROME && isExecutable(process.env.CHROME)) return process.env.CHROME;
  const exe = process.platform === "win32" ? "chrome-headless-shell.exe" : "chrome-headless-shell";
  const base = join(homedir(), ".cache", "puppeteer", "chrome-headless-shell");
  if (existsSync(base)) {
    for (const v of readdirSync(base).sort().reverse()) {
      try {
        for (const inner of readdirSync(join(base, v))) {
          const bin = join(base, v, inner, exe);
          if (isExecutable(bin)) return bin;
        }
      } catch {
        /* ignore */
      }
    }
  }
  for (const c of [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
  ]) {
    if (isExecutable(c)) return c;
  }
  throw new Error("Executable Chrome / chrome-headless-shell not found.");
}

export function parseArgs(argv) {
  const args = {};
  const onlyActs = [];
  for (let i = 2; i < argv.length; i++) {
    const k = argv[i];
    if (!k.startsWith("--")) continue;
    const name = k.slice(2);
    const val = i + 1 < argv.length && !argv[i + 1].startsWith("--") ? argv[++i] : true;
    if (name === "only-act") {
      if (typeof val === "string") {
        for (const part of val.split(",")) {
          const trimmed = part.trim();
          if (trimmed) onlyActs.push(trimmed);
        }
      }
      continue;
    }
    args[name] = val;
  }
  if (onlyActs.length > 0) args["only-act"] = onlyActs;
  return args;
}

