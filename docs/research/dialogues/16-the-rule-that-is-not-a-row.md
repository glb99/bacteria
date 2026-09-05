# Dialogue 16 — The rule that is not a row

> Opened 2026-09-05 by the human, while reading the module map:
>
> *"would it be a good idea to use checks.py for evaluation, extracting the rest (rules) to catalogue? why personal domain doesn't have checks.py?"*

Two questions, and they turn out to point opposite ways. The first proposes a split
that is right in principle and wrong in destination. The second sounds like it has
found a gap in the first domain and has instead found that the first domain is the
complete case and the second is the exception.

Underneath both: **this project stores its vocabulary as data and its rules as
code, and only noticed the second half by accident.**

## What the two domains actually do

`personal/` states nine relations and, on each, both halves of a rule:

```python
Relation(
    name="employer",
    invariant="A person has one employer at a time.",
    functional=True,
    ...
)
```

`functional` is the machine-checkable half; `invariant` is the sentence a human
argues with. `graph/constraints.py` evaluates the first **domain-neutrally** —
`conflicts_for(relation, believed, conclusions)` knows nothing about employment.
`personal/graph_views.py:182` renders the second, `relation.invariant or
relation.sentence`, on every conflict badge. So the rule is data, the evaluator is
substrate, and the sentence reaches the person it is about.

`architecture/` states four relations the same way, and then states seven boundaries
a completely different way:

```python
Boundary(
    name="core_names_a_domain_concept",
    sentence="Features own their tables, tasks, and routes. core/ holds nothing that names a domain concept.",
    decides=_core_names_a_domain_concept,
)
```

A tuple of dataclasses in a Python module, with a callable in it.

**So the asymmetry is not that architecture has an extra file. It is that
architecture's rules never became data, and nobody noticed because they arrived in
a domain where the machinery to hold them did not fit.**

## Three reasons they did not fit

Worth stating before proposing anything, because each is a real constraint and the
proposal has to survive all three.

**Scope.** A functional constraint is about *one relation's arity*. A boundary is a
predicate over *the whole graph* — "no edge from `core` to a feature". The substrate
has machinery for the first and none at all for the second.

**Ground truth.** There is a `Derived` to run a predicate against. There is no parse
of a person's life, so *nobody has two employers* can be declared and never
computed. The check that exists for architecture is possible only because the domain
is derivable, which is the same property [dialogue 13](13-the-subject-changed.md)
noted makes architecture fast and unrepresentative.

**Authority, and this is the deep one.** A `Verdict` presumes something entitled to
say *this is wrong*. [§8](../../architecture/memory-graph.md) refuses exactly that for
personal: **the owner's writes are never blocked**, and a constraint violation opens
a negotiation — *your rule says one employer, this says two; fix the fact or fix the
rule?* The constraint layer there is *"a contestable hypothesis about the user's
world"*. Pass/fail over somebody's own life is the wrong act, not a missing feature.

So *"why does personal have no `checks.py`"* has a clean answer: **because it has no
verdict, and everything else `checks.py` provides it already has, in better
places.**

## Why the catalogue cannot take the boundaries

The obvious version of the proposal does not survive contact with the import graph.

```
derive.py     ->  catalogue.py     today, and correct
catalogue.py  ->  derive.py        needed for Rule = Callable[[Derived], ...]
```

`Boundary.decides` is a predicate over `Derived`. Moving `BOUNDARIES` into
`architecture/catalogue.py` means the catalogue importing the adapter: a cycle, and
backwards besides — the ontology would depend on the parser, which is the precise
coupling that module's opening paragraph exists to undo.

The dodge is to move the `sentence` and leave `decides` behind, joined by `name`.
That is the defect PR #101 just removed one level down — two halves of one thing
in two files, matched by a string nothing checks. It should not be reintroduced as
the fix for its own cause.

## The destination `checks.py` already names

The module knows where it is going, and says so:

> `CATALOGUE` says it stays a literal until an authoring route exists, since a rule
> is exactly the sort of thing its owner is entitled to disagree with. **Same here,
> and the same destination:** rows keyed by scope, with a date stated and a date
> retired, so that retiring a boundary is an event rather than a deletion from a
> file.

And under `Not built:`

> Any way for a crossing to be accepted. That is the stated layer above this one —
> an append saying *this edge is fine and here is why* — and it needs somewhere to
> write, which this module deliberately does not have.

[Dialogue 13](13-the-subject-changed.md) named the same thing as the architecture
prototype's actual deliverable: **the boundary lifecycle in the log — stated,
crossed, accepted with a reason, retired with a date. The loop, not merely the
check.**

Four facts say the path is shorter than it looks:

