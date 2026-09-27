---
name: research-session
description: >
  Run a research session that builds a shared mental model of one concept or
  design decision: an opening interview, sourced reasoning, a session record
  under ai/sessions/, and a closing alignment check. Use when the user wants
  to understand, compare, or decide; to research a design; to check that you
  share a mental model; or when they run /research-session.
argument-hint: concept or decision to understand
metadata:
  short-description: Record a research session and check the shared model
---

# Research session

Build a shared model of one concept or design decision and record it.

The boundaries are in `AGENTS.md`. The report sections are `ai/session-template.md`. File names, the index, and status values are in `ai/README.md`.

## Start

1. Read `ai/README.md`, `ai/sessions/index.md`, and any session whose question overlaps. Read the ADRs and code you will rely on. Do not explain the topic yet.
2. Copy `ai/session-template.md` to a new file as named in `ai/README.md`. Set `date`, `question`, and `status: exploring`. Add a row at the top of the index.
3. Interview in the conversation. Ask only what the person's message has not already answered: what they currently believe, which decision this understanding would change, which constraint they will not trade away, and what observation would show the belief is wrong. Wait for the answers. Write them under **Starting model** in their words.

## Reason

4. Put checked facts under **Evidence**, each with a file path, ADR id, or named source. Put conclusions under **Inferences**, each naming the evidence it rests on. Add a **Gap** as soon as something is unknown, disagreed, or unchecked.
5. Update the session file when the model changes during the conversation.
6. Write **Shared model** in sentences both parties could repeat next time. Define any term this session will keep using.

## Align

7. Run this check in conversation, then fill **Alignment check**:
   - Ask them to restate the shared model.
   - Ask one question aimed at the gap you most suspect.
   - Ask what they would decide. Leave the decision theirs.
8. Set `status` using the meanings in `ai/README.md`. `aligned` requires their confirmation. A skipped check stays `gaps`.
9. Fill **Handoff for a human ADR** with constraints, evidence, and open questions. Do not choose an option.

## Stop

The session record is the deliverable. Wait for an explicit request before any other change.
