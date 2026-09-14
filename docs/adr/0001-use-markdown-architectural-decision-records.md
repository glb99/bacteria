---
status: accepted
date: 2026-09-14
decision-makers:
  - Guillermo López
---

# Use Markdown Architectural Decision Records

## Context and Problem Statement

Bacteria needs a lightweight, version-controlled way to retain the reasoning for
architecturally significant decisions as the project evolves.

## Decision Drivers

* Keep decisions near the code and documentation.
* Use a lightweight, well-known structure.

## Considered Options

* Markdown Architectural Decision Records (MADR)
* Unstructured Markdown notes

## Decision Outcome

Chosen option: "Markdown Architectural Decision Records (MADR)", because its
structured Markdown format works naturally with Git and the documentation site.

### Consequences

* Good, because decisions and their rationale are versioned beside the code.
* Bad, because contributors must maintain record status and the ADR index.

### Confirmation

Review architecturally significant changes for a corresponding ADR and verify it
