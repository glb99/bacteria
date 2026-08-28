/**
 * The architecture surface: a conversation column, and a scene it scopes.
 *
 * Hand-rolled SVG, no layout library. The console has exactly one runtime
 * dependency and dialogue 10 decided a graph-drawing package runs hard against
 * that grain — so the layering below is forty lines rather than a bundle.
 *
 * **Packages, not modules.** A repository of a hundred modules and two hundred
 * imports drawn plainly is a hairball, and the boundaries are stated *about*
 * packages, so that is the level the scene works at. Modules are what the
 * conversation column resolves against.
 *
 * The left column is not the agent yet. It scopes the scene by name and says
 * so; wiring it to a model is the next slice. A column that answered in
 * sentences it had made up would be worse than one that admits its range.
 */

import {
  addProject,
  askAbout,
  judgeClassification,
  listProjects,
  readArchitecture,
  runTests,
  type ArchBoundary,
  type ArchCrossing,
  type ArchProposal,
  type ArchitectureModel,
  type Project,
} from "./api";
import { el, text } from "./dom";

const selector = el<HTMLSelectElement>("arch-project");
const addButton = el<HTMLButtonElement>("arch-add");
const counts = el("arch-counts");
const tallies = el("arch-tallies");
const thread = el("arch-thread");
const form = el<HTMLFormElement>("arch-form");
const input = el<HTMLInputElement>("arch-input");
const svgHost = el("arch-svg");
const boundaryList = el("arch-boundaries");
const proposalList = el("arch-proposals");
const verdicts = el("arch-verdicts");
const runTestsButton = el<HTMLButtonElement>("arch-run-tests");
const readingPill = el("arch-reading");

const SVG = "http://www.w3.org/2000/svg";

let model: ArchitectureModel | null = null;
let scope: string | null = null;

// ---------------------------------------------------------------- packages

interface Pkg {
  name: string;
  modules: number;
  tables: number;
  layer: number;
  x: number;
  y: number;

  /**
   * What somebody said this package is, and whether they have said it yet.
   *
   * The scene used to pick a glyph from `tables > 0` -- a *derived* property --
   * so a package you had agreed was a feature looked identical to one you had
   * rejected. The only knowledge anybody contributed reached the cards and
   * never the picture, which is backwards for a surface whose whole argument is
   * that stated and derived facts must not be drawn alike.
   *
   * `claim` is what the classifier proposes; `verdict` is null while nobody has
   * ruled. Rejection returns a package to unclassified rather than to some third
   * shape, because disagreeing that it is a feature says nothing about what it
   * is instead.
   */
  claim: string | null;
  verdict: string | null;
}

interface Edge {
  from: string;
  to: string;
  weight: number;
  deferred: boolean;
  crossed: boolean;
}

const packageOf = (moduleName: string, packages: Set<string>): string => {
  // The longest known package that is a prefix. A module's own `package` field
  // is its immediate parent, which for a deep tree draws thirty boxes where the
  // repository has six.
  let best = moduleName;
  for (const candidate of packages) {
    if (
      (moduleName === candidate || moduleName.startsWith(candidate + ".")) &&
      candidate.length > (best === moduleName ? 0 : best.length)
    ) {
      best = candidate;
    }
  }
  return best;
};

/**
 * The packages worth drawing: the shallowest level that gives a readable count.
 *
 * Depth is chosen rather than fixed because repositories differ. `bacteria.app`
 * has its features two segments down; a flat project has everything at one. The
 * rule is the first depth that yields more than two groups, capped so a very
 * wide repository still fits.
 */
function chooseGroups(names: string[]): Set<string> {
  for (let depth = 1; depth <= 4; depth += 1) {
    const groups = new Set(names.map((n) => n.split(".").slice(0, depth).join(".")));
    if (groups.size > 2 && groups.size <= 18) return groups;
  }
  return new Set(names.map((n) => n.split(".").slice(0, 3).join(".")));
}

