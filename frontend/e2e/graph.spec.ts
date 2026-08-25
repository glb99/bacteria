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

test("linking takes two clicks on two nodes", async ({ page }) => {
  await signIn(page);

  const things = thingsSection(page);
  const rows = things.locator("li.node");
  const people = await rowsOfKind(page, "person");
  test.skip(people.length < 2, "fewer than two people to link");

  // The last button on the row: its label alternates between "same as…" and
  // "picked", so anything matching on text stops matching the moment it is used.
  await rows.nth(people[0]!).locator("button").last().click();

  // The pending half is the only state on this page a person cannot otherwise
  // see, so it has to be named.
  await expect(things).toContainText("Linking");

  // Asserted on the request rather than on a row count, and both earlier
  // versions of this line were wrong in instructive ways. Asserting a `same_as`
  // claim *existed* passed without the click doing anything, because one already
  // did. Counting rows then failed whenever the pair was already linked, since
  // restating a believed claim is correctly not written again. What the click
  // owes is a successful call.
  const posted = page.waitForResponse(
    (r) => r.url().includes("/graph/links") && r.request().method() === "POST",
  );

  await rows.nth(people[1]!).locator("button").last().click();

  expect((await posted).status()).toBe(201);
  await expect(things).not.toContainText("Linking");
});

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
