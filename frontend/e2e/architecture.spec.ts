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
