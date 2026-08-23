/**
 * The chat tab: a conversation, and the proposals it produced.
 *
 * Renders what the transcript actually contains rather than a chat bubble
 * abstraction over it. A turn is not one message: it is the user's message, any
 * tool calls, the reply, and a `run_meta` describing how the run was configured
 * — and a console that hid the last three would be a worse view of this system
 * than `bacteria-admin chat` already is.
 */

import {
  acceptProposal,
  createSession,
  listSessions,
  readExtraction,
  readProposals,
  readTranscript,
  rejectProposal,
  takeTurn,
  type Proposal,
  type SessionSummary,
  type TranscriptEntry,
} from "./api";
import { el, short, text, when } from "./dom";

let sessionId: string | null = null;
let sessions: SessionSummary[] = [];

const picker = el<HTMLSelectElement>("session-picker");
const newSession = el<HTMLButtonElement>("new-session");
const transcript = el("transcript");
const composer = el<HTMLFormElement>("composer");
const message = el<HTMLTextAreaElement>("message");
const sendButton = el<HTMLButtonElement>("send");
const pending = el("pending");
const queue = el("queue");
const queueCount = el("queue-count");
const watermark = el("watermark");

/** The kinds this console knows how to draw. Anything else is shown raw rather than dropped. */
const KNOWN = new Set(["message", "tool_call", "run_error", "run_meta"]);

function renderEntry(entry: TranscriptEntry): HTMLElement {
  const item = document.createElement("article");
  item.className = `entry ${entry.kind}`;

  const head = document.createElement("header");
  const who = document.createElement("span");
  who.className = "who";

  const payload = entry.payload as Record<string, unknown>;

  if (entry.kind === "message") {
    who.textContent = String(payload["role"] ?? "message");
    item.classList.add(String(payload["role"] ?? ""));
  } else {
    who.textContent = entry.kind.replace("_", " ");
  }

  const meta = document.createElement("span");
  meta.className = "meta";
  // The run id, not a sequence number. `seq` is real in the database and is not
  // on the projection -- see `TranscriptEntry` -- and the run is what actually
  // groups these items into one turn anyway.
  meta.textContent = [when(entry.timestamp), entry.run_id ? `run ${short(entry.run_id)}` : null]
    .filter(Boolean)
    .join(" · ");

  head.append(who, meta);
  item.append(head);

  if (entry.kind === "message") {
    item.append(text("p", String(payload["text"] ?? "")));
  } else if (entry.kind === "run_error") {
    const error = text("p", String(payload["error"] ?? "unknown error"));
    error.className = "error";
    item.append(error);
    // Said out loud, because the transcript containing an error at all is the
    // property ADR 0012 is about: the run committed what it had before failing.
    item.append(text("p", "the run committed what it had before failing", "note"));
  } else if (entry.kind === "run_meta") {
    item.append(renderRunMeta(payload));
  } else if (entry.kind === "tool_call") {
    item.append(text("pre", JSON.stringify(payload, null, 2)));
  }

  if (!KNOWN.has(entry.kind)) {
    item.append(text("pre", JSON.stringify(payload, null, 2)));
  }

  return item;
}

/**
 * How a run was configured, as facts rather than a blob.
 *
 * **`memories_in_context` is a count, and this says "N memories" rather than
 * naming them on purpose.** The keys are not recorded: `run_meta` keeps counts
 * deliberately, so the design board's "prompt carried: dad_name, dad_city" strip
 * cannot be built from anything that exists. Showing a number is the honest
 * version; inventing the keys from current memory would show what the prompt
 * *would* carry today, not what it carried then.
 */
function renderRunMeta(payload: Record<string, unknown>): HTMLElement {
  const list = document.createElement("dl");
  list.className = "run-meta";

  const included = Number(payload["memories_in_context"] ?? 0);
  const considered = Number(payload["memories_considered"] ?? 0);
  const omitted = Math.max(considered - included, 0);

  const facts: [string, string][] = [
    ["model", String(payload["model"] ?? "unknown")],
    ["outcome", String(payload["outcome"] ?? "unknown")],
    ["context", `${payload["messages_in_context"] ?? 0} messages`],
    ["memory", omitted > 0 ? `${included} carried, ${omitted} displaced` : `${included} carried`],
    ["retrieval", String(payload["retrieval_strategy"] ?? "—")],
  ];

  const exposed = payload["tools_exposed"];
  if (Array.isArray(exposed) && exposed.length > 0) {
    facts.push(["tools", exposed.join(", ")]);
  }

  for (const [term, value] of facts) {
    list.append(text("dt", term), text("dd", value));
  }
  return list;
}

/**
 * How many suggestions in this listing want the same key.
 *
 * Two proposers finding one fact is the ordinary case, not a corner one: the
 * model's `remember` tool proposes mid-turn, the extraction job proposes from
 * the transcript afterwards, and `known_keys` deliberately pushes the second
 * towards the key the first already used. Left unmarked, they read as two
 * unrelated facts that happen to be spelled alike, and a reviewer accepts both.
 */
function rivalsByKey(proposals: Proposal[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const proposal of proposals) {
    counts.set(proposal.key, (counts.get(proposal.key) ?? 0) + 1);
  }
  return counts;
}

