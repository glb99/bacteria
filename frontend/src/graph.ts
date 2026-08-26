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
 * And now it writes. A claim can be retracted, a conclusion rejected, a node
 * renamed, and two nodes linked — which is what turns a viewer into the surface
 * where a person and their agent disagree.
 *
 * **Nothing here stages.** These are the owner's own edits and the design's rule
 * is that their writes are never blocked, so each acts immediately and the reply
 * redraws the page. What would stage is a proposal somebody else made, and
 * nothing makes one yet.
 *
 * Retraction asks twice, in place rather than in a dialog: the button becomes
 * "sure?" and a click elsewhere puts it back. A modal would be the notification
 * fatigue the design warns against in miniature, and no confirmation at all
 * makes a misclick cost a claim that has to be said again to come back.
 */

import {
  confirmAssertion,
  linkNodes,
  readConclusions,
  readGraph,
  rejectConclusion,
  renameNode,
  retractAssertion,
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

/** The node waiting for a second one to be linked to, if any. */
let pendingLink: string | null = null;

/**
 * Why the last link was refused, shown beside the act rather than in the legend.
 *
 * A refusal reported at the bottom of the page is a refusal nobody reads: the
 * first version put "cannot link a person to an organization" in the legend, six
 * inches from the button that had just done nothing, and the honest description
 * of that from the other side of the screen is "I click and nothing happens".
 */
let linkError: string | null = null;

/**
 * Run one act, then redraw.
 *
 * Errors are surfaced on the page rather than thrown into an event handler,
 * where an unhandled rejection would be invisible to the person who just clicked
 * and appear only in a browser console they are not reading. That failure has
 * already happened once in this file's history.
 */
function perform(button: HTMLButtonElement, run: () => Promise<unknown>): void {
  button.disabled = true;
  void run()
    .then(() => refresh(currentSessionId))
    .catch((failure: unknown) => {
      report(failure instanceof Error ? failure.message : String(failure));
    })
    // Always, rather than only on failure. A redraw normally replaces this
    // button and the flag goes with it -- but if the redraw is what failed, the
    // row is left dead with nothing saying why, and the page looks broken
    // rather than the request looking failed.
    .finally(() => {
      button.disabled = false;
    });
}

function act(label: string, className: string): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `act ${className}`;
  button.textContent = label;
  return button;
}

/** A button that acts on the click. */
function action(label: string, className: string, run: () => Promise<unknown>): HTMLButtonElement {
  const button = act(label, className);
  button.addEventListener("click", () => perform(button, run));
  return button;
}

/**
 * A destructive act that asks once, in place. The second click is the one that acts.
 *
 * **One listener, and the reset skips this button.** The first version wired two
 * listeners onto one element and relied on their order, then reset itself from a
 * `document` handler registered with `capture: true` — which fires on the way
 * *down*, before the event reaches the button. So the confirming click disarmed
 * it first and the handler, finding it unarmed, armed it again. It could be
 * armed forever and never fired.
 *
 * Now the click that arms and the click that confirms both stop propagating, so
 * neither reaches the reset; every other click on the page does.
 *
 * **At most one button is armed at a time**, tracked here rather than per
 * button. Arming a second one cannot rely on the document reset, because that
 * click stops propagating too — so without this, a row abandoned mid-confirm
 * stays armed and its next click acts immediately, which is the trap the
 * confirmation exists to prevent.
 */
let disarmArmed: (() => void) | null = null;

function confirmable(label: string, run: () => Promise<unknown>): HTMLButtonElement {
  const button = act(label, "danger");
  let armed = false;

  const disarm = (): void => {
    armed = false;
    button.textContent = label;
    if (disarmArmed === disarm) disarmArmed = null;
  };

  button.addEventListener("click", (event) => {
    event.stopPropagation();
    if (armed) {
      document.removeEventListener("click", disarm);
      disarm();
      perform(button, run);
      return;
    }
    disarmArmed?.();
    armed = true;
    button.textContent = "sure?";
    disarmArmed = disarm;
    // An abandoned "sure?" must not sit there waiting to catch someone later.
    document.addEventListener("click", disarm, { once: true });
  });

  return button;
}

function report(message: string): void {
  legend.replaceChildren(text("span", message, "failed"));
}

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

