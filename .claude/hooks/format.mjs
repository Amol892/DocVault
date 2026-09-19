// PostToolUse hook: auto-format files Claude just edited. Never blocks (always exits 0).
import { spawnSync } from "node:child_process";
import { relative, resolve } from "node:path";

let raw = "";
for await (const chunk of process.stdin) raw += chunk;

try {
  const file = JSON.parse(raw)?.tool_input?.file_path;
  if (!file) process.exit(0);
  const root = resolve(process.env.CLAUDE_PROJECT_DIR ?? process.cwd());
  const rel = relative(root, resolve(file)).replaceAll("\\", "/");
  if (rel.startsWith("backend/") && rel.endsWith(".py")) {
    spawnSync("uv", ["run", "ruff", "format", rel.slice("backend/".length)], {
      cwd: `${root}/backend`,
      stdio: "ignore",
      shell: true,
    });
  } else if (rel.startsWith("frontend/src/") && /\.(tsx?|css|json)$/.test(rel)) {
    spawnSync("pnpm", ["exec", "prettier", "--write", rel.slice("frontend/".length)], {
      cwd: `${root}/frontend`,
      stdio: "ignore",
      shell: true,
    });
  }
} catch {
  // formatting is best-effort
}
process.exit(0);