function build(current: ArchitectureModel): { packages: Pkg[]; edges: Edge[] } {
  const names = current.modules.map((m) => m.name);
  const groups = chooseGroups(names);

  // Classifications are proposed about packages by their full dotted name. The
  // scene groups at whatever depth reads well, so the two agree for most
  // repositories and not for all -- a package the scene drew at a different
  // depth simply has no classification, which is honest rather than a guess.
  const said = new Map(
    current.proposals
      .filter((p) => p.claim !== "role")
      .map((p) => [p.subject, { claim: p.claim, verdict: p.verdict ?? null }]),
  );

  const byGroup = new Map<string, { modules: number; tables: number }>();
  for (const module of current.modules) {
    const group = packageOf(module.name, groups);
    const entry = byGroup.get(group) ?? { modules: 0, tables: 0 };
    entry.modules += 1;
    entry.tables += module.tables.length;
    byGroup.set(group, entry);
  }

  const crossed = new Set(current.crossings.map((c) => `${c.src}\u0000${c.dst}`));
  const edgeMap = new Map<string, Edge>();
  for (const edge of current.imports) {
    const from = packageOf(edge.src, groups);
    const to = packageOf(edge.dst, groups);
    if (from === to) continue;
    const key = `${from}\u0000${to}`;
    const existing = edgeMap.get(key);
    const isCrossed = crossed.has(`${edge.src}\u0000${edge.dst}`);
    if (existing) {
      existing.weight += 1;
      existing.deferred = existing.deferred && edge.deferred;
      existing.crossed = existing.crossed || isCrossed;
    } else {
      edgeMap.set(key, {
        from,
        to,
        weight: 1,
        deferred: edge.deferred,
        crossed: isCrossed,
      });
    }
  }

  const edges = [...edgeMap.values()];
  const layers = layerOf([...byGroup.keys()], edges);

  const packages: Pkg[] = [...byGroup.entries()].map(([name, entry]) => ({
    name,
    modules: entry.modules,
    tables: entry.tables,
    layer: layers.get(name) ?? 0,
    x: 0,
    y: 0,
    claim: said.get(name)?.claim ?? null,
    verdict: said.get(name)?.verdict ?? null,
  }));

  place(packages, edges);
  return { packages, edges };
}

/**
 * How deep a package sits, by longest path along its dependencies.
 *
 * Iterative relaxation with a bound rather than a topological sort, because a
 * real codebase has cycles and a sort would either refuse or need a
 * cycle-breaking pass. The bound is what stops a cycle spinning; the cost of
 * being wrong inside one is that two mutually-dependent packages land on the
 * same band, which is the honest picture anyway.
 */
function layerOf(names: string[], edges: Edge[]): Map<string, number> {
  const depth = new Map(names.map((n) => [n, 0]));
  for (let pass = 0; pass < Math.min(names.length, 12); pass += 1) {
    let moved = false;
    for (const edge of edges) {
      const next = (depth.get(edge.from) ?? 0) + 1;
      if (next > (depth.get(edge.to) ?? 0)) {
        depth.set(edge.to, next);
        moved = true;
      }
    }
    if (!moved) break;
  }
  return depth;
}

const WIDTH = 1000;
const BOX = 116;

function place(packages: Pkg[], edges: Edge[]): void {
  const bands = new Map<number, Pkg[]>();
  for (const pkg of packages) {
    const band = bands.get(pkg.layer) ?? [];
    band.push(pkg);
    bands.set(pkg.layer, band);
  }

  const rows = [...bands.keys()].sort((a, b) => b - a);
  rows.forEach((layer, row) => {
    const band = (bands.get(layer) ?? []).sort((a, b) => b.modules - a.modules);
    spread(band, 90 + row * 150);
  });

  // Ordering within a band decides how many edges cross, and sorting by size
  // ignores the graph entirely -- the first version drew nineteen packages as a
  // hairball because a package sat wherever its module count put it, however far
  // that was from everything it imports.
  //
  // Barycentre passes: repeatedly move each package to the average x of its
  // neighbours, then re-space the band. The classic Sugiyama heuristic, five
  // lines of it, and enough. Alternating direction matters -- sweeping one way
  // only settles the layers it sweeps toward.
  const neighbours = new Map<string, string[]>();
  for (const edge of edges) {
    (neighbours.get(edge.from) ?? neighbours.set(edge.from, []).get(edge.from)!).push(edge.to);
    (neighbours.get(edge.to) ?? neighbours.set(edge.to, []).get(edge.to)!).push(edge.from);
  }
  const at = new Map(packages.map((p) => [p.name, p]));

  for (let pass = 0; pass < 6; pass += 1) {
    const order = pass % 2 === 0 ? rows : [...rows].reverse();
    for (const layer of order) {
      const band = bands.get(layer) ?? [];
      for (const pkg of band) {
        const linked = (neighbours.get(pkg.name) ?? [])
          .map((name) => at.get(name))
          .filter((other): other is Pkg => other !== undefined && other.layer !== pkg.layer);
        if (linked.length === 0) continue;
        pkg.x = linked.reduce((total, other) => total + other.x, 0) / linked.length;
      }
      band.sort((a, b) => a.x - b.x);
      spread(band, band[0]?.y ?? 0);
    }
  }
}