/**
 * How a claim says who is making it.
 *
 * Two voices, because there are two parties: the person whose graph this is, and
 * the agent that reads for them. `origin` carries it — `stated` means somebody
 * meant it, `inferred` means the extractor produced it and nobody has endorsed
 * it yet.
 *
 * **Not `trust`.** That records which channel a claim arrived through and is the
 * same value on nearly every row, which is why it was taken off the claim and
 * counted in the diagnostics instead. A voice has to distinguish somebody from
 * somebody else or it is decoration.
 *
 * This is the difference between a log you inspect and a model you argue with: a
 * claim cannot be contested if it is not visible who is making it.
 */
const VOICE: Record<string, { label: string; className: string }> = {
  stated: { label: "you confirmed this", className: "voice stated" },
  inferred: { label: "I worked this out", className: "voice inferred" },
};

function renderClaims(
  assertions: GraphAssertion[],
  nodes: Map<string, GraphNode>,
  contested: Map<string, string>,
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
      // A claim inside a disagreement is marked here as well as in the panel
      // below, because a person scanning the columns should not have to find the
      // badge to know one of these is disputed.
      //
      // **The state travels, not a boolean.** This was `contested` either way,
      // which rendered `possible` and `explained` identically to `conflict` --
      // collapsing on screen the three-valued distinction the temporal layer
      // exists to produce. A contradiction is a thing to resolve, a possible one
      // a thing to date, an explained one an assumption to agree with: three
      // asks, and one border colour cannot make three requests.
      const state = contested.get(assertion.assertion_id);
      item.className = `node${state ? ` disputed ${state}` : ""}${
        assertion.canonical ? "" : " tail"
      }`;

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
      // A relation nobody has ratified. ADR 0007 records the tail rather than
      // dropping it precisely so it can be judged, and it cannot be judged while
      // it renders like an agreed one.
      if (!assertion.canonical) {
        item.append(text("span", "unratified word", "tag tail"));
      }
      if (state) {
        item.append(text("span", CONFLICT_COPY[state]?.label ?? state, `tag ${state}`));
      }
      // Where it came from, in the words that produced it. This is what makes a
      // wrong claim contestable rather than merely visible.
      if (assertion.reason) item.append(text("p", `from: “${assertion.reason}”`, "note"));
      // Who is saying it, on every claim rather than only on the endorsed ones.
      // The previous version tagged a confirmed claim and left the rest bare,
      // so the common case -- the agent's own reading of a transcript -- was
      // the one with no attribution at all.
      const voice = VOICE[assertion.origin];
      if (voice) item.append(text("span", voice.label, `tag ${voice.className}`));
      // The claim is the unit a person agrees or disagrees with, so both
      // affordances are on it rather than in a panel that would make them match
      // ids by eye.
      //
      // Confirm is not offered on a claim already confirmed. A button that
      // reports success and writes nothing teaches a person that the act is
      // pointless, which is worse for the one act that fills the graph than for
      // any of the ones that empty it.
      if (assertion.origin !== "stated") {
        item.append(action("confirm", "quiet", () => confirmAssertion(assertion.assertion_id)));
      }
      item.append(
        confirmable("retract", () => retractAssertion(assertion.assertion_id)),
      );
      list.append(item);
    }
    column.append(list);
    return column;
  });
}

/**
 * The things themselves, and the two acts that are about identity rather than fact.
 *
 * Nodes had no section: they appeared only as the ends of claims, which is where
 * a reader wants them and leaves nowhere to hang an act that is *about* a node.
 * Both acts here are — renaming one, and saying two are the same thing.
 *
 * **Linking takes two clicks on two nodes** rather than a form asking for two
 * ids, because a person picking out a duplicate is looking at labels and would
 * have to go and find ids to type. The first click arms; the second commits;
 * clicking the armed node again cancels.
 */
