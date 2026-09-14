# Architecture decisions

This directory contains Architecture Decision Records (ADRs): short documents that
capture important technical decisions and the reasoning behind them.

Records use the [Markdown Architectural Decision Records (MADR)](https://adr.github.io/madr/)
format. They are immutable historical records: when a decision changes, create a
new ADR and mark the older record as superseded.

## Records

* [ADR-0001: Use Markdown Architectural Decision Records](0001-use-markdown-architectural-decision-records.md)

## Creating a record

1. Copy [the template](adr-template.md) to `NNNN-short-title-with-dashes.md`.
2. Use the next consecutive four-digit number.
3. Complete the relevant sections, remove unused optional sections, and add the
   new record to the list above.
4. If it replaces a prior decision, update the prior record's status to link to
   the new one.
