import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const { chromium } = await import(
  process.env.PLAYWRIGHT_MODULE || "playwright"
);
const baseURL = process.env.WILLOW_BASE_URL;
if (!baseURL)
  throw new Error(
    "Run this test through pytest so it uses an isolated test database.",
  );
const output = process.env.WILLOW_TEST_OUTPUT || "test-results";
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  channel: process.env.BROWSER_CHANNEL || "chrome",
});
const page = await browser.newPage({
  viewport: { width: 1440, height: 1000 },
  reducedMotion: "reduce",
});
page.setDefaultTimeout(12000);
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
const email = `browser-${Date.now()}@example.com`;
const password = "Browser-test-123";

try {
  await page.goto(baseURL, { waitUntil: "networkidle" });
  assert.match(await page.locator('[data-price="Classic"]').innerText(), /100/);
  await page.evaluate(() => {
    for (const image of document.images) image.loading = "eager";
  });
  await page.waitForFunction(() =>
    [...document.images].every(
      (image) => image.complete && image.naturalWidth > 0,
    ),
  );
  await page.screenshot({ path: path.join(output, "desktop.png") });

  await page.locator('[data-gallery="0"]').click();
  await page.locator("#gallery-next").click();
  assert.match(await page.locator("#gallery-caption").innerText(), /Classic/);
  await page.keyboard.press("Escape");
  assert.equal(
    await page.locator("#gallery-dialog").evaluate((element) => element.open),
    false,
  );

  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  assert.equal(
    await page.evaluate(() => document.documentElement.scrollWidth),
    390,
  );
  await page.getByRole("button", { name: "Open menu", exact: true }).click();
  await page
    .locator("#main-nav")
    .getByRole("link", { name: "Rooms & suites" })
    .click();
  assert.equal(
    await page.locator(".menu-toggle").getAttribute("aria-expanded"),
    "false",
  );
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(output, "mobile.png") });
  await page.setViewportSize({ width: 1440, height: 1000 });

  await page
    .getByRole("button", { name: "Check availability", exact: true })
    .click();
  await page.getByRole("heading", { name: "Choose your room." }).waitFor();
  assert.equal(await page.locator(".availability-card").count(), 3);
  await page
    .getByRole("button", { name: "Choose room →", exact: true })
    .first()
    .click();
  await page
    .getByRole("button", { name: "Sign in to reserve", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Create an account", exact: true })
    .click();
  await page.getByLabel("Full name", { exact: true }).fill("Browser Guest");
  await page.getByLabel("Email address", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Confirm reservation", exact: true })
    .waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(
    await page
      .locator("#reservation-dialog")
      .evaluate((element) => element.scrollWidth <= element.clientWidth + 1),
  );
  await page.screenshot({ path: path.join(output, "mobile-reservation.png") });
  await page
    .getByRole("button", { name: "Confirm reservation", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "We have a place for you." })
    .waitFor();
  assert.match(await page.locator(".success-details").innerText(), /Room 101/);
  assert.match(await page.locator(".success-details").innerText(), /200/);
  await page
    .getByRole("button", { name: "View my stays", exact: true })
    .click();
  await page.locator(".booking-item").waitFor();
  assert.equal(await page.locator(".status-tag").textContent(), "confirmed");
  await page
    .getByRole("button", { name: "Cancel reservation", exact: true })
    .click();
  await page.getByRole("button", { name: "Keep my stay", exact: true }).click();
  await page
    .getByRole("button", { name: "Cancel reservation", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Confirm cancellation", exact: true })
    .click();
  await page.locator(".status-tag.cancelled").waitFor();
  await page.screenshot({ path: path.join(output, "mobile-account.png") });
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.locator("#account-dialog").waitFor({ state: "hidden" });
  assert.equal(
    await page.evaluate(() => sessionStorage.getItem("willow.session")),
    null,
  );

  await page.getByRole("button", { name: "Your stay", exact: true }).click();
  await page.getByLabel("Email address", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill("wrong-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByText("Invalid email or password", { exact: true }).waitFor();
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.locator(".status-tag.cancelled").waitFor();
  await page.keyboard.press("Escape");

  await page.evaluate(() => {
    const tokens = JSON.parse(sessionStorage.getItem("willow.session"));
    tokens.access_token = "expired-access-token";
    sessionStorage.setItem("willow.session", JSON.stringify(tokens));
  });
  const refreshed = page.waitForResponse(
    (response) =>
      response.url().endsWith("/auth/refresh") && response.status() === 200,
  );
  await page.reload({ waitUntil: "networkidle" });
  await refreshed;
  await page.getByRole("button", { name: "My stays", exact: true }).waitFor();

  await page.route("**/availability?*", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        detail: "Availability is temporarily unavailable.",
      }),
    }),
  );
  await page
    .getByRole("button", { name: "Check availability", exact: true })
    .click();
  await page
    .getByText("Availability is temporarily unavailable.", { exact: true })
    .waitFor();
  await page.unroute("**/availability?*");
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await page.getByRole("heading", { name: "Choose your room." }).waitFor();
  await page.keyboard.press("Escape");

  await page.setViewportSize({ width: 320, height: 740 });
  assert.equal(
    await page.evaluate(() => document.documentElement.scrollWidth),
    320,
  );
  assert.deepEqual(errors, []);
  console.log(
    "Browser checks passed: desktop/mobile layout, gallery, registration, booking, cancellation, login errors, JWT refresh, network errors and retry.",
  );
} catch (error) {
  await page.screenshot({
    path: path.join(output, "failure.png"),
    fullPage: true,
  });
  throw error;
} finally {
  await browser.close();
}
