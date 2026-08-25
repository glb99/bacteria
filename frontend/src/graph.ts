/**
 * The graph tab: relationships the agent extracted, and what disagrees with what.
 *
 * **This drew derived edges until phase two shipped.** There was no relation
 * table, so every line came from splitting a memory key on its first underscore
 * and was labelled on the page as computed at read time — because presenting a
 * derived edge as an extracted one would have made the graph look finished and
 * quietly answered the question phase two existed to ask.
 *
 * That question now has an answer. `graph_assertion` holds extracted relations
 * with two time axes, `GET /graph` serves them, and the prefix heuristic is
 * gone. Memory entries and proposals are not drawn here any more either: the
 * chat tab already reviews them, and a screen mixing confirmed key/value facts
 * with extracted relations would be two different graphs stacked on one canvas.
 *
 * What is drawn is what a person has to be able to contest:
 *
 * - a **claim**, with whether it is still true, where it came from, and why
 * - a **contradiction**, with the rule that found it and how sure that rule is
 * - a **conclusion**, with the claims underneath it and whether they still hold
 *
 * Nothing here writes. The routes to retract a claim or reject a conclusion do
 * not exist yet, so this is a viewer rather than the negotiation surface it is
 * meant to become — and a button that looked like it did something would be
 * worse than its absence.
 */

import {
  readConclusions,
  readGraph,
  type GraphAssertion,
  type GraphConclusion,
  type GraphConflict,
  type GraphNode,
} from "./api";
import { el, text, when } from "./dom";

type Layout = "subject" | "relation";

const canvas = el<HTMLDivElement>("graph");
const legend = el("graph-legend");
const verdict = el("graph-verdict");
const layoutButtons = el<HTMLDivElement>("graph-layout");

let layout: Layout = "subject";

/**
 * Where trust is reported, and why it is not on the claim.
 *
 * It was a tag on every row, and it was the same value on every row: attribution
 * is per transcript slice, and after the first turn essentially every slice
 * contains an assistant turn, so everything reads `third-party`. A label that
 * never varies is not information — it is a word a reader has to learn in order
 * to discover it means nothing to them.
 *
 * So it is counted in the diagnostics instead, where a constant is a *finding*:
 * the tier is inert, which is an open question in the design rather than
 * something a person looking at their own memory needs to act on.
 */
function trustSummary(assertions: GraphAssertion[]): string {
  const counts = new Map<string, number>();
  for (const a of assertions) counts.set(a.trust, (counts.get(a.trust) ?? 0) + 1);
  return [...counts]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([trust, n]) => `${n} ${trust}`)
    .join(" · ");
}

/**
 * How a valid-time end reads on screen.
 *
 * Three states, three phrasings, because the API sends three and collapsing any
 * two loses the distinction the whole temporal layer rests on. "still true" and
 * "end unknown" look similar and are not: only the first makes a second current
 * claim a contradiction rather than a pair nobody can decide between.
 */
function endsLabel(ends: string): string {
  if (ends === "open") return "still true";
  if (ends === "unknown") return "end unknown";
  return `until ${when(ends)}`;
}

/**
 * What a conflict state means to someone who has to act on it.
 *
 * Deliberately not three shades of red. A contradiction is a thing to resolve, a
 * possible one is a thing to date, and an explained one is an assumption to
 * agree or disagree with — three different asks, and rendering them as
 * severities would suggest the third is a milder version of the first.
 */
const CONFLICT_COPY: Record<string, { label: string; hint: string }> = {
  conflict: {
    label: "contradiction",
    hint: "Both are asserted to be true now. One of them is wrong.",
  },
  possible: {
    label: "possible",
    hint: "These would collide if their dates overlapped, and the dates are unknown.",
  },
  explained: {
    label: "explained",
    hint: "Undecided, with an assumption accounting for it. Disagree and it comes back.",
  },
};

function labelsOf(nodes: GraphNode[]): Map<string, GraphNode> {
  return new Map(nodes.map((node) => [node.node_id, node]));
}

/** Group claims into the columns a layout puts them in. */
function group(
  assertions: GraphAssertion[],
  nodes: Map<string, GraphNode>,
  by: Layout,
): Map<string, GraphAssertion[]> {
  const groups = new Map<string, GraphAssertion[]>();
  for (const assertion of assertions) {
    const name = by === "subject" ? (nodes.get(assertion.src)?.label ?? "?") : assertion.rel;
    const bucket = groups.get(name);
    if (bucket) bucket.push(assertion);
    else groups.set(name, [assertion]);
  }
  return new Map([...groups].sort(([a], [b]) => a.localeCompare(b)));
}

