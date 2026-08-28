/**
 * The architecture surface, exercised by something that actually clicks.
 *
 * The scene is built by hand out of SVG, and every failure mode it has is one
 * a type checker cannot see: an empty `<svg>`, a layout that stacks every
 * package on one point, a click listener attached to a node that was replaced.
 * `just check-all` builds this file's module and never renders it.
 *
 * Written against a running server, like `graph.spec.ts`, so it is the same
 * process a person is looking at. `just e2e` supplies the key.
 *
 * **Read-only.** The only write this surface has is adding a project, which
 * takes a path from a `window.prompt` and would leave a row behind in whatever
 * database the run pointed at. The scoping, the scene and the boundary cards are
 * where every defect this file was written for lives.
 */

import { expect, test, type Page } from "@playwright/test";

const KEY = process.env["BACTERIA_KEY"] ?? "";

async function openArchitecture(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.locator("#sign-in, #workspace").first()).toBeVisible();

  const field = page.locator("#key");
  if (await field.isVisible().catch(() => false)) {
    await field.fill(KEY);
    await page.locator("#sign-in-form button").click();
  }
  await expect(page.locator("#workspace")).toBeVisible();

  await page.locator('#tabs button[data-tab="architecture"]').click();
  await expect(page.locator("#tab-architecture")).toBeVisible();
}

test.describe("architecture", () => {
  test.skip(!KEY, "needs BACTERIA_KEY and a project already added");

  test("the scene draws a package per glyph, not one pile", async ({ page }) => {
    await openArchitecture(page);

    const glyphs = page.locator("#arch-svg .arch-glyph");
    await expect(glyphs.first()).toBeVisible();
    expect(await glyphs.count()).toBeGreaterThan(2);

    // Distinct positions. A layout bug that put every package at the same point
    // still renders a plausible-looking scene, and counting glyphs would pass.
    const xs = await page.locator("#arch-svg .arch-glyph text").evaluateAll((nodes) =>
      nodes.map((n) => (n as SVGTextElement).getAttribute("x")),
    );
    expect(new Set(xs).size).toBeGreaterThan(2);
  });

  test("every boundary is shown, including the ones nothing can decide", async ({ page }) => {
    await openArchitecture(page);

    const cards = page.locator("#arch-boundaries .arch-card");
    await expect(cards.first()).toBeVisible();

    // The undecidable ones are the point: a surface listing only what it could
    // check reads as a clean bill of health over questions nothing asked.
    await expect(page.locator("#arch-boundaries .arch-card.undecidable").first()).toBeVisible();
  });

  test("asking for a package scopes the scene", async ({ page }) => {
    await openArchitecture(page);
    await expect(page.locator("#arch-svg .arch-glyph").first()).toBeVisible();

    await page.locator("#arch-input").fill("graph");
    await page.locator("#arch-form button").click();

    // Something answered, and the scene dimmed everything else. Asserting only
    // that a reply appeared would pass while the scene ignored the scope.
    await expect(page.locator(".arch-answer").last()).toBeVisible();
    await expect(page.locator("#arch-svg .arch-glyph.dim").first()).toBeVisible();
  });

  test("clicking a package scopes, and clicking it again clears", async ({ page }) => {
    await openArchitecture(page);
    const first = page.locator("#arch-svg .arch-glyph").first();
    await expect(first).toBeVisible();

    await first.click();
    await expect(page.locator("#arch-svg .arch-glyph.dim").first()).toBeVisible();

    // Redrawn on every scope change, so the listener has to survive its own
    // node being replaced -- which is exactly the wiring an e2e run catches and
    // a build does not.
    await page.locator("#arch-svg .arch-glyph").first().click();
    await expect(page.locator("#arch-svg .arch-glyph.dim")).toHaveCount(0);
  });
});