/** Even spacing across the scene, keeping the order the caller settled on. */
function spread(band: Pkg[], y: number): void {
  const span = WIDTH / (band.length + 1);
  band.forEach((pkg, index) => {
    pkg.x = span * (index + 1);
    pkg.y = y;
  });
}

// ------------------------------------------------------------------ drawing

const node = (name: string, attrs: Record<string, string | number>): SVGElement => {
  const element = document.createElementNS(SVG, name);
  for (const [key, value] of Object.entries(attrs)) {
    element.setAttribute(key, String(value));
  }
  return element;
};

function draw(packages: Pkg[], edges: Edge[]): void {
  const rows = Math.max(...packages.map((p) => p.y), 200) + 130;
  const svg = node("svg", {
    viewBox: `0 0 ${WIDTH} ${rows}`,
    width: "100%",
    height: "100%",
    role: "img",
    "aria-label": "package dependency scene",
  });

  const at = new Map(packages.map((p) => [p.name, p]));
  const lit = (name: string) => scope === null || name === scope || name.startsWith(scope + ".");

  for (const edge of edges) {
    const from = at.get(edge.from);
    const to = at.get(edge.to);
    if (!from || !to) continue;
    const on = lit(edge.from) || lit(edge.to);
    const cls = edge.crossed ? "crossed" : edge.deferred ? "deferred" : "beam";
    svg.appendChild(
      node("path", {
        d: `M${from.x} ${from.y + 18} C${from.x} ${from.y + 70} ${to.x} ${to.y - 70} ${to.x} ${to.y - 18}`,
        class: `arch-edge ${cls}${on ? "" : " dim"}`,
        "stroke-width": Math.min(0.8 + edge.weight * 0.22, 3),
      }),
    );
  }

  for (const pkg of packages) {
    // Shape carries what was *stated*, line style carries whether anybody has
    // agreed to it, and the text below carries what was *derived*. Splitting it
    // that way is the whole point: the picture stops describing the parser and
    // starts describing the model people are building.
    const agreed = pkg.verdict === "agreed";
    const shape = agreed ? pkg.claim : pkg.verdict === null && pkg.claim ? pkg.claim : null;
    const group = node("g", {
      class:
        `arch-glyph ${shape ?? "unclassified"}` +
        `${agreed ? " agreed" : shape ? " proposed" : ""}` +
        `${lit(pkg.name) ? "" : " dim"}`,
      // The full dotted name, which the visible label does not carry -- it
      // shows only the last segment. Anything that needs to find one glyph
      // rather than count all of them needs this.
      "data-package": pkg.name,
    });
    const width = Math.min(BOX, 62 + pkg.modules * 3);

    if (shape === "feature") {
      // A drum: something that holds its own state and is bounded.
      for (const offset of [10, 0, -10]) {
        group.appendChild(
          node("ellipse", { cx: pkg.x, cy: pkg.y + offset, rx: width / 2, ry: 8 }),
        );
      }
      group.appendChild(
        node("path", {
          d: `M${pkg.x - width / 2} ${pkg.y - 10} v20 M${pkg.x + width / 2} ${pkg.y - 10} v20`,
        }),
      );
    } else if (shape === "layer") {
      // A slab: wide, flat, and drawn as something other things rest on.
      const wide = width + 26;
      group.appendChild(
        node("rect", { x: pkg.x - wide / 2, y: pkg.y - 11, width: wide, height: 22, rx: 2 }),
      );
      group.appendChild(
        node("path", {
          d: `M${pkg.x - wide / 2} ${pkg.y + 11} h${wide} M${pkg.x - wide / 2} ${pkg.y + 15} h${wide}`,
        }),
      );
    } else {
      // Nothing has been said about it -- including a package whose
      // classification was rejected, which returns it here rather than to some
      // third shape. Smaller and plainer, so the scene reads as mostly
      // unjudged, which it is.
      group.appendChild(
        node("rect", { x: pkg.x - width / 2, y: pkg.y - 11, width, height: 22, rx: 2 }),
      );
    }

    const label = node("text", { x: pkg.x, y: pkg.y - 26, "text-anchor": "middle" });
    label.textContent = pkg.name.split(".").pop() ?? pkg.name;
    group.appendChild(label);

    const sub = node("text", {
      x: pkg.x,
      y: pkg.y + (shape === "feature" ? 40 : 32),
      "text-anchor": "middle",
      class: "sub",
    });
    // The derived facts move to the text now that the shape is spoken for.
    // Nothing is lost -- table ownership was only ever legible here anyway.
    sub.textContent = pkg.tables > 0 ? `${pkg.modules} · ${pkg.tables} tables` : `${pkg.modules}`;
    group.appendChild(sub);

    group.addEventListener("click", () => {
      scope = scope === pkg.name ? null : pkg.name;
      say(scope ? `scoped to ${scope}` : "showing everything", describe(scope));
      render();
    });
    svg.appendChild(group);
  }

  svgHost.replaceChildren(svg);
}

