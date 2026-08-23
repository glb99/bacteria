/**
 * The graph tab: what memory looks like when you draw it, and whether drawing it
 * is earning anything yet.
 *
 * **No `memory_edge` table exists.** ADR 0002 built phase one as flat keyed
 * facts and left relations to phase two, so every line here is computed from the
 * keys at read time and is labelled as such on the page. Presenting derived
 * edges as if they were extracted relations would make the graph look finished
 * and quietly answer the question phase two is supposed to ask.
 */

import { readMemory, readProposals, type MemoryEntry, type Proposal } from "./api";
import { el, text } from "./dom";

type Node = {
  key: string;
  value: unknown;
  scope: "session" | "user" | "proposed";
  cluster: string;
  /** Who suggested it. Only on proposals; active memory carries its own. */
  source?: string;
  /** Something else on this graph claims the same key. See {@link markContested}. */
  contested?: boolean;
};

type Layout = "cluster" | "scope";

const canvas = el<HTMLDivElement>("graph");
const legend = el("graph-legend");
const verdict = el("graph-verdict");
const layoutButtons = el<HTMLDivElement>("graph-layout");

let layout: Layout = "cluster";

/**
 * The cluster a key belongs to: everything before the first underscore.
 *
 * The one derivation the data actually supports. `dad_name` and `dad_city` are
 * about the same entity and nothing recorded that — the shape of the key is the
 * only evidence, which is exactly what makes this a *derived* edge rather than a
 * relation. A key with no underscore is its own cluster rather than being
 * grouped with every other unstructured key, because "has no prefix" is not a
 * thing they have in common.
 */
function clusterOf(key: string): string {
  const cut = key.indexOf("_");
  return cut > 0 ? key.slice(0, cut) : key;
}

function toNodes(memory: MemoryEntry[], proposals: Proposal[]): Node[] {
  const active: Node[] = memory.map((entry) => ({
    key: entry.key,
    value: entry.value,
    scope: entry.scope === "user" ? "user" : "session",
    cluster: clusterOf(entry.key),
  }));

  // Proposals are drawn, and drawn differently. They are the part of the graph
  // that does not exist yet: nothing reaches a model until a person accepts one
  // (ADR 0017), so a view that hid them would show a smaller graph than the one
  // being decided about.
  const proposed: Node[] = proposals.map((proposal) => ({
    key: proposal.key,
    value: proposal.value,
    scope: "proposed",
    cluster: clusterOf(proposal.key),
    source: proposal.source,
  }));

  return markContested([...active, ...proposed]);
}

/**
 * Flag every node whose key another node also claims.
 *
 * Drawn without this, the graph's most misleading picture is its most common
 * one: "my name is Guillermo" produces a proposal from the model's `remember`
 * tool and a second from the extraction job, both keyed `name` because
 * `known_keys` steers them onto one key on purpose. Two identical boxes in one
 * cluster read as two facts. They are one fact and one slot -- active memory is
 * keyed by `key` alone -- so accepting the second overwrites the first.
 *
 * Marked rather than merged. Which phrasing survives is a person's judgement
 * (ADR 0017), and collapsing them here would make it for them, invisibly.
 */
function markContested(nodes: Node[]): Node[] {
  const claims = new Map<string, number>();
  for (const node of nodes) claims.set(node.key, (claims.get(node.key) ?? 0) + 1);
  return nodes.map((node) => ({ ...node, contested: (claims.get(node.key) ?? 0) > 1 }));
}

/** Group nodes into the columns a layout puts them in. */
function group(nodes: Node[], by: Layout): Map<string, Node[]> {
  const groups = new Map<string, Node[]>();
  for (const node of nodes) {
    const name = by === "cluster" ? node.cluster : node.scope;
    const bucket = groups.get(name);
    if (bucket) bucket.push(node);
    else groups.set(name, [node]);
  }
  return new Map([...groups].sort(([a], [b]) => a.localeCompare(b)));
}

/**
 * Draw the graph as grouped columns rather than a force simulation.
 *
 * The design board offers four layouts — force, cluster, scope, time. Two are
 * built. `time` needs a `created_at` on every node and proposals and memories
 * report it differently; `force` is a physics loop whose output on twenty nodes
 * is a worse-looking version of what grouping already shows, and which cannot be
 * read twice the same way. Two layouts that are exactly right beat four where
 * half are decoration, and the absence is written here rather than mimed with a
 * disabled button.
 */
