import { expect, test } from "@playwright/test";

// The core handler journey: queue → case → correct an agent's extraction → decide →
// the correction shows up as an agent quality signal on the dashboard.

test("dashboard shows agent pipeline results", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByText("Awaiting review", { exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "extraction-agent" })).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/dashboard.png", fullPage: true });
});

test("handler corrects extraction, approves, and the override is measured", async ({ page }) => {
  await page.goto("/claims");
  await expect(page.getByRole("heading", { name: "Review queue" })).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/queue.png", fullPage: true });

  // Pick a claim the engine says is covered, so it can be approved.
  const row = page.locator("tr", { has: page.getByText("COVERED", { exact: true }) }).first();
  await row.getByRole("link").click();
  await expect(page.getByRole("heading", { name: "Case brief" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Coverage (deterministic engine)" })).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/case.png", fullPage: true });

  // Correct one extracted field → stored as an "edit" with a field-level correction.
  const extraction = page.locator("section", { has: page.getByRole("heading", { name: "Extracted data" }) });
  await extraction.getByText("Your feedback on this draft").click();
  const total = extraction.locator('input[name="field:total_amount"]');
  await total.fill("1.00");
  await extraction.getByRole("button", { name: "Accept / save corrections" }).click();
  await expect(page.getByText("Feedback on extraction saved (edit)")).toBeVisible();

  // Approve with the engine's payable amount.
  const decision = page.locator("section", { has: page.getByRole("heading", { name: "Your decision" }) });
  await decision.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText(/Claim moved to APPROVED by handler\.novak/)).toBeVisible();
  await expect(page.locator("h1").getByText("APPROVED")).toBeVisible();
  await expect(page.getByText("human:handler.novak")).toBeVisible(); // audit trail

  await page.goto("/");
  const row2 = page.locator("tr", { has: page.getByRole("cell", { name: "extraction-agent" }) });
  await expect(row2.getByRole("cell", { name: "100 %" })).toBeVisible();
  await expect(page.getByText("total_amount × 1")).toBeVisible();
});

test("a rejection without a reason is refused by the core API", async ({ page }) => {
  await page.goto("/claims");
  await page.locator("tbody tr").first().getByRole("link").click();
  const summary = page.locator("section", { has: page.getByRole("heading", { name: "Case brief" }) });
  await summary.getByText("Your feedback on this draft").click();
  await summary.getByRole("button", { name: "Reject draft" }).click();
  await expect(page.getByText("Say what was wrong")).toBeVisible();
});
