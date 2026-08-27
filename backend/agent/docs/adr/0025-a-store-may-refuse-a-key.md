# 0025 — A store may refuse a key, and refusing is not failing

## Status

Proposed — 2026-08-26

## Context

`SessionRepository` was written against one implementation, and that
implementation cannot refuse anything: a table takes whatever key it is handed.
So `remember` and `propose` return a `MemoryEntry` and have no other outcome, and
every caller — the `remember` tool included — was built on the assumption that a
write either succeeds or the process is broken.

A second implementation exists now, and it refuses. The application's
graph-backed store holds a keyed memory as a *relation*, and relations are a
governed vocabulary, so a key outside it has nowhere to go. Its own note is that
writing anyway would be **"a call that reports success and loses the fact, which
is worse than a refusal a caller can see"** — which is right, and it raises to
say so.

Nothing catches it. `execute_tool_call` wraps any handler exception as
`ToolExecutionError` on the stated grounds that *a handler that raises is a bug*,
and the runtime propagates it. **So a refused key takes down the whole turn**: the
caller gets a 500 and no answer, for a memory nobody asked for.

This is not hypothetical and it is not an edge. The first turn ever taken against
that store failed with `UnknownPreferenceError('user_name')`. With that key
aliased, the next attempt failed with `brevity_preference` — a key the model
invented on the spot for a tone. **Coining keys is what a model does**, which is
why the vocabulary exists at all, so the refusing path is the ordinary one.

Telling the model which keys exist makes it rare — that shipped separately and
the same turn now succeeds. It does not make it impossible, and a store somebody
lives on cannot lose a turn to a word.

**The gap is a missing outcome, not a missing guard.** Every layer behaved
correctly: the store refused rather than lying, the executor treated a raise as a
fault because that is what a raise means, the runtime propagated. What is absent
is any way for a store to say *I cannot hold that* in a vocabulary the caller
understands.

## Decision

### 1. `MemoryRefused` is part of the session protocol

A refusal is an outcome the protocol names, alongside the entry a write returns.
It carries the key and a short reason a model can read.

It lives with the protocol rather than in either package's private code, because
it is the contract that is incomplete: an implementation raising an exception
only the application knows about is an implementation talking past its interface.

### 2. The tool catches it and answers with it

`build_remember_tool`'s handler catches `MemoryRefused` and returns a tool
**result** describing it, rather than letting it escape. The model reads the
result, keeps talking, and does not try the same key again in that turn.

**Only this exception, and only around the store call.** A blanket `except
Exception` would turn every genuine bug into a polite message and hide it —
which is the failure this record must not create while fixing its opposite.

### 3. Everything else stays a fault

`execute_tool_call` is unchanged. A handler that raises anything else is still a
bug and still fails the turn, because that is what a raise means and the
alternative is a system that cannot distinguish a refusal from a defect.

Not built:
    A refusal on any other write. `forget`, `activate` and `reject` all take a
    key that must already exist, so their failure is *unknown key* rather than
    *unacceptable key* — a different thing with a different answer, and no
    caller has needed one. When one does, it belongs beside this rather than
    inside it.

## Consequences

**A store may now have a vocabulary**, which is what makes the graph-backed one
usable at all rather than merely built. Until this, a store with a closed key set
could serve any turn where the model happened to guess correctly.

**A refusal becomes visible to the model and invisible to the user.** The model
learns its write did not land and can say something useful; a sibling change in the
application tells it never to narrate the storage layer, after a
live turn produced *"since the memory tool only allows me to save your name
directly…"* to somebody asking about their mother.

**The model still sometimes narrates the limit, and no instruction fixes it.**
Two separate lines tell it not to — the tool's key description and the refusal
text itself — and a live turn asking it to remember a biscuit still produced *"I
can only save specific types of long-term preferences to my permanent memory"*.
That is the *asked and cannot be held to* pattern for the fifth time here, and it
is a **consequence of telling the model the vocabulary** rather than a defect in
the wording: a model shown a closed list will sometimes explain it. Not showing
the list is the only structural fix and it is worse, because then the model
coins keys and every one is a refusal.

**One more thing can go wrong quietly.** A refusal that used to be a 500 is now a
tool result, so a store rejecting *everything* — a misconfiguration, an empty
vocabulary — would look like a working system that remembers nothing. The
counter that would catch it does not exist, and this record does not add one
because inventing an alerting story for a failure nobody has had is how a
codebase acquires monitoring nobody reads.

**The protocol grows a type**, and a protocol is the thing this package changes
most reluctantly. The defence is that it was already wrong: it described one
store's capabilities as though they were every store's, and the second store
found the omission by falling over.

### The one to dislike

This makes it easier to add stores that refuse things. A vocabulary is a real
constraint on what a person's memory may contain, and the graph's is currently
**three keys** — `tone`, `language`, `name`. A model that cannot record what it
just heard will now do so quietly and pleasantly rather than crashing, and a
crash is at least a signal somebody acts on. The honest reading is that this
records the cost rather than removing it: the vocabulary is the problem, and
graceful refusal only stops it being an outage as well.

## Alternatives rejected

**Catch `Exception` in the tool handler.** One line, and it converts every real
defect in the store into a message the model reads as a refusal. The bug this
record fixes would be replaced by a worse one that is much harder to see.

**Let the application translate the refusal before the agent sees it.** The
repository would catch its own exception and return… a `MemoryEntry`, because
that is all the protocol offers. That is the *reports success and loses the fact*
outcome the store refused on purpose.

**Give the store no vocabulary — accept any key.** It cannot: a key is a relation
and an unratified relation has no sentence, so a memory written under one could
never be rendered for a model. The refusal is load-bearing and the alternative is
silent loss.