function renderClaims(
  assertions: GraphAssertion[],
  nodes: Map<string, GraphNode>,
  contested: Set<string>,
): HTMLElement[] {
  const groups = group(assertions, nodes, layout);

  return [...groups].map(([name, members]) => {
    const column = document.createElement("section");
    column.className = "cluster";

    const heading = document.createElement("h3");
    heading.append(text("span", name), text("span", String(members.length), "count"));
    column.append(heading);
    column.append(
      text(
        "p",
        layout === "subject" ? "what it knows about this" : "everything related this way",
        "derivation",
      ),
    );

    const list = document.createElement("ul");
    for (const assertion of members) {
      const item = document.createElement("li");
      // A claim inside a contradiction is marked here as well as in the panel
      // below, because a person scanning the columns should not have to find the
      // badge to know one of these is disputed.
      item.className = `node${contested.has(assertion.assertion_id) ? " contested" : ""}`;

      const subject = nodes.get(assertion.src)?.label ?? "?";
      const object = nodes.get(assertion.dst)?.label ?? "?";

      // A sentence with its direction drawn, not a row of cells. The first
      // version printed `rel`, `object`, and two tags, which is a database tuple
      // with the schema removed: nothing on the row said which end was the
      // subject, and the reader had to know that the column heading was.
      const claim = document.createElement("p");
      claim.className = "claim";
      claim.append(
        text("span", subject, "end"),
        text("span", `—${assertion.rel}→`, "arrow"),
        text("span", object, "end"),
      );
      item.append(claim);

      item.append(text("span", endsLabel(assertion.ends), "tag"));
      if (contested.has(assertion.assertion_id)) {
        item.append(text("span", "disputed", "tag contested"));
      }
      // Where it came from, in the words that produced it. This is what makes a
      // wrong claim contestable rather than merely visible.
      if (assertion.reason) item.append(text("p", `from: “${assertion.reason}”`, "note"));
      list.append(item);
    }
    column.append(list);
    return column;
  });
}

function renderConflicts(conflicts: GraphConflict[], assertions: GraphAssertion[]): HTMLElement[] {
  if (conflicts.length === 0) return [];

  const claims = new Map(assertions.map((a) => [a.assertion_id, a]));
  const section = document.createElement("section");
  section.className = "cluster";
  section.append(text("h3", "Disagreements"));

  const list = document.createElement("ul");
  for (const conflict of conflicts) {
    const copy = CONFLICT_COPY[conflict.state] ?? { label: conflict.state, hint: "" };
    const item = document.createElement("li");
    item.className = `node ${conflict.state === "conflict" ? "contested" : "proposed"}`;

    const left = claims.get(conflict.left);
    const right = claims.get(conflict.right);
    item.append(text("code", conflict.rule));
    item.append(text("span", copy.label, "tag contested"));
    // The rule's own sentence, because a constraint here is a hypothesis about
    // this person's world rather than something the system is entitled to
    // enforce — and nobody can disagree with a rule they cannot read.
    item.append(text("p", conflict.sentence, "value"));
    if (left && right) item.append(text("p", `${left.rel} · ${right.rel}`, "note"));
    item.append(text("p", copy.hint, "note"));
    list.append(item);
  }
  section.append(list);
  return [section];
}

function renderConclusions(conclusions: GraphConclusion[]): HTMLElement[] {
  if (conclusions.length === 0) return [];

  const section = document.createElement("section");
  section.className = "cluster";
  section.append(text("h3", "Things it worked out"));
  section.append(text("p", "drawn from the claims, not stated by anyone", "derivation"));

  const list = document.createElement("ul");
  for (const conclusion of conclusions) {
    const item = document.createElement("li");
    item.className = `node${conclusion.status === "stale" ? " contested" : ""}`;
    item.append(text("span", conclusion.statement, "value"));
    item.append(text("span", `${Math.round(conclusion.confidence * 100)}%`, "tag"));
    item.append(text("span", conclusion.derived_by, "tag source"));
    if (conclusion.status === "stale") {
      // Stale is not wrong, and the wording matters: this was a sound inference
      // from a premise that has since moved, and calling it wrong would tell a
      // person to distrust the reasoning rather than to look at the evidence.
      item.append(text("span", "evidence changed", "tag contested"));
    }
    item.append(text("p", `rests on ${conclusion.evidence.length} claim(s)`, "note"));
    list.append(item);
  }
  section.append(list);
  return [section];
}

