/**
 * The console's write affordances, exercised by something that actually clicks.
 *
 * **Three defects in one session were reachable only this way**: a tab that did
 * nothing, a confirmation that could be armed forever and never fired, and a
 * two-click link. All three were event wiring — the one thing a type checker
 * cannot see and `just smoke` never looked at, because it asserts the console is
 * *served* rather than that it works.
 *
 * Written against a running server rather than starting one, so it is the same
 * process a person is looking at when they report something. `just e2e` supplies
 * the key.
 */

import { expect, test, type Page } from "@playwright/test";

const KEY = process.env["BACTERIA_KEY"] ?? "";

async function signIn(page: Page): Promise<void> {
  await page.goto("/");
  // The console exchanges a key for a session cookie; a saved session skips it.
  const field = page.locator("#key");
  if (await field.isVisible().catch(() => false)) {
    await field.fill(KEY);
    await page.locator("#sign-in-form button").click();
  }
  await page.locator('[data-tab="graph"]').click();
  await expect(page.locator("#graph")).toBeVisible();
}

test("the graph tab renders rather than failing silently", async ({ page }) => {
  await signIn(page);

  // The first defect: the panel switched and `refresh` threw into an async
  // handler, so the page looked empty and the reason went to a console nobody
  // was reading.
  await expect(page.locator("#graph-legend")).toContainText("things");
});

test("retract asks once and then acts", async ({ page }) => {
  await signIn(page);

  const claims = page.locator("#graph li.node", { has: page.locator("p.claim") });
  const before = await claims.count();
  test.skip(before === 0, "no claims in this graph to retract");

  // Located by class rather than by text, because the text is what changes.
  // Filtering on "retract" made the armed button unfindable and the failure read
  // as "the click did nothing" — which is the very report this test exists for.
  const button = claims.first().locator("button.danger");
  await button.click();

  // Armed, not fired.
  await expect(button).toHaveText("sure?");
  await expect(claims).toHaveCount(before);

  // The second defect: a `document` listener registered with `capture: true`
  // disarmed this on the way down, so the confirming click re-armed instead of
  // acting and the claim could never be retracted.
  await button.click();
  await expect(claims).toHaveCount(before - 1);
});

test("an abandoned confirmation resets rather than waiting to catch someone", async ({ page }) => {
  await signIn(page);

  const claims = page.locator("#graph li.node", { has: page.locator("p.claim") });
  test.skip((await claims.count()) === 0, "no claims in this graph");

  const button = claims.first().locator("button.danger");
  await button.click();
  await expect(button).toHaveText("sure?");

  await page.locator("#graph-legend").click();

  await expect(button).toHaveText("retract");
});

test("linking takes two clicks on two nodes", async ({ page }) => {
  await signIn(page);

  const things = page.locator("#graph section", {
    has: page.getByRole("heading", { name: "Things", exact: true }),
  });
  const rows = things.locator("li.node");
  test.skip((await rows.count()) < 2, "fewer than two nodes to link");

  // The last button on the row: its label alternates between "same as…" and
  // "picked", so anything matching on text stops matching the moment it is used.
  await rows.nth(0).locator("button").last().click();

  // The pending half is the only state on this page a person cannot otherwise
  // see, so it has to be named.
  await expect(things).toContainText("Linking");

  await rows.nth(1).locator("button").last().click();

  // Either a link was written, or the API refused for a reason it stated. Both
  // are outcomes; silence is not.
  await expect(async () => {
    const linked = await page.locator("#graph .claim", { hasText: "same_as" }).count();
    const reported = await page.locator("#graph-legend .failed").count();
    expect(linked + reported).toBeGreaterThan(0);
  }).toPass({ timeout: 5000 });
});
