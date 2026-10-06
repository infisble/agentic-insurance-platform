import { defineConfig } from "@playwright/test";

// E2E: a fresh demo database (seeded, offline pipeline) on :8100 and the CRM on :3100.
// Relative to the repository root, which is the cwd of the core API web server below.
const python = process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  use: { baseURL: "http://localhost:3100", viewport: { width: 1500, height: 1000 } },
  webServer: [
    {
      command: `${python} -m aip.demo --db var/e2e.db --port 8100`,
      cwd: "..",
      url: "http://localhost:8100/health",
      timeout: 180_000,
      reuseExistingServer: false,
    },
    {
      command: "npx next dev -p 3100",
      env: { CORE_API_URL: "http://localhost:8100" },
      url: "http://localhost:3100",
      timeout: 180_000,
      reuseExistingServer: false,
    },
  ],
});