test.describe("judging a proposal", () => {
  test.skip(!KEY, "needs BACTERIA_KEY and a project already added");

  test("agreeing and disagreeing both stick, and both are counted", async ({ page }) => {
    await openArchitecture(page);
    const cards = page.locator("#arch-proposals .arch-card");
    await expect(cards.first()).toBeVisible();

    await cards.first().locator("button", { hasText: "agree" }).first().click();
    await expect(page.locator("#arch-proposals .arch-card.agreed").first()).toBeVisible();

    await cards.nth(1).locator("button", { hasText: "disagree" }).click();
    await expect(page.locator("#arch-proposals .arch-card.disagreed").first()).toBeVisible();

    // The tally is the number this whole surface exists to produce: a review
    // everyone approves is worse than no review. Asserting the cards changed
    // without asserting the count would miss a tally that never updates.
    await expect(page.locator("#arch-verdicts")).toContainText("disagreed");
  });

  test("agreeing repaints the scene, not only the card", async ({ page }) => {
    await openArchitecture(page);
    await expect(page.locator("#arch-svg .arch-glyph").first()).toBeVisible();

    // A *feature*, not whatever card is first. The first is usually a role — a
    // claim about a word rather than a package — and a role correctly has no
    // glyph, so agreeing to one moves nothing.
    const card = page
      .locator("#arch-proposals .arch-card")
      .filter({ hasText: "is a feature" })
      .first();
    const title = (await card.locator(".arch-card-title").textContent()) ?? "";
    const subject = title.replace(" is a feature", "").trim();

    // Asserted on this one glyph rather than on a count of them. These tests
    // write, and they share a database with each other — `graph.spec.ts` says
    // why that matters, having eaten eight assertions once. A delta over all
    // glyphs passed alone and failed in the suite, because a sibling test
    // judged something else at the same time.
    const glyph = page.locator(`#arch-svg .arch-glyph[data-package="${subject}"]`);
    await expect(glyph).toHaveCount(1);

    await card.locator("button", { hasText: "disagree" }).click();
    await expect(glyph).not.toHaveClass(/agreed/);

    // The whole sentence, not the subject alone. A role card lists its evidence
    // as module names, so `hasText: "bacteria.app.architecture"` matched a role
    // proposal first and agreed to that instead — the click landed, the tally
    // moved, and the glyph correctly did not.
    await page
      .locator("#arch-proposals .arch-card")
      .filter({ hasText: `${subject} is a feature` })
      .first()
      .locator("button", { hasText: "agree" })
      .first()
      .click();

    // The scene used to keep drawing the classification as still proposed while
    // the tally said it was agreed — the picture and the count disagreeing
    // about the same click, which is worse than either being wrong alone.
    await expect(glyph).toHaveClass(/agreed/);
  });

  test("a rejected proposal keeps its place in the list", async ({ page }) => {
    await openArchitecture(page);
    const first = page.locator("#arch-proposals .arch-card").first();
    await expect(first).toBeVisible();
    const before = await page.locator("#arch-proposals .arch-card").count();

    await first.locator("button", { hasText: "disagree" }).click();
    await expect(page.locator("#arch-proposals .arch-card.disagreed").first()).toBeVisible();

    // Vanishing on rejection would leave the surface unable to show that
    // anything was ever rejected.
    expect(await page.locator("#arch-proposals .arch-card").count()).toBe(before);
  });
});

test.describe("running the tests", () => {
  test.skip(!KEY, "needs BACTERIA_KEY and a project with a test command");

  test("a reading appears and is marked as a reading", async ({ page }) => {
    await openArchitecture(page);
    // Wait for the model, not merely the panel. Clicking sooner used to do
    // nothing at all, which is how the button's missing disabled state was
    // found — by a test that failed for the right reason.
    await expect(page.locator("#arch-svg .arch-glyph").first()).toBeVisible();
    await expect(page.locator("#arch-run-tests")).toBeEnabled();

    await page.locator("#arch-run-tests").click();

    // Up to ten minutes is allowed server-side; a real suite here is seconds.
    await expect(page.locator("#arch-reading")).not.toHaveText("not checked", {
      timeout: 60_000,
    });

    // The state is a word, but the output is what somebody acts on — and the
    // note is what stops it being read as something the model now believes.
    await expect(page.locator(".arch-output").last()).toBeVisible();
    await expect(page.locator(".arch-answer").last()).toContainText("not a belief");
  });
});
