import { defineConfig, devices } from "@playwright/test";
import { execSync } from "node:child_process";

/**
 * Playwright config — points at the already-running vite dev server.
 *
 * Usage:
 *   # Backend services + vite must already be running (make dev or equivalent)
 *   npx playwright test
 *   npx playwright test --headed   # see the browser
 *   npx playwright test e2e/chat.spec.ts -g "revenue"
 *
 * Screenshots and traces land in test-results/ on failure; explicit
 * page.screenshot() calls land in .playwright/screenshots/ for ad-hoc probes.
 *
 * ## Port detection
 *
 * Vite normally binds 5173 but falls back to 5174/5175/etc. if the canonical
 * port is occupied (e.g. a stale dev server in another worktree). We probe
 * common candidates at startup and pick whichever serves Lumen's index.html.
 * Override with `LUMEN_BASE_URL=http://localhost:NNNN` if needed.
 */
function detectViteUrl(): string {
  const override = process.env.LUMEN_BASE_URL;
  if (override) return override;
  const candidates = [5173, 5174, 5175, 5176];
  for (const port of candidates) {
    try {
      const body = execSync(
        `curl -s -m 2 http://localhost:${port}/ 2>/dev/null`,
        { encoding: "utf8" },
      );
      // A live vite serves index.html (~600 bytes, contains `id="root"`
      // and the @vite/client tag). The dead-vite collision returns a
      // 404 with 0 bytes. Check both signatures.
      if (
        body.length > 200 &&
        body.includes('id="root"') &&
        body.includes("@vite/client")
      ) {
        if (port !== 5173) {
          // eslint-disable-next-line no-console
          console.log(
            `[playwright] Vite detected on port ${port} (5173 is occupied by something else)`,
          );
        }
        return `http://localhost:${port}`;
      }
    } catch {
      // port not listening; try next
    }
  }
  // eslint-disable-next-line no-console
  console.warn(
    "[playwright] No Lumen vite server found on 5173–5176; defaulting to 5173. Start `make dev` first or set LUMEN_BASE_URL.",
  );
  return "http://localhost:5173";
}

const BASE_URL = detectViteUrl();

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    viewport: { width: 1280, height: 800 },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
