---
date: 2026-10-16
status: aligned
question: "What does the read-by-id route return when a PDF is ready?"
adr: ""
---

# What does the read-by-id route return when a PDF is ready?

## Why this session

The route session, the pipeline session, and the eval session are aligned. The route session chose an upload route and a read-by-id route, and stopped at a status. The pipeline session ends as page-ordered extracted text. The eval session checks the visual call's return against expected page text and does not read a database row. The person said to go ahead with the decision that was waiting: what the read route returns when the job is ready. The person writes any ADR that comes out of it.

## Starting model

The person has not yet said what the ready response contains. The aligned route session says the read route returns a status, and the frontend reads it again until the PDF is ready.

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | "the status" |
| Which decision does this understanding change? | What the read-by-id route returns when a PDF is ready. The person said "go ahead" after that decision was named. |
| Which constraint will you not trade away? | "both" — the response never includes the extracted text, and the frontend can tell ready from not-ready. |
| What observation would show that belief is wrong? | "that finally that info is needed, wether from the front or api caller" |

## Evidence

- The route session is `aligned`. The read-by-id route returns a status. The frontend reads the same id until the PDF is ready. The response fields beyond the status were left open. Constraints: "only pdfs for now" and "the front for now." Source: `ai/sessions/2026-10-16-ingestion-rag-for-the-agent.md`.
- The pipeline session is `aligned`. V1 joins extracted text in page order. That text is the pipeline's product. Source: `ai/sessions/2026-10-16-pdf-ingestion-pipeline.md`.
- The eval session is `aligned`. The eval compares the visual call's returned text with expected page text. It does not read a database row. Source: `ai/sessions/2026-10-16-ingestion-evals.md`.
- `backend/app/src/app/api/routes/items.py` `read_item` loads an `Item` by id and returns that item. The existing read-by-id route returns the resource, not a status alone.
- `backend/app/src/app/models.py` has users and items. It has no document row.

## Inferences

- The ready response contains the status and does not contain the extracted text. The frontend can tell ready from not-ready. Evidence: "the status" and "both."
- "That info" in the falsifier is the information this response withholds. The withheld information named in the constraints is the extracted text. The belief is wrong when that text is needed, whether the frontend needs it or an API caller needs it. Evidence: the falsifier sentence read against the constraint. This reading is the one the restatement should confirm.
- The status-only payload can serve the frontend's current job, which is to tell ready from not-ready. It cannot serve a caller that needs the text. Evidence: the constraints and the falsifier.
- The joined text still exists as the pipeline's product and as the eval's input. This route is not where a caller reads it. Evidence: the pipeline session and the eval session.
- Today's item read route returns the item. A status-only document read is a different response than `read_item`. Evidence: `items.py`.

## Shared model

This session decides what the read-by-id route returns when a PDF is ready. On restatement, the endpoint is for checking the processing state. The response contains that state. It never includes the extracted text. The frontend can tell ready from not-ready.

The **processing state** is the status field that distinguishes not-ready from ready. The **extracted text** is the page-ordered text V1 joins. That text stays off this response.

The person confirmed that this endpoint stays a state check until the extracted text is needed, whether the frontend needs it or an API caller needs it. Until then, this route tells the frontend the processing state and does not hand over the text.

Where a caller reads the text once it is needed is outside this response. The repository has no document row. `read_item` returns the item itself.

## Gaps

- The person confirmed the state check and the open items with "yes that matches".
- Status values besides ready and not-ready are unstated. A failed job is not named.
- The route session said the same read route returns the status before the job is ready. Whether the not-ready response is the same shape, status only, is implied by "never includes the extracted text" and not said as its own sentence.
- Which later route or response carries the text, once someone needs it, is unstated.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| Restate the shared model. | The ready read returns the status and never the extracted text. The frontend can tell ready from not-ready. This holds until the frontend or an API caller needs that text. | "The read-by-id endpoint is for checking the processing state" | partial |
| Does this endpoint stay a state check until the extracted text is needed? | Yes. The need can come from the frontend or from an API caller. | "yes it does" | yes |
| Confirm the paragraph that records the state check and the open items. | That paragraph, including the open items. | "yes that matches" | yes |

## Handoff for a human ADR

One record, not written. The person chose the state-only payload and confirmed the shared model, including the open items.

### What the read-by-id route returns when a PDF is ready — revisit this section

#### Context to carry

Upload accepts one PDF, starts the background job, and returns an id with a not-ready status. The frontend reads that id until the status is ready. Only PDFs, and only the frontend, for now. V1 splits the PDF into pages, runs one visual call per page, and joins the extracted text in page order. The pipeline is independent of the agent. The eval compares a known page's returned text with a fixed expected text. It does not read a database row.

#### Decision drivers

- "only pdfs for now" and "the front for now," from the route session.
- "both": the response never includes the extracted text, and the frontend can tell ready from not-ready.

#### Considered options

Named, not chosen as a full payload. The ready response contains "the status."

#### Decision outcome to write

Chosen and confirmed. The read-by-id endpoint checks the processing state. The response carries that state and never the extracted text. The frontend can tell ready from not-ready. The endpoint stays a state check until the frontend or an API caller needs the extracted text.

Because the frontend's current job is to learn whether processing is ready, and the extracted text is a later need. The person confirmed the paragraph, including the open items, with "yes that matches".

#### Consequences

- The ready response has a state the frontend can read as ready.
- The body does not include the joined page text.
- The pipeline's text and the page-text eval stay off this route.
- A later need for that text, from the frontend or from an API caller, ends this payload.
- Failed, and any state besides ready and not-ready, is unnamed.
- Where the text is read once it is needed is unnamed.

#### Confirmation

- A ready document returns a state the frontend can tell from not-ready.
- The body contains no extracted text.

#### More Information

The person said "go ahead" when the next decision was named as what the read-by-id route returns when the job is ready.

> the status

> that finally that info is needed, wether from the front or api caller

> The read-by-id endpoint is for checking the processing state

#### Left open for the person

- Status values besides ready and not-ready.
- Where a caller reads the text once it is needed.