function renderNodes(nodes: GraphNode[]): HTMLElement[] {
  if (nodes.length === 0) return [];

  const section = document.createElement("section");
  section.className = "cluster wide";
  section.append(text("h3", "Things"));

  // The pending state says which node is waiting and offers the way out, because
  // a half-finished two-click act is the one place this page holds state a person
  // cannot see. Naming the node is the point: "pick the other one" is useless if
  // you have forgotten which one you picked.
  const waiting = nodes.find((n) => n.node_id === pendingLink);
  if (waiting) {
    const banner = document.createElement("p");
    banner.className = "derivation";
    banner.append(
      text("span", `Linking “${waiting.label}” — pick another ${waiting.kind}.`),
    );
    banner.append(
      action("cancel", "quiet", async () => {
        pendingLink = null;
        linkError = null;
      }),
    );
    section.append(banner);
    if (linkError) section.append(text("p", linkError, "failed"));
  } else {
    section.append(
      text("p", "Two nodes for one thing are linked, never merged: both keep their claims.", "derivation"),
    );
  }

  const list = document.createElement("ul");
  for (const node of nodes) {
    const item = document.createElement("li");
    const arming = pendingLink === node.node_id;
    // A link is between two things of one kind, so while one is waiting the
    // others are not all candidates. Refusing at the API and reporting it is a
    // worse answer than not offering the click: the person learns the rule by
    // seeing which rows stay available.
    const eligible = waiting === undefined || node.kind === waiting.kind;
    item.className = `node${arming ? " proposed" : ""}`;
    item.append(text("span", node.label, "value"));
    item.append(text("span", node.kind, "tag"));

    item.append(
      action("rename", "quiet", async () => {
        // `prompt` is modal, which this file otherwise avoids. It stays because
        // the alternative is an inline editor, and one is a line of code against
        // fifty for an act nobody performs twice on the same node.
        const label = window.prompt(`What should “${node.label}” be called?`, node.label);
        if (label === null || label.trim() === "" || label === node.label) return;
        await renameNode(node.node_id, label.trim());
      }),
    );

    item.append(
      linkButton(node, arming, eligible),
    );
    list.append(item);
  }
  section.append(list);
  return [section];
}

/**
 * One node's half of the two-click link.
 *
 * **The pending node survives a refusal.** It used to be cleared before the
 * request, so a rejected link put the person back at the start with nothing said
 * and nothing selected — which is indistinguishable from the click having been
 * ignored.
 */
function linkButton(node: GraphNode, arming: boolean, eligible: boolean): HTMLButtonElement {
  const button = action(arming ? "picked" : "same as…", "quiet", async () => {
    // Read at click time rather than from the closure, so a stale render cannot
    // make the second click behave like a first one.
    if (pendingLink === null || pendingLink === node.node_id) {
      pendingLink = pendingLink === node.node_id ? null : node.node_id;
      linkError = null;
      return;
    }
    try {
      await linkNodes(pendingLink, node.node_id);
      pendingLink = null;
      linkError = null;
    } catch (failure) {
      // Kept rather than rethrown, so the redraw still happens and the message
      // lands in the section the person is looking at.
      linkError = failure instanceof Error ? failure.message : String(failure);
    }
  });

  if (!eligible) {
    button.disabled = true;
    button.title = "a link is between two things of the same kind";
  }
  return button;
}

function renderConflicts(conflicts: GraphConflict[], assertions: GraphAssertion[]): HTMLElement[] {
  if (conflicts.length === 0) return [];

  const claims = new Map(assertions.map((a) => [a.assertion_id, a]));
  const section = document.createElement("section");
  section.className = "cluster wide";
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
  section.className = "cluster wide";
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
    // Rejecting is not destructive in the way retracting is -- a conclusion may
    // be recomputed and the log keeps everything it rested on -- so it asks
    // once, not twice. A retracted one is gone from this list and stays gone.
    if (conclusion.status === "active") {
      item.append(action("reject", "quiet", () => rejectConclusion(conclusion.conclusion_id)));
    }
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
  // Every state, not only the provable one. Filtering to `conflict` meant a
  // claim waiting on a date looked exactly like an agreed one, so the two
  // states the constraint layer works hardest to distinguish were invisible on
  // the claim itself and reachable only by matching ids against the panel.
  //
  // Hard conflicts win a tie: a claim in both a contradiction and an explained
  // pair has one ask that cannot wait and one that can.
  const contested = new Map<string, string>();
  const rank: Record<string, number> = { explained: 0, possible: 1, conflict: 2 };
  for (const c of graph.conflicts) {
    for (const id of [c.left, c.right]) {
      const held = contested.get(id);
      if (held === undefined || (rank[c.state] ?? 0) > (rank[held] ?? 0)) {
        contested.set(id, c.state);
      }
    }
  }

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
      ...renderNodes(graph.nodes),
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