// -------------------------------------------------------------- the column

function say(question: string, answer: HTMLElement): void {
  const asked = text("div", question, "arch-said");
  thread.append(asked, answer);
  thread.scrollTop = thread.scrollHeight;
}

function describe(name: string | null): HTMLElement {
  const wrap = document.createElement("div");
  wrap.className = "arch-answer";
  if (!model) return wrap;

  if (name === null) {
    wrap.append(text("p", `${model.modules.length} modules, ${model.imports.length} imports.`));
    return wrap;
  }

  const inside = model.modules.filter((m) => m.name === name || m.name.startsWith(name + "."));
  const out = model.imports.filter((i) => inside.some((m) => m.name === i.src));
  const into = model.imports.filter((i) => inside.some((m) => m.name === i.dst));
  wrap.append(
    text(
      "p",
      `${inside.length} module(s). Reaches out ${out.length} time(s), reached into ${into.length}.`,
    ),
  );

  const crossings = model.crossings.filter(
    (c) => inside.some((m) => m.name === c.src) || inside.some((m) => m.name === c.dst),
  );
  for (const crossing of crossings) {
    wrap.appendChild(
      card("crossed", crossing.boundary, crossingLine(crossing)),
    );
  }
  return wrap;
}

/**
 * One finding, as a sentence naming the relation it actually broke.
 *
 * Both call sites said "imports" whatever the finding was, so a table declared
 * in the wrong package read as `core.db:0 imports chat_session` — a dependency
 * that does not exist, described in a relation that was not the one broken. The
 * API carries `rel` now precisely so this can be right.
 *
 * `line` is dropped when it is zero: the offence is a declaration rather than a
 * statement, and `:0` invites somebody to go looking for a line that is not
 * there.
 */
function crossingLine(crossing: ArchCrossing): string {
  const where = crossing.line > 0 ? `${crossing.src}:${crossing.line}` : crossing.src;
  return `${where} ${crossing.rel} ${crossing.dst}`;
}

function card(state: string, title: string, detail: string): HTMLElement {
  const box = document.createElement("div");
  box.className = `arch-card ${state}`;
  box.append(text("p", title, "arch-card-title"), text("p", detail, "arch-card-detail"));
  return box;
}

// ------------------------------------------------------------------ render

function render(): void {
  if (!model) return;
  const { packages, edges } = build(model);
  draw(packages, edges);

  counts.textContent =
    `${model.modules.length} modules · ${packages.length} packages · ` +
    `${model.tables.length} tables · ${model.imports.length} imports · ` +
    `roots ${model.roots.join(", ")}`;

  const tally = (state: string) => model!.boundaries.filter((b) => b.state === state).length;
  tallies.replaceChildren(
    ...[
      ["crossed", tally("crossed")],
      ["holds", tally("holds")],
      ["undecidable", tally("undecidable")],
      ["n/a", tally("inapplicable")],
    ]
      .filter(([, n]) => (n as number) > 0)
      .map(([state, n]) => text("span", `${n} ${String(state).toUpperCase()}`, `arch-pill ${state}`)),
  );

  boundaryList.replaceChildren(...model.boundaries.map(boundaryCard));
  proposalList.replaceChildren(...model.proposals.map(proposalCard));
  countVerdicts();
}