| | |
|---|---|
| **Four of the seven boundaries have `decides=None`** | There is no callable to relocate. They are a sentence and nothing else, and could be rows today. |
| **`decisions.py` already writes stated claims** | `origin="stated"`, `trust="user"`, contrary judgments closed with `closed_by="superseded"`. The machinery exists one level down and was never carried up. |
| **`above` is already a boundary-shaped assertion** | "One layer sits above another" is testimony in the log, added by [dialogue 15](15-the-third-axis.md). The first one is built. |
| **[§5](../../architecture/memory-graph.md) already requires it** | Rules are *"stored as **data, not code** — arbitrary code would need a runtime and a sandbox, and would destroy the property that a human can read and contest a rule."* |

That last line is the awkward one. The model states the rule; the codebase honours
it in one domain and breaks it in the other, and the ADRs record neither.

## Questions

### Q1 — Do boundaries become assertions, and what carries the predicate?

The claim: a boundary is not vocabulary and never was. A functional constraint is a
property of a *relation* — arity, checkable generically, correctly in the catalogue.
A boundary is a *proposition over the graph* with an author and a date, which is the
definition of a claim. It belongs in the log with `origin="stated"`, and
`checks.py` keeps `Cited`, `Boundary`, `Crossing`, `Verdict`, `evaluate()` and the
predicates — becoming what the question proposed, pure evaluation, without the
catalogue being involved at all.

The part that needs deciding is the join. A row carries the sentence; a predicate
lives in code; something matches them. Keying on `name` is the string-matching this
dialogue just refused elsewhere — but the two cases may not be alike: a relation
name re-typed in an adapter was one thing spelled twice, whereas a person-authored
row and a Python function are genuinely different kinds of thing that have to meet
somewhere. **Is that distinction real, or is it the same mistake wearing a better
argument?**

**What would make the whole idea wrong:** that a boundary nobody can author is not
worth making authorable. Seven sentences, lifted from `CLAUDE.md`, changing perhaps
twice a year. A literal tuple is an honest representation of something that rare,
and the log buys contestability nobody has asked to use.

### Q2 — Does an undecidable boundary belong in the log, or only in the file?

Four of seven have `decides=None`, kept deliberately: *"Leaving them out would be
the more convenient design and it would make this a monitor that reports a clean
bill of health on questions it never asked."*

Those four are pure testimony — a sentence a person wrote, with nothing that can
settle it. They are the *easiest* to move and the ones where moving buys least:
nothing evaluates them, so nothing changes except where the words live. Moving only
those would split the seven across two homes on a distinction (*is it decidable*)
that is about the evaluator rather than about the claim, which looks like exactly
the wrong seam.

**Is `elsewhere` the answer?** Two of the four say a test guards them. If a boundary
row can cite what decides it — a predicate name, a test id, or nothing — then
decidable and undecidable are one shape with a field that may be empty, and the
seam disappears.

### Q3 — Does personal get a verdict after all, for a different reader?

Settled above: no pass/fail over somebody's own life. But the argument was about
*authority over the owner*, and there is a second reader the argument does not
cover — **the system asking itself how healthy its own model is.** How many
conflicts are unexplained, how many claims sit in the unratified tail, how far
behind the extraction watermark is.

`architecture/checks.py` produces `Verdict(held, crossings, undecidable,
inapplicable)` and the console draws it. Personal computes conflicts per relation at
read time in `graph_views.py` and reports no aggregate at all.

Is that a missing surface, or the same refusal correctly applied — a health score
over a person's memory being one step from a compliance report about their life?
[§8](../../architecture/memory-graph.md)'s *"a review everyone clicks through is worse
than no review"* argues one way; the [dialogue 13](13-the-subject-changed.md) kill
criterion, which needs a *rejection rate*, needs some aggregate to exist.

### Q4 — Is `invariant` load-bearing, and should the substrate require it?

`invariant` is optional on `Relation`. All nine personal relations set it; five of
architecture's six set it to `None`, including both derived ones.

That is defensible — *`<src> imports <dst>`* needs no invariant because nothing
constrains it — but it means the field that makes a rule contestable is present
exactly where a rule exists and absent where one does not, which is either good
design or an accident nobody has tested. **Should `functional=True` require an
`invariant`?** A functional relation with no sentence produces a conflict badge with
no explanation, which is the failure `graph_views.py:182`'s fallback to `sentence`
is quietly papering over.

---

## What is agreed

*Nothing yet. Opened 2026-09-05.*

---

Related: [dialogue 07](07-relation-vocabulary.md) (the same question one level down —
closed literal, or authored and ratified), [dialogue 10](10-a-place-to-stand.md) Q4
(substrate travels, policy does not), [dialogue 13](13-the-subject-changed.md) (the
boundary lifecycle as the actual deliverable), [dialogue 14](14-the-domain-with-no-package.md)
(rules differ in content, identical in shape — a claim Q1 tests), and
[dialogue 15](15-the-third-axis.md) (`above`, the first boundary-shaped assertion).
