---
date: 2026-10-16
status: aligned
question: "How do we know the PDF ingestion system works?"
adr: ""
---

# How do we know the PDF ingestion system works?

## Why this session

The route session and the pipeline session are aligned. The pipeline session left "what accurate means" open, and named inaccurate extracted text as the observation that shows the visual calls are wrong. The person wants to define the evals before deciding what the read-by-id route returns, so those evals run from the beginning. The person writes any ADR that comes out of it.

## Starting model

From this message, before the rest of the interview:

> before that, I would like to define the way of knowing the system works (evals) to have them running from the beginning

"That" is the read-route result, which was the proposed next session.

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | "I was thinking of having a golden set, some queries and what should be returned, so following modifications for V2, V3 in prompt, processing, models... have a way of being validated" |
| Which decision does this understanding change? | "define the way of knowing the system works (evals) to have them running from the beginning" |
| Which constraint will you not trade away? | "both" — the same queries and expected results stay fixed, and a change that misses an expected result does not ship. |
| What observation would show that belief is wrong? | "Deploying a version of the system that brokes the basic behaviour of the system without detecting it" |

## Evidence

- The route session is `aligned`. Upload accepts one PDF and returns an id with a not-ready status. Read-by-id returns that status. The frontend is the caller. Only PDFs for now. Source: `ai/sessions/2026-10-16-ingestion-rag-for-the-agent.md`.
- The pipeline session is `aligned`. V1 separates that PDF into pages, runs one visual multimodal call per page, and joins the extracted text in page order. The pipeline is independent of the agent. The calls are wrong when the extracted text is not accurate. What "accurate" means, the model provider, and how the agent consumes the RAG are open. Source: `ai/sessions/2026-10-16-pdf-ingestion-pipeline.md`.
- `backend/app/pyproject.toml` and `backend/agent/pyproject.toml` depend on pytest. A search for `def test_` on 2026-10-16 found one test, `backend/agent/src/tests/agent/context/test_context_assembly.py`, which checks that context assembly returns the expected messages. No golden set, no PDF fixture, and no ingestion test were found.
- There is no documents route and no pipeline code. Sources: the two aligned sessions and the search recorded there.

## Inferences

- The decision is the evals that show the ingestion system works, and they exist before the read-route payload is decided. Evidence: the opening message.
- A golden set, in this session, is a fixed list of queries and the results those queries should return. Later changes to the prompt, the processing, and the models are checked against that same list. Evidence: the belief answer and "both."
- A change that misses an expected result does not ship. Evidence: the constraint answer. The falsifier is shipping a version that breaks basic behaviour without the evals detecting it. Evidence: their sentence. Together, an eval that stays green while basic behaviour breaks is a failed eval.
- "Basic behaviour" is not defined. The only behaviour the aligned sessions name as a failure is inaccurate extracted text. The golden set is queries and expected returns, which may be that text or may be something a query asks of the RAG. Evidence: the pipeline session and the belief answer. Those two checks are not yet the same eval.
- The repository has no such set to extend. The one existing test checks the agent's message window. Evidence: the `def test_` search.

## Shared model

This session decides the evals that show the PDF ingestion system works. They run from the beginning, before the read-by-id payload is decided.

An **eval** is a fixed check a change has to pass. A **golden set** is queries plus the results those queries should return. The person believes that set is how V2 and V3 changes to the prompt, the processing, and the models get validated.

Two constraints stay: the queries and expected results stay fixed, and a change that misses an expected result does not ship. The belief is wrong when a version ships that breaks the basic behaviour of the system and the evals do not detect it.

On restatement, basic behaviour is what that set of evals represents. A later change to the prompt, the model, or the processing must not break the behaviour the set records. The queries and expected results stay fixed, and a miss does not ship.

The person considered a database check, in their words "we are evaluating wether the system stores in the database what we want to store?" They then preferred the earlier check. Their words: "I think I preferred that." That check compares the text the visual call returns for a known page with the fixed expected text for that page. It does not read a database row, and it does not retrieve a chunk.

The person first confirmed a page-text check, then chose a different first check. Their words: "The firstcheck I want is the entity recognition over a pdf page." A golden page lists the diagrams, tables, and text blocks. Each entry records where it sits and the text inside the block. A later change to the prompt, the model, or the processing that misses one of those entries does not ship.

The page-text comparison remains the check they preferred before this sentence. It is no longer the first check. The code in `backend/ingestion/src/ingestion/evals.py` still compares one returned string with one expected string. Where "where it sits" is measured, and what a diagram records when it has no text, are unstated. Whether the page-text comparison remains a later check is unstated. The person confirmed this paragraph with "yes that matches". The code in `backend/ingestion/src/ingestion/evals.py` still compares one returned string with one expected string.

## Gaps

