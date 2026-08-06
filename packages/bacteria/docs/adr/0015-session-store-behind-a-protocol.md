# 0015 — Put the session store behind a protocol the host implements

## Status

Accepted — 2026-08-06

## Context

`session/store.py` has always described persistence as a second implementation
of the same class: "not a change to any caller." That claim was never true. The
runtime's constructor named the concrete `SessionStore`, so a durable store
would have had to subclass it — inheriting an in-memory dictionary in order to
replace it — or the annotation would have had to change, and with it the claim.

An application is now being built around this package, and it has a database.
The store is where that meets: it is the only layer here whose implementation a
host genuinely needs to replace, and the only one whose gap has been documented
since the beginning.

Two directions were available. The package could depend on the host's
persistence — importing SQLModel, or a storage interface the host defines — or
the host could depend on a shape the package declares. The first is the shorter
path and is how a store usually arrives: the class that needs a database imports
one. It also makes the agent unvendorable anywhere the host's persistence
differs, which is the property this package exists to have.

## Decision

Declare `SessionRepository` in a new `session/protocol.py`: the five methods
already on `SessionStore`, as a structural `Protocol`. `Runtime` is typed
against it. `SessionStore` becomes the in-memory implementation of it and is
otherwise unchanged.

It is deliberately not a CRUD interface. There is no `update`, because an
`update` method is a second write path and [ADR
0004](0004-single-commit-path.md) exists to guarantee there is exactly one.
`remember` and `forget` stay separate from `commit` for the reason in
`store.py`: a memory is a decision with its own lifecycle, not a byproduct of a
turn.

The dependency runs outward. This package declares the shape; whoever hosts it
implements the shape. Nothing here imports a database driver, an ORM, or the
host.

## Consequences

The persistence gap's promise is now true rather than aspirational. A durable
store is an addition made outside this package, and no caller here changes.

The agent stays vendorable. A host with Postgres, SQLite, DynamoDB, or a
key-value store satisfies the same five methods, and this package never learns
which.

The guarantees that actually matter are not in the type system, and this makes
that worse rather than better. `get_state` must return a detached copy;
`commit` must append rather than replace; an unknown id must raise. An
implementation can satisfy every signature and violate all four, and now there
is an explicit invitation to write such an implementation. The protocol's
docstring states them, which is documentation, not enforcement. A conformance
suite parameterized over implementations is what would close this, and it is
recorded as a `Not built:` gap rather than written.

`runtime_checkable` is set, and is worth less than it looks: it verifies the
methods exist and not that they behave. It catches a typo in a method name and
nothing else.

Two names now exist for one idea — `SessionRepository` (the contract) and
`SessionStore` (an implementation) — in a package that has otherwise avoided
that. The alternative, one name in two places, is worse; but a reader meeting
both for the first time has to learn which is which, and the `model` layer's
`protocol.py` / `client.py` split is the precedent that makes it guessable.