/**
 * A proposal, drawn as the uncertain thing it is.
 *
 * Dashed and unfilled, borrowing the console's existing convention for a claim
 * nothing has ratified. It matters here more than it does next door: every
 * other mark on this surface is a fact read off the syntax, so a proposal drawn
 * like one would be trusted like one.
 *
 * `because` is shown rather than hidden behind a disclosure. A person asked to
 * agree with a computation has to be able to see it, and a proposal folded away
 * is one that gets approved unread.
 */
/**
 * How many proposals have been agreed with, disagreed with, and not yet judged.
 *
 * Not decoration. The open question about this whole surface is whether a
 * person actually contests what is proposed or waves it through — a review
 * everyone approves is worse than no review, because everyone believes it was
 * checked. This is that number, and it belongs where the proposals are rather
 * than in a report nobody opens.
 *
 * Three counts and not two: *not yet judged* and *judged no* are different
 * states, and only the second says anything about the thesis.
 */
function countVerdicts(): void {
  if (!model) return;
  const agreed = model.proposals.filter((p) => p.verdict === "agreed").length;
  const against = model.proposals.filter((p) => p.verdict === "disagreed").length;
  const open = model.proposals.length - agreed - against;
  verdicts.textContent = `${agreed} agreed · ${against} disagreed · ${open} open`;
}

function proposalCard(proposal: ArchProposal): HTMLElement {
  const box = document.createElement("div");
  box.className = `arch-card proposed ${proposal.verdict ?? ""}`;
  box.append(
    text("p", proposal.sentence, "arch-card-title"),
    text("p", proposal.because, "arch-card-detail"),
  );

  if (proposal.verdict) {
    // A judged proposal keeps its place in the list rather than disappearing.
    // Hiding what somebody rejected would leave the surface unable to show that
    // anything was ever rejected, which is the one number it exists to produce.
    box.append(
      text(
        "p",
        `${proposal.verdict} by ${proposal.stated_by ?? "someone"}`,
        "arch-card-note",
      ),
    );
  }

  const acts = document.createElement("div");
  acts.className = "arch-acts";
  for (const verdict of ["agreed", "disagreed"] as const) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `arch-act tiny${proposal.verdict === verdict ? " on" : ""}`;
    button.textContent = verdict === "agreed" ? "agree" : "disagree";
    button.addEventListener("click", async () => {
      if (!model) return;
      // Repainted from the reply rather than from a re-read: the answer already
      // carries the verdict, and re-fetching the model would re-parse the whole
      // tree to learn one word.
      const judged = await judgeClassification(
        model.project.project_id,
        proposal.subject,
        proposal.claim,
        verdict,
      );
      const index = model.proposals.findIndex(
        (p) => p.subject === proposal.subject && p.claim === proposal.claim,
      );
      if (index >= 0) model.proposals[index] = judged;
      // A full redraw, not just this card. Replacing the card alone left the
      // scene showing the classification as still proposed while the tally said
      // it was agreed -- the picture and the count disagreeing about the same
      // click, which is worse than either being wrong on its own.
      render();
    });
    acts.append(button);
  }
  box.append(acts);
  return box;
}

function boundaryCard(boundary: ArchBoundary): HTMLElement {
  const box = document.createElement("div");
  box.className = `arch-card ${boundary.state}`;
  box.append(text("p", boundary.sentence, "arch-card-title"));

  if (boundary.state === "undecidable" && boundary.elsewhere) {
    box.append(text("p", `no import can settle this — checked by: ${boundary.elsewhere}`, "arch-card-detail"));
  } else if (boundary.state === "inapplicable") {
    box.append(text("p", "about code this repository does not have", "arch-card-detail"));
  } else if (boundary.state === "crossed" && model) {
    for (const crossing of model.crossings.filter((c) => c.boundary === boundary.name)) {
      box.append(
        text("p", crossingLine(crossing), "arch-card-detail"),
      );
    }
    // Deliberately not offered yet: accepting a crossing writes to the log, and
    // that route does not exist. A button that only looked like it recorded a
    // decision would be worse than none.
    box.append(text("p", "accepting a crossing is not built", "arch-card-note"));
  }
  return box;
}

// -------------------------------------------------------------------- shell