- The person confirmed the page-text check and the open items with "yes that matches".
- What counts as a match is unstated. Development started with exact string equality in `backend/ingestion/src/ingestion/evals.py`, so every difference is a miss. That does not choose the match rule.
- No real page and no real expected text have been named. The code loads `page.pdf` and `expected.txt` per case. The committed tree has no case. An empty set fails.
- The person confirmed the revised paragraph with "yes that matches". The first check is entity recognition on a PDF page. The code still compares one text string.
- The set is described as the check on V2 and V3. "From the beginning" is also a driver. Whether V1 must pass the same set before it exists is implied and not said.
- No query, no expected result, and no PDF have been named. The set is a shape, not a list.
- The read-route payload stays outside this session, by the person's order.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| Restate the shared model. | Evals run from the beginning. A fixed golden set of queries and expected results gates changes to the prompt, the processing, and the models. A miss does not ship. The evals fail their purpose if a version ships that breaks basic behaviour and they stay green. What a query returns, and what basic behaviour is, are still open. | "We need to implement a set of evals, that represent the basic behaviour we want the system to have, so that any later change in the prompt, model or processing doesn't broke it" | partial |
| Is the check the pipeline text for a page against the expected text? | Offered, not chosen. | "so, in my own words: we are evaluating wether the system stores in the database what we want to store?" | no |
| Which check do you prefer? | The person's choice. | "I think I preferred that" — "that" is the visual call's text for a known page compared with the expected text, not a database row. | yes |
| Confirm the paragraph that records the page-text check and the open items. | That paragraph, including the open items. | "yes that matches" | yes |
| What is the first check? | The person's choice. | "The firstcheck I want is the entity recognition over a pdf page" | yes |
| Confirm the revised paragraph. | Entity recognition is the first check. Each diagram, table, and text block records where it sits and the text inside the block. The page-text comparison is not the first check. Where it sits, and a diagram with no text, stay open. | "yes that matches" | yes |

## Handoff for a human ADR

One record, not written. The person chose entity recognition on a PDF page as the first check and confirmed the revised paragraph.

### Evals for PDF ingestion — revisit this section

Suggested title, for the person to keep or replace: "Gate ingestion changes on a fixed golden set."

#### Context to carry

The aligned route session chose an upload route and a read-by-id route for one PDF. The aligned pipeline session chose V1: split into pages, one visual call per page, join the extracted text. The pipeline is independent of the agent. Inaccurate extracted text shows the calls are wrong. What "accurate" means is open.

The person wants the evals defined before the read-route result, and running from the beginning. Their belief: a golden set of queries and what should be returned, so later changes to the prompt, the processing, and the models can be validated. On restatement, that set represents the basic behaviour they want the system to have, so a later change in the prompt, model, or processing does not break it. The queries and expected results stay fixed. A change that misses an expected result does not ship.

The repository's only found test checks agent context assembly. There is no golden set.

#### Decision drivers

- The evals run from the beginning, before the read-route payload.
- The same queries and expected results stay fixed.
- A change that misses an expected result does not ship.
- Shipping a break in basic behaviour without detecting it shows the evals are wrong.

#### Considered options

- Named, not chosen as a concrete list. A golden set of queries and expected returns. No query has been written.
- Earlier preference, no longer the first check: one entry is a known PDF page, and the expected return is that page's text. Their words were "I think I preferred that."
- Chosen as the first check, in their words "The firstcheck I want is the entity recognition over a pdf page." A golden page lists diagrams, tables, and text blocks. Each entry records where it sits and the text inside the block.

#### Decision outcome to write

The first check, chosen after the page-text confirmation: entity recognition over a PDF page. A golden page lists diagrams, tables, and text blocks. Each entry records where it sits and the text inside the block. A change that misses one does not ship.

The earlier page-text comparison stays in the record and is not the first check. The person confirmed the revised paragraph with "yes that matches".

Because V1's behaviour is page text, and these evals run before a database document row, a retriever, or an answerer exist. The person set aside the database wording after hearing that distinction.

A question-and-answer golden set is not this decision. What counts as a match, and the actual pages, are not chosen.

#### Consequences

- The eval calls the pipeline and reads its return. It does not read a database row.
- The golden pages and their expected text stay fixed.
- A miss blocks shipping the change.
- The read-route payload and where the text is stored stay outside this session.
- Question answering stays a later set.

#### Confirmation

- One fixed page is run through the visual call.
- The returned text is compared with the fixed expected text.
- A changed prompt that returns different text fails the eval.

#### More Information

> before that, I would like to define the way of knowing the system works (evals) to have them running from the beginning

> I was thinking of having a golden set, some queries and what should be returned, so following modifications for V2, V3 in prompt, processing, models... have a way of being validated

> Deploying a version of the system that brokes the basic behaviour of the system without detecting it

> We need to implement a set of evals, that represent the basic behaviour we want the system to have, so that any later change in the prompt, model or processing doesn't broke it

> so, in my own words: we are evaluating wether the system stores in the database what we want to store?

> I think I preferred that

> what about, as a very initial step, checking the visual entity recognition the system does over a pdf page?

> for example detecting diagrams, tables and text blocks

> also where it sits and the text inside the block

> The firstcheck I want is the entity recognition over a pdf page

#### Left open for the person

- Where "where it sits" is measured.
- What a diagram records when it has no text.
- Whether the page-text comparison remains a later check.
- The code still compares one returned string with `expected.txt`. It does not check entities.
- What counts as a match.
- The actual pages and their expected text.
- Whether V1 must pass the same set.
- The actual queries and expected results.
