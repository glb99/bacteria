---
date: 2026-09-27
status: exploring
question: "How should the assistant work in this repository?"
adr: ""
---

# How should the assistant work in this repository?

## Why this session

Set up the way research sessions are recorded, so later design decisions can be made from a shared model. The person writes any ADR that comes out of this.

## Starting model

From the opening message, before this structure existed:

| Prompt | Answer |
| --- | --- |
| What should the assistant do first? | Use AI for researching and understanding. Do not generate code unless told to. The project's AI philosophy is not using AI to generate, but to understand. |
| What does a session start with? | Reasoning about a design decision, or a deep understanding of a concept that will guide a design decision. |
| What must every session produce? | A structured markdown record. The assistant should keep a shared mental model and detect gaps with interviews, quizzes, and similar checks. |
| Who writes ADRs, and where may the assistant write? | The person generates the ADRs. Everything the assistant generates stays in a dedicated folder. |
| How should the structure be built? | In the best way, using skills, plugins, and AGENTS.md. |

## Evidence

- `README.md` says the project's documentation is the ADRs and the codebase, and that this documentation is not AI-generated.
- `docs/adr/index.md` and `docs/adr/adr-template.md` define ADRs as human-maintained MADR records under `docs/adr/`.
- `zensical.toml` publishes the docs site from `docs/` (`edit_uri = "edit/main/docs/"`). `ai/` is outside that tree.
- Grok loads `AGENTS.md` every session. Project skills load from `.grok/skills/`. A project plugin under `.grok/plugins/` stays off until enabled and requires trust, so it would not be the always-on rule.
- Project `.grok/config.toml` can deny edits. User-level config would be required to change the default agent, and that file is outside this repo.

## Inferences

- The always-on rule belongs in `AGENTS.md`, because that file loads without an extra install step.
- The repeatable procedure belongs in `.grok/skills/research-session/`, invoked with `/research-session` or when a message asks to understand, compare, or decide.
- A plugin would wrap the same skill and then wait on trust and an enable flag. That does not make the rule more reliable in this repo.
- A hard deny on `docs/adr/` is what keeps an assistant from writing an ADR even if a later prompt asks it to. The person can still edit those files in their editor.
- `ai/` can sit in the repo without becoming project documentation, because the docs site does not publish it.

## Shared model

The assistant's default job in this repository is to understand, not to change the product. A research session starts from the person's current beliefs, separates checked facts from inferences, and writes that down under `ai/sessions/`. A model counts as shared only after the person confirms it, or explicitly accepts the remaining gaps.

Code, tests, config, and docs change only when the current message explicitly asks for that change. Architecture decision records stay in `docs/adr/` and are written by the person. Assistant-authored files stay under `ai/`.

**Research session** means one concept or design decision, recorded as one markdown file from `ai/session-template.md`.

## Gaps

- The opening message named plugins as a way to build this. No plugin was added. Unchecked whether that omission matches the intent.
- The deny rule blocks the assistant from editing `docs/adr/` even when a later message explicitly asks. Unchecked whether that is too strict.
- `ai/` is not gitignored, so session notes will be committed if the person commits them. Unchecked whether these notes should stay out of git.
- `README.md` gained one sentence pointing at `ai/`. Unchecked whether that sentence belongs in the human-written project readme.
- "Always record the session" is implemented for research sessions. An explicit request to change code does not by itself open a new session file.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| What does the assistant do when you ask it to understand a design choice? | It interviews, records a file under `ai/sessions/`, checks alignment, and does not write code or an ADR. | | |
| You later say "update ADR-0006 to match what we decided." What happens? | The assistant does not edit `docs/adr/`. You write that record. | | |
| Should session notes under `ai/` be committed with the repo? | Open. The structure assumes they can be committed, and that they are not project documentation. | | |

## Handoff for a human ADR

Constraints stated in the opening message: the assistant is for understanding; code only when explicitly requested; ADRs are written by a person; assistant output stays in a dedicated folder; sessions are recorded; shared understanding is checked with interviews and quizzes.

Evidence and open questions are the gaps above. This session does not choose whether to accept the layout as an architecture decision.
