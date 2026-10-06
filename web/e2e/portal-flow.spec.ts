import { expect, test } from "@playwright/test";

// The customer journey end to end, with the queue worker in the loop:
// quote → buy → report a claim with a document → agents process it in the background →
// a handler asks for more information → the customer answers → agents run again.

const INVOICE = `Faktúra č. 2026-0412
Dodávateľ: Inštalatérstvo Novák s.r.o.
Oprava prasknutého potrubia v kúpeľni a vysušenie podlahy.
Spolu na úhradu: 850,00 EUR
IBAN: SK31 1200 0000 1987 4263 7541`;

test("customer buys a policy and reports a claim that reaches a handler", async ({ page }) => {
  // Quote: the price and every factor come from the core tariff engine.
  await page.goto("/portal/quote?product=HOUSEHOLD");
  await page.getByRole("button", { name: "Calculate price" }).click();
  await page.waitForURL(/calc=1/);
  const price = page.getByRole("region", { name: "Your price" });
  await expect(price).toBeVisible();
  await expect(price.getByText("Insurance tax")).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/portal-quote.png", fullPage: true });

  // Buy.
  await page.getByLabel("First name").fill("Eva");
  await page.getByLabel("Last name").fill("Testová");
  await page.getByLabel("E-mail").fill("eva.testova@example.sk");
  await page.getByRole("button", { name: "Buy policy" }).click();
  await expect(page.getByText("Your policy is active. Welcome!")).toBeVisible();

  // Report a water leak with an invoice.
  await page.getByLabel("What happened?").selectOption("WATER_LEAK");
  await page.getByLabel("Amount you claim (€)").fill("850");
  await page.getByLabel("Describe what happened").fill("Prasknuté potrubie v kúpeľni, voda vytopila podlahu.");
  await page.getByLabel("Documents").setInputFiles({
    name: "faktura.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(INVOICE, "utf-8"),
  });
  await page.getByRole("button", { name: "Submit claim" }).click();
  await expect(page.getByText("Thank you. Your claim was submitted.")).toBeVisible();
  const number = (await page.locator("h1 .font-mono").textContent())!.trim();

  // The upload enqueued a job; the worker runs the pipeline and the page refreshes itself.
  const status = page.getByTestId("claim-status");
  await expect(status).toHaveText("With a claims handler", { timeout: 30_000 });
  await page.screenshot({ path: "e2e/screenshots/portal-claim.png", fullPage: true });

  // The handler sees the same claim, prepared by the agents, and asks for a photo.
  await page.goto("/claims?status=all");
  await page.getByRole("link", { name: number }).click();
  await expect(page.getByRole("heading", { name: "Case brief" })).toBeVisible();
  const decision = page.locator("section", { has: page.getByRole("heading", { name: "Your decision" }) });
  await decision.getByPlaceholder("What do you need from the customer?").fill("Please send a photo of the damage.");
  await decision.getByRole("button", { name: "Request information" }).click();
  await expect(page.getByText(/Claim moved to NEEDS_INFO/)).toBeVisible();

  // Back in the portal: the customer sees the request and answers it.
  await page.goBack();
  await page.goto("/portal");
  await page.getByRole("link", { name: /Household/ }).first().click();
  await page.getByRole("link", { name: new RegExp(number) }).click();
  await expect(status).toHaveText("We need more information");
  await expect(page.getByText("Please send a photo of the damage.")).toBeVisible();
  await page.getByLabel("Send the requested documents").setInputFiles({
    name: "foto-popis.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Fotodokumentácia: mokrá podlaha v kúpeľni, poškodené dlaždice.", "utf-8"),
  });
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page.getByText("Documents received, thank you.")).toBeVisible();

  // Processed again by the agents, back with the handler.
  await expect(status).toHaveText("With a claims handler", { timeout: 30_000 });
});

test("portal pages are scoped to the customer's own policies", async ({ page }) => {
  await page.goto("/claims?status=all");
  const href = await page.locator("tbody tr a").first().getAttribute("href");
  const claimId = href!.split("/").pop();
  const res = await page.goto(`/portal/claims/${claimId}`);
  expect(res?.status()).toBe(404);
});
