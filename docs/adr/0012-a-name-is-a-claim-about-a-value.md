# 0012 — A name is a claim about a value, not a property to be dropped

## Status

Proposed — 2026-08-26.

**Amends [ADR 0007](0007-the-relation-vocabulary-is-a-catalogue.md) §9 rather
than superseding the record.** Everything else 0007 decided stands: the
catalogue, the unratified tail, canonicality derived at read time, promotion by
the rule of three. What changes is one entry and one denylist.

Records are immutable in substance, so §9 is not edited. It reasoned correctly
from what existed when it was written, and what existed changed underneath it —
which is the case this record exists to state.

## Context

§9 stopped the extractor emitting name-claims, and the reason was concrete
rather than tidy. `self —name→ Guillermo` made *"Guillermo"* a **node**, and it
did: `a8127237` labelled `Guillermo`, kind `person`, sat beside `783e1dc6`
labelled `self` — the same human as two person nodes, with no `same_as` to join
them. Five of fifteen rows were one name-claim wearing six hats.

It left the gap open honestly:

> Where a name-claim goes instead. "The owner is called Guillermo" should
> **rename the `self` node** […] That route is a write path and this record does
> not open one.

**Two things have happened since.**

[ADR 0009](0009-the-graph-is-correctable.md) opened the write path: `rename`
exists. And [ADR 0008](0008-preferences-are-assertions.md) introduced the `value`
node kind — a word rather than a thing anyone could point at — so that a
preference could be a functional relation whose object is a plain string.

**The obvious repair is unsafe, and that is why this record is not simply "wire
`rename` up".** Renaming the owner and projecting the label as memory would put
text in a prompt that never passed
`bacteria.app.graph.service.preferences_for` — the one function permitted to
decide what may be spoken, gating on `origin == "stated"`. A label carries no
origin, and 0009 is explicit that it is a display name with **no history**, so
there is nowhere to record who set it. That route breaks the agent's ADR 0017
boundary at exactly the point 0010 §5 was careful to preserve.

**The finding that forces this record**: a name has a shape in this system
already, and 0008 built it. It is not a label and not an attribute. It is a
claim whose object is a value.

## Decision

### 1. `name` joins the catalogue as a preference-shaped relation

| | |
|---|---|
| name | `name` |
| signature | `person → value` |
| functional | yes — *"A person goes by one name at a time."* |
| sentence | *"`<src>` is called `<dst>`"* |
| aliases | the twelve words `_NAMING_RELATIONS` held |

`self —name→ "Guillermo"`, with `Guillermo` a **value** node. §9's objection is
answered rather than overruled: as a value it is not a person, so no second
person node exists to be joined.

**It prevents the split rather than repairing it**, which is the stronger
outcome. The `rename` route repairs a graph that already has two nodes for one
human; this one never creates the second. 0006's asymmetry says splitting is
recoverable and collapsing is not — so not splitting is better than either.

### 2. `functional` is right, and the reason is not "people have one name"

They do not, and `alternative_name` was among the observed rows. Functional means
*at most one `dst` per `(user_id, src)` at a time*, and the question this
relation answers is **what do I call you now** — which has one answer. "Call me
Gui" should *replace* "Guillermo", which is what a functional relation does and
what a keyed memory does.

An alternative name is a different relation. Nothing has asked for one, and the
catalogue's rule is that a relation is admitted when something can check it
rather than when someone can imagine it.

So `name` is admitted on **both** tests — functionality and an asymmetric kind
signature — where `mother` earns its place on functionality alone.

### 3. The denylist becomes aliases, and that is worth more than the feature

`_NAMING_RELATIONS` describes itself as

> a denylist, which is the shape this package argues against everywhere else, and
> it is used here because the alternative is worse rather than because it is
> good.

Twelve literal words with no promotion path, no tail, and no evidence trail. They
become aliases of a catalogue entry, and the one construct 0007's vocabulary
design had to apologise for goes away.

### 4. The prompt's naming rule is replaced, not deleted

The rule *"A person's name is an attribute, not a relationship"* comes out.
`name` joins `tone` and `language` in the value-object exception the prompt
already carries, and — like every catalogue entry — is rendered with its reading
sentence rather than described by hand.

### 5. The label still gets corrected, as a consequence

A graph whose owner is drawn as `self` is unreadable, so a confirmed `name` claim
updates the owner node's label. That is 0009's split kept rather than blurred:
the claim is what is **true**, the label is what is **drawn**, and the second
follows the first instead of standing in for it.

Not built:
    Applying it to nodes other than the owner. A name-claim about a third party
    would rename their node too, and that is the same act with a worse failure
    mode — a wrong rename of someone you have one claim about is harder to
    notice than a wrong rename of yourself. It waits for a caller.

## Consequences

**The key becomes `name`, not `user_name`.** The relation name is the key (0008),
and `user_name` presumes the owner — wrong in a graph where any person may have
one. The cost is near zero and was checked rather than assumed: `user_name`
appears nowhere in either package or the console, only in rows the model wrote
and a table accepted. `memory-diff` will report both keys until the table rows
age out.

**It depends on the model saying `kind: "value"` for a name**, which is the
*asked and cannot be held to* pattern for the fourth time in this package, after
per-claim trust, the naming rule itself and relative dates. The answer is the
same one that has worked each time: do not rely on the instruction, make the
failure cheap. §6's kind signature drops a `name` claim whose `dst` is a person,
so **the failure mode is exactly today's behaviour** — the claim is lost and
counted — rather than a wrong node.

**One more relation is speakable**, and speakable content is the surface 0006
guards hardest. It is gated by the same single function as every other
preference, and by confirmation: an extracted name is `inferred` until the owner
says otherwise, so nothing reaches a prompt because a model heard a word.

**Step three of the unification stops being blocked by this.** `user_name` was
the only key the tables held that the graph could not, and it was in every one of
three compared sessions.

### The one to dislike

This amends a record eight days old, and "the record was early" is an argument
available for almost anything. The defence is narrow and should stay narrow:
§9 named one concrete failure — a person node for a string — and a node kind that
did not exist then removes exactly that failure and nothing else. If a later
amendment cannot point at a specific decision that changed underneath it, it is a
different kind of move and should be a supersession.

## Alternatives rejected

**Rename the owner and project the label.** The obvious wiring, and it breaks the
speech boundary: a label has no `origin`, so `preferences_for` cannot gate it and
the guarantee ADR 0017 rests on is lost. It also has nowhere to record who set
the name, since 0009 gives a label no history.

**Keep names out, and let the tables hold `user_name` forever.** Honest, and it
means step four of the unification never completes for a fact every conversation
produces in its first minute.

**Admit `name` with `dst_kind: person`.** Reverts to precisely what §9 caught.