async function load(projectId: string): Promise<void> {
  model = await readArchitecture(projectId);
  scope = null;
  thread.replaceChildren();
  // A reading belongs to the moment it was taken, so opening a project shows
  // "not checked" rather than whatever was true the last time anybody looked.
  readingPill.textContent = "not checked";
  readingPill.className = "arch-pill";
  // Enabled only once there is a project to probe. It used to be clickable
  // immediately, and the handler returned silently when no model had loaded
  // yet -- "nothing happened", which is the worst thing a control can do
  // because it is indistinguishable from working.
  runTestsButton.disabled = false;
  say(`opened ${model.project.name}`, describe(null));
  render();
}

export async function refresh(): Promise<void> {
  const projects: Project[] = await listProjects();
  selector.replaceChildren(
    ...projects.map((project) => {
      const option = document.createElement("option");
      option.value = project.project_id;
      option.textContent = project.name;
      return option;
    }),
  );

  if (projects.length === 0) {
    counts.textContent = "no projects — add a checkout to begin";
    runTestsButton.disabled = true;
    readingPill.textContent = "not checked";
    svgHost.replaceChildren();
    boundaryList.replaceChildren();
    thread.replaceChildren();
    model = null;
    return;
  }

  const chosen = selector.value || projects[0]!.project_id;
  selector.value = chosen;
  await load(chosen);
}

selector.addEventListener("change", () => {
  void load(selector.value);
});

addButton.addEventListener("click", async () => {
  // `prompt` rather than a modal: this is a console for whoever runs the
  // server, the value is a path on their own machine, and a dialog would be
  // more code than the thing it collects.
  const location = window.prompt("path to a checkout on this machine");
  if (!location) return;
  // Asked once, here, and never taken from a request afterwards. The probe that
  // runs it reads the project row; a route that accepted a command would be
  // remote code execution with extra steps.
  const command = window.prompt("command to run its tests (optional)") ?? "";
  await addProject(location, "", command);
  await refresh();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const asked = input.value.trim();
  if (!asked || !model) return;
  input.value = "";

  // Scope first, from the question itself, so the scene has moved before the
  // model has answered. A name in the question is a scope the person meant even
  // when the answer takes four seconds to arrive.
  const match =
    model.modules.find((m) => m.name === asked) ??
    model.modules.find((m) => m.name.endsWith("." + asked)) ??
    model.modules.find((m) => m.name.includes(asked));
  if (match) {
    scope = match.name.split(".").slice(0, -1).join(".") || match.name;
    render();
  }

  const pending = text("p", "…", "arch-answer");
  say(asked, pending);

  try {
    const answer = await askAbout(model.project.project_id, asked);
    const wrap = document.createElement("div");
    wrap.className = "arch-answer";
    wrap.append(text("p", answer.reply));

    // Which tools it used, because an answer read off the parse and one
    // invented from a plausible package name look identical. An empty list is
    // the signal to distrust the reply, and hiding it removes the only way to
    // tell.
    const provenance =
      answer.tools_used.length > 0
        ? `read: ${answer.tools_used.join(", ")}`
        : "answered without reading anything — treat with suspicion";
    wrap.append(text("p", provenance, "arch-card-note"));

    if (answer.refused.length > 0) {
      // The gate saying no, out loud. Normally empty; non-empty means a model
      // reached for something this surface does not offer.
      wrap.append(
        text("p", `refused: ${answer.refused.join(", ")}`, "arch-card-note"),
      );
    }
    pending.replaceWith(wrap);
  } catch (error) {
    pending.replaceWith(text("p", `could not answer — ${String(error)}`, "arch-answer"));
  }
});

runTestsButton.addEventListener("click", async () => {
  if (!model) return;
  runTestsButton.disabled = true;
  readingPill.textContent = "running…";
  readingPill.className = "arch-pill";
  try {
    const reading = await runTests(model.project.project_id);
    readingPill.textContent = reading.state;
    readingPill.className = `arch-pill ${reading.state}`;
    // Answered in the conversation as well as in the pill, because the pill
    // says a word and the output says what broke -- and a failing suite is only
    // actionable if somebody can read the tail of it.
    const answer = document.createElement("div");
    answer.className = "arch-answer";
    answer.append(text("p", reading.detail));
    if (reading.output) answer.append(text("pre", reading.output, "arch-output"));
    answer.append(
      text("p", "a reading, not a belief — nothing was written down", "arch-card-note"),
    );
    say("run tests", answer);
  } finally {
    runTestsButton.disabled = false;
  }
});
