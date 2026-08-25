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
 *
 * **Nothing here writes**, and that is a constraint rather than a preference.
 * The first version retracted whichever claim came first and linked whichever
 * nodes came first, against a real graph — and ate eight assertions across a few
 * runs, including the pair a succession was resting on. Seeding a graph of its
 * own needs a route that creates assertions, and none exists.
 *
 * So these check the wiring up to the moment of the write: a confirmation arms
 * and disarms, an ineligible partner is not offered, a row is actually reachable.
 * Every defect this file was written for lived there. What happens *after* the
 * request is the backend suite's job, where the data is disposable.
 */

import { expect, test, type Page } from "@playwright/test";

const KEY = process.env["BACTERIA_KEY"] ?? "";

async function signIn(page: Page): Promise<void> {
  await page.goto("/");
  // The console exchanges a key for a session cookie; a saved session skips it.
  // The console decides *asynchronously* whether a stored session still works,
  // so immediately after `goto` both panels are hidden. Asking "is the key field
  // visible" then answers no, the sign-in is skipped, and every later assertion
  // fails as "#workspace is hidden" — a rendering bug that is really this race.
  await expect(page.locator("#sign-in, #workspace").first()).toBeVisible();

  const field = page.locator("#key");
  if (await field.isVisible().catch(() => false)) {
    await field.fill(KEY);
    await page.locator("#sign-in-form button").click();
  }
  // Wait for the exchange to finish before reaching for a tab. Clicking earlier
  // hits a hidden workspace and fails as "#graph is hidden", which reads like a
  // rendering bug and is a race in this helper.
  await expect(page.locator("#workspace")).toBeVisible();
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

test("an abandoned confirmation resets rather than waiting to catch someone", async ({ page }) => {
  await signIn(page);

  const claims = page.locator("#graph li.node", { has: page.locator("p.claim") });
  test.skip((await claims.count()) === 0, "no claims in this graph");

  // Armed and abandoned, never confirmed, so this one writes nothing.
  const button = claims.first().locator("button.danger");
  await button.click();
  await expect(button).toHaveText("sure?");

  await page.locator("#graph-legend").click();

  await expect(button).toHaveText("retract");
});

function thingsSection(page: Page) {
  return page.locator("#graph section", {
    has: page.getByRole("heading", { name: "Things", exact: true }),
  });
}

/** Row indexes whose node is of the given kind, in render order. */
async function rowsOfKind(page: Page, kind: string): Promise<number[]> {
  const rows = thingsSection(page).locator("li.node");
  const found: number[] = [];
  for (let i = 0; i < (await rows.count()); i++) {
    if ((await rows.nth(i).innerText()).includes(kind)) found.push(i);
  }
  return found;
}

test("a node of another kind cannot be picked as the other half", async ({ page }) => {
  await signIn(page);

  const rows = thingsSection(page).locator("li.node");
  const people = await rowsOfKind(page, "person");
  const others = await rowsOfKind(page, "organization");
  test.skip(people.length === 0 || others.length === 0, "need two kinds present");

  await rows.nth(people[0]!).locator("button").last().click();

  // This is the report that opened the investigation: clicking a second node and
  // seeing nothing happen. It was the API refusing a person-to-organization link
  // and saying so in the legend, six inches from the button. Not offered now.
  await expect(rows.nth(others[0]!).locator("button").last()).toBeDisabled();
  await expect(thingsSection(page)).toContainText("pick another person");
});


test("the other nodes are reachable, not merely present", async ({ page }) => {
  await signIn(page);

  const rows = thingsSection(page).locator("li.node");
  const people = await rowsOfKind(page, "person");
  test.skip(people.length < 2, "fewer than two people");

  await rows.nth(people[0]!).locator("button").last().click();
  // Wait for the redraw before measuring: a box read mid-replace is null, which
  // would fail for a reason that has nothing to do with reachability.
  await expect(thingsSection(page)).toContainText("Linking");

  // Asserted on geometry, because every DOM assertion in this file passed while
  // the section was crammed into one 15rem grid column: the buttons were present
  // and enabled, the labels wrapped to a character per line, and the whole thing
  // was unusable. "Present and enabled" is not "reachable".
  const partner = rows.nth(people[1]!).locator("button").last();
  const box = await partner.boundingBox();

  expect(box).not.toBeNull();
  expect(box!.width).toBeGreaterThan(40);
  expect(box!.height).toBeGreaterThan(12);

  const label = await rows.nth(people[1]!).locator("span.value").boundingBox();
  expect(label!.width).toBeGreaterThan(30);
});