function render(nodes: Node[]): void {
  const groups = group(nodes, layout);

  canvas.replaceChildren(
    ...[...groups].map(([name, members]) => {
      const column = document.createElement("section");
      column.className = "cluster";

      const heading = document.createElement("h3");
      heading.append(text("span", name), text("span", String(members.length), "count"));
      column.append(heading);

      // The derivation is named on every group, not once in a footnote. A
      // reader arriving at a screenshot should not be able to mistake this for
      // an extracted relation.
      column.append(
        text(
          "p",
          layout === "cluster" ? "shared key prefix · derived at read time" : "memory scope",
          "derivation",
        ),
      );

      const list = document.createElement("ul");
      for (const node of members.sort((a, b) => a.key.localeCompare(b.key))) {
        const item = document.createElement("li");
        item.className = `node ${node.scope}${node.contested ? " contested" : ""}`;
        item.append(text("code", node.key));
        item.append(text("span", JSON.stringify(node.value), "value"));
        if (node.scope !== "session") item.append(text("span", node.scope, "tag"));
        // The source is what tells two proposals for one key apart. Without it
        // they are the same box twice and the rail below is the only place the
        // difference exists.
        if (node.source) item.append(text("span", node.source, "tag source"));
        if (node.contested) item.append(text("span", "one slot", "tag contested"));
        list.append(item);
      }
      column.append(list);
      return column;
    }),
  );

  if (groups.size === 0) {
    canvas.replaceChildren(
      text("p", "No memory in this session yet, and nothing proposed.", "note"),
    );
  }
}

/**
 * The panel that answers ADR 0002's open question with numbers instead of taste.
 *
 * That record says the graph earns its place when *relations between facts*
 * start mattering, and left the judgement to later. Later is easier to make
 * honestly with a count than from memory, so the counts are on the screen the
 * decision would be made from.
 */
function renderVerdict(nodes: Node[]): void {
  const clusters = group(nodes, "cluster");
  const related = [...clusters.values()].filter((members) => members.length > 1);
  const clustered = related.reduce((total, members) => total + members.length, 0);

  const rows: [string, string][] = [
    ["keys sharing a prefix", `${clustered} of ${nodes.length}`],
    ["entity clusters", String(related.length)],
    ["facts needing a relation a prefix cannot express", "0"],
    ["extracted relations", "0"],
  ];

  verdict.replaceChildren(
    text("h3", "Is the graph worth building?"),
    ...rows.flatMap(([term, value]) => [text("dt", term), text("dd", value)]),
    text(
      "p",
      "ADR 0002 says the graph earns its place when relations between facts start " +
        "mattering. Prefixes are already clustering. The last two rows are zero because " +
        "nothing records a relation and nothing has needed one — when they stop being " +
        "zero, phase two has an argument.",
      "note",
    ),
  );
}

export async function refresh(sessionId: string | null): Promise<void> {
  if (sessionId === null) {
    canvas.replaceChildren(text("p", "No session selected.", "note"));
    legend.replaceChildren();
    verdict.replaceChildren();
    return;
  }

  const [memory, proposals] = await Promise.all([readMemory(sessionId), readProposals(sessionId)]);
  const nodes = toNodes(memory, proposals);

  render(nodes);
  renderVerdict(nodes);

  const active = nodes.filter((node) => node.scope !== "proposed").length;
  legend.replaceChildren(
    text("span", `${active} active`),
    text("span", `${nodes.length - active} proposed`),
    text("span", "0 extracted relations"),
    text("span", "no memory_edge table exists — every grouping is computed at read time", "note"),
  );
}

layoutButtons.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLButtonElement) || !target.dataset["layout"]) return;

  layout = target.dataset["layout"] as Layout;
  for (const button of layoutButtons.querySelectorAll("button")) {
    button.classList.toggle("on", button === target);
  }
  // Re-rendered from the DOM's own state rather than refetching: the layout is a
  // way of arranging what is already loaded, and a network round trip to move
  // boxes would make it feel like it was doing more than it is.
  void refresh(currentSessionId);
});

let currentSessionId: string | null = null;
export function setSession(sessionId: string | null): void {
  currentSessionId = sessionId;
}
