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

test("groups, pages, searches, and opens evidence without eagerly rendering every finding", async ({ page }) => {
  await page.goto(dashboardUrl);

  const groupRows = page.locator("#top-findings-table tbody tr.group-row");
  const childRows = page.locator("#top-findings-table tbody tr.child-row");
  const status = page.locator("#findings-filter-status");
  const search = page.locator("#findings-search");
  const product = page.locator("#findings-product-filter");
  const route = page.locator("#findings-route-filter");

  await expect.poll(() => page.locator("#findings-data").evaluate((node) => JSON.parse(node.textContent).length)).toBe(60);
  await expect(groupRows).toHaveCount(25);
  await expect(childRows).toHaveCount(0);
  await expect(status).toHaveText("Showing 60 findings in 30 groups");
  await expect(page.locator("#findings-page-label")).toHaveText("Page 1 of 2");

  await groupRows.first().locator(".expand-button").click();
  await expect(childRows).toHaveCount(2);
  await childRows.first().locator(".evidence-button").click();
  await expect(page.locator("#evidence-drawer")).toHaveClass(/open/);
  await expect(page.locator("#evidence-drawer-body")).toContainText("Evidence");
  await page.keyboard.press("Escape");
  await expect(page.locator("#evidence-drawer")).not.toHaveClass(/open/);

  await search.fill("Finding 30");
  await expect(groupRows).toHaveCount(1);
  await expect(status).toHaveText("Showing 2 findings in 1 group");
  await product.selectOption("r&d <core>");
  await route.selectOption("owner_review");
  await expect(groupRows).toHaveCount(1);
  await expect(groupRows.first()).toContainText("2 versions");

  await search.fill("");
  await product.selectOption("");
  await route.selectOption("");
  await page.locator("#findings-flat-view").click();
  const flatRows = page.locator("#top-findings-table tbody tr.flat-row");
  await expect(flatRows).toHaveCount(25);
  await expect(status).toHaveText("Showing 60 of 60 findings");
  await expect(page.locator("#findings-page-label")).toHaveText("Page 1 of 3");
  await page.locator("#findings-next-page").click();
  await expect(flatRows).toHaveCount(25);
  await page.locator("#findings-next-page").click();
  await expect(flatRows).toHaveCount(10);

  await search.fill("30.0.1");
  await expect(flatRows).toHaveCount(1);
  await expect(flatRows.first()).toContainText("30.0.1");

  const coverageRows = page.locator("#coverage-gaps-table tbody tr:not(.no-filter-results)");
  await expect(coverageRows).toHaveCount(25);
  await expect(page.locator("#coverage-page-label")).toHaveText("Page 1 of 2");
  await page.locator("#coverage-next-page").click();
  await expect(coverageRows).toHaveCount(5);
  await page.locator("#coverage-search").fill("Missing export 30");
  await expect(coverageRows).toHaveCount(1);
});