function renderProposal(proposal: Proposal, rivals: number): HTMLElement {
  const item = document.createElement("li");
  item.className = "proposal";

  const head = document.createElement("header");
  head.append(text("code", proposal.key), text("span", proposal.source, "source"));
  if (rivals > 1) head.append(text("span", `${rivals} for this key`, "rival"));
  item.append(head);

  item.append(text("p", JSON.stringify(proposal.value), "value"));
  item.append(text("p", proposal.reason, "note"));

  // What accepting would destroy, named with its value. Active memory is keyed
  // by `key` alone while proposals are keyed by `(source, key)`, so this accept
  // replaces rather than joins -- and there is no history table, so the previous
  // value is gone the instant the button is pressed. Saying only *that* a
  // replacement will happen is what let a strictly worse phrasing of a fact get
  // promoted over a good one; the value is the part that makes it a decision.
  for (const held of proposal.held_by ?? []) {
    const replaced = `accepting replaces ${held.scope} memory: ${JSON.stringify(held.value)}`;
    item.append(text("p", replaced, "replaces"));
  }

  const actions = document.createElement("div");
  actions.className = "actions";

  // Two accept buttons rather than a scope dropdown beside one. The scope is
  // the decision -- `user` carries the fact into every later conversation --
  // and a control you can leave on its default is one people leave on its
  // default.
  for (const scope of ["session", "user"] as const) {
    const accept = document.createElement("button");
    accept.textContent = `accept · ${scope}`;
    accept.addEventListener("click", async () => {
      await acceptProposal(sessionId!, proposal.source, proposal.key, scope);
      await refresh();
    });
    actions.append(accept);
  }

  const reject = document.createElement("button");
  reject.className = "ghost";
  reject.textContent = "reject";
  reject.addEventListener("click", async () => {
    await rejectProposal(sessionId!, proposal.source, proposal.key);
    await refresh();
  });
  actions.append(reject);

  item.append(actions);
  return item;
}

/** Reload everything the tab shows for the current session. */
export async function refresh(): Promise<void> {
  sessions = await listSessions();

  if (sessionId === null || !sessions.some((s) => s.session_id === sessionId)) {
    sessionId = sessions[0]?.session_id ?? null;
  }

  picker.replaceChildren(
    ...sessions.map((session) => {
      const option = document.createElement("option");
      option.value = session.session_id;
      option.textContent = `${short(session.session_id)} · ${when(session.last_activity_at)}`;
      option.selected = session.session_id === sessionId;
      return option;
    }),
  );

  if (sessionId === null) {
    transcript.replaceChildren(text("p", "No conversations yet. Start one.", "note"));
    queue.replaceChildren();
    queueCount.textContent = "0";
    watermark.textContent = "no session";
    composer.hidden = true;
    return;
  }

  composer.hidden = false;

  const [entries, proposals, extraction] = await Promise.all([
    readTranscript(sessionId),
    readProposals(sessionId),
    readExtraction(sessionId),
  ]);

  transcript.replaceChildren(
    ...(entries.length === 0
      ? [text("p", "Nothing said yet.", "note")]
      : entries.map(renderEntry)),
  );
  transcript.scrollTop = transcript.scrollHeight;

  const rivals = rivalsByKey(proposals);
  queue.replaceChildren(
    ...(proposals.length === 0
      ? [text("li", "Nothing waiting for a decision.", "note")]
      : proposals.map((proposal) => renderProposal(proposal, rivals.get(proposal.key) ?? 1))),
  );
  queueCount.textContent = String(proposals.length);

  // `behind` rather than a "worker up" light. Nothing reports whether a worker
  // is running, and inferring it from a watermark that has not moved would be a
  // guess presented as a status -- a session with no new turns is also behind by
  // zero and perfectly healthy.
  watermark.textContent =
    extraction.latest_seq < 0
      ? "seq — · nothing to read"
      : `seq ${extraction.latest_seq} · extraction ${
          extraction.behind === 0 ? "caught up" : `${extraction.behind} behind`
        }`;
}

picker.addEventListener("change", async () => {
  sessionId = picker.value;
  await refresh();
});

newSession.addEventListener("click", async () => {
  const created = await createSession();
  sessionId = created.session_id;
  await refresh();
});

composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const said = message.value.trim();
  if (!said || sessionId === null) return;

  message.value = "";
  sendButton.disabled = true;

  // Elapsed seconds, not a fake token stream. `send()` blocks until the reply is
  // whole, so animating one would be a lie about what the layer below does --
  // and the elapsed count is the honest signal a person actually wants while
  // waiting.
  const started = Date.now();
  pending.hidden = false;
  const tick = window.setInterval(() => {
    pending.textContent = `waiting on the model · ${((Date.now() - started) / 1000).toFixed(1)}s`;
  }, 100);

  try {
    await takeTurn(sessionId, said);
  } finally {
    window.clearInterval(tick);
    pending.hidden = true;
    sendButton.disabled = false;
    // Refreshed even when the turn failed. The runtime commits the user's
    // message and the error before the exception escapes, so there is something
    // to see -- and showing nothing would suggest the turn never happened.
    await refresh();
  }
});

message.addEventListener("keydown", (event) => {
  // Enter sends, Shift+Enter breaks the line. The composer is a `textarea` so
  // that a multi-line message is possible at all; without this it would need a
  // mouse to send one.
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    composer.requestSubmit();
  }
});

export const currentSession = () => sessionId;