/**
 * The panel that asked ADR 0002's open question, and now reports on it.
 *
 * That record bet that the graph would earn its place when *relations between
 * facts* start mattering, and said the honest version was that the extractor was
 * the valuable half while the edges were speculative. These rows were zeroes for
 * as long as nothing recorded a relation. They are not zeroes any more, which is
 * evidence and not proof: relations existing is not the same as retrieval over
 * them beating recency, which is the measurement ADR 0006 defers to its last
 * phase on purpose.
 */
function renderVerdict(
  assertions: GraphAssertion[],
  conflicts: GraphConflict[],
  conclusions: GraphConclusion[],
): void {
  const open = assertions.filter((a) => a.ends === "open").length;
  const undecided = conflicts.filter((c) => c.state !== "conflict").length;
  const stale = conclusions.filter((c) => c.status === "stale").length;

  const rows: [string, string][] = [
    ["extracted relations", String(assertions.length)],
    ["asserted to still hold", `${open} of ${assertions.length}`],
    ["contradictions", String(conflicts.length - undecided)],
    ["undecided for want of a date", String(undecided)],
    ["conclusions drawn", String(conclusions.length)],
    ["conclusions whose evidence moved", String(stale)],
    ["trust attribution", trustSummary(assertions) || "—"],
  ];

  verdict.replaceChildren(
    text("h3", "What is in here, and whether it is earning its keep"),
    ...rows.flatMap(([term, value]) => [text("dt", term), text("dd", value)]),
    text(
      "p",
      "ADR 0002 bet that the graph would matter once relations between facts did. " +
        "These are relations, extracted rather than derived from a key prefix. Whether " +
        "traversing them beats recency is a different measurement, and ADR 0006 leaves " +
        "it to the retrieval phase deliberately — a graph nobody has curated would fail " +
        "that test for the wrong reason.",
      "note",
    ),
  );
}

export async function refresh(_sessionId: string | null): Promise<void> {
  // The session id is ignored, and the parameter stays because the shell hands
  // it to every tab. A graph belongs to a person and outlives the conversation
  // it was learned in, so switching sessions does not change what is drawn.
  const [graph, conclusions] = await Promise.all([readGraph(), readConclusions()]);

  const nodes = labelsOf(graph.nodes);
  const contested = new Set(
    graph.conflicts.filter((c) => c.state === "conflict").flatMap((c) => [c.left, c.right]),
  );

  if (graph.assertions.length === 0) {
    canvas.replaceChildren(
      text("p", "Nothing extracted yet.", "note"),
      text(
        "p",
        "Relations are recorded by a background job, and only when " +
          "BACTERIA_GRAPH_EXTRACTION_ENABLED is on and a worker is running.",
        "note",
      ),
    );
  } else {
    canvas.replaceChildren(
      ...renderClaims(graph.assertions, nodes, contested),
      ...renderConflicts(graph.conflicts, graph.assertions),
      ...renderConclusions(conclusions),
    );
  }

  renderVerdict(graph.assertions, graph.conflicts, conclusions);

  legend.replaceChildren(
    text("span", `${graph.nodes.length} things`),
    text("span", `${graph.assertions.length} things it knows about them`),
    text("span", `${graph.conflicts.length} disagreements`),
  );
}

layoutButtons.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLButtonElement) || !target.dataset["layout"]) return;

  layout = target.dataset["layout"] as Layout;
  for (const button of layoutButtons.querySelectorAll("button")) {
    button.classList.toggle("on", button === target);
  }
  // Refetched rather than re-arranged from what is in the DOM. The graph is not
  // session-scoped, and a person switching layout has usually just been talking,
  // so the round trip is also the cheapest way to pick up whatever the extractor
  // wrote while they were reading.
  void refresh(currentSessionId);
});

let currentSessionId: string | null = null;
export function setSession(sessionId: string | null): void {
  currentSessionId = sessionId;
}
