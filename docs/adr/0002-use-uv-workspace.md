---
status: proposed
date: 2026-09-14
decision-makers: []
---

# Use uv workspace for repository structure

## Context and Problem Statement

Bacteria needs a well-defined and consistent repository structure.

## Decision Drivers

* Bacteria project is so focused on architecture.
* Codebase must be closed for modification, open for extension, so the most clear boundarties and isolation, the better.
* Just finding the optimal way of structuring a project like this :).

## Considered Options

* Classic pip and requirements.txt (NEVER)
* Use a uv package or app
* Use a uv workspace

## Decision Outcome

Chosen option: "uv workspace", because the isolation it gives, while giving the standard uv local development easibility. Could have gone ahead with a standard uv app or package, but workspace gives complete dependency isolation, packages can be independently distributed, packaged with its own dependencies and tests, which is awesome for me, near 100% decouplement, what makes me happy :).

### Consequences

* Good, because the isolation it gives.
* Bad, because some folders overhead, we will deal with it.

### Confirmation

After building the complete local workflow, commands, actions and Docker packaging (this one is hard), see how our child behaves.

## Pros and Cons of the Options

### Classic pip and requirements.txt

* Good, because mostly nothing but junior adoption.
* Bad, because not a proper python packaging (actually it isn't a package at all), pip is so slow, and needing of some scripts (propably .sh, for our python application, that's not ok) for frozing dependencie version, etc.

### uv package or app

* Good, because it is near what we want, the perfect python packaging, and it's fast!
* Bad, because not modular enough.

## More Information

Nothing (for now).