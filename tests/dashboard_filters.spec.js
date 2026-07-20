const { execFileSync } = require("node:child_process");
const { mkdtempSync, rmSync } = require("node:fs");
const { tmpdir } = require("node:os");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { test, expect } = require("@playwright/test");

let fixtureDirectory;
let dashboardUrl;

test.beforeAll(() => {
  fixtureDirectory = mkdtempSync(path.join(tmpdir(), "uipath-dashboard-filter-"));
  const dashboardPath = path.join(fixtureDirectory, "dashboard.html");
  execFileSync(
    process.platform === "win32" ? "python.exe" : "python3",
    [path.join(__dirname, "render_dashboard_browser_fixture.py"), dashboardPath],
    { stdio: "inherit" },
  );
  dashboardUrl = pathToFileURL(dashboardPath).href;
});

test.afterAll(() => {
  rmSync(fixtureDirectory, { recursive: true, force: true });
});

test("filters all ranked findings with AND semantics and an accessible empty state", async ({ page }) => {
  await page.goto(dashboardUrl);

  const rows = page.locator("#top-findings-table tbody tr.finding-row");
  const visibleRows = page.locator("#top-findings-table tbody tr.finding-row:visible");
  const status = page.locator("#findings-filter-status");
  const emptyState = page.locator("#findings-empty-state");
  const severity = page.locator("#findings-severity-filter");
  const product = page.locator("#findings-product-filter");
  const route = page.locator("#findings-route-filter");

  await expect(rows).toHaveCount(12);
  await expect(visibleRows).toHaveCount(12);
  await expect(status).toHaveText("Showing 12 of 12 findings");
  await expect(emptyState).toBeHidden();

  await severity.selectOption("critical");
  await expect(visibleRows).toHaveCount(4);
  await expect(status).toHaveText("Showing 4 of 12 findings");

  await severity.selectOption("");
  await product.selectOption("orchestrator");
  await expect(visibleRows).toHaveCount(5);

  await product.selectOption("");
  await route.selectOption("uipath-test");
  await expect(visibleRows).toHaveCount(5);

  await severity.selectOption("critical");
  await product.selectOption("orchestrator");
  await expect(visibleRows).toHaveCount(2);
  await expect(status).toHaveText("Showing 2 of 12 findings");

  await severity.selectOption("");
  await product.selectOption("r&d <core>");
  await route.selectOption("owner_review");
  await expect(visibleRows).toHaveCount(1);
  await expect(visibleRows.first()).toContainText("Finding 12");

  await severity.selectOption("low");
  await expect(visibleRows).toHaveCount(0);
  await expect(status).toHaveText("Showing 0 of 12 findings");
  await expect(emptyState).toBeVisible();

  await severity.selectOption("");
  await product.selectOption("");
  await route.selectOption("");
  await expect(visibleRows).toHaveCount(12);
  await expect(status).toHaveText("Showing 12 of 12 findings");
  await expect(emptyState).toBeHidden();
});
