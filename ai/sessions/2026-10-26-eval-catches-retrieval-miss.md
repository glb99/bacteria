---
date: 2026-10-26
status: exploring
question: "Do we have an eval that catches the retrieval error before we change ranking?"
adr: ""
---

# Do we have an eval that catches the retrieval error before we change ranking?

## Why this session

The person wants to fix the retrieval miss from [2026-10-25-retriever-page-index.md](2026-10-25-retriever-page-index.md), where the eval expects page index 3 and the retriever ranks index 4 first. The first step they named is red-green-refactor: know whether an eval already catches that error before changing ranking.

## Starting model

From this message, before the rest of the interview:

> so I want to solve, at first do we have an eval that catches the error? Like in a red-green-refactor methodology

The person then removed the constraint and falsifier prompts from the methodology: "remove that two questions from our methodology, I usually don't fill it".

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | They want to solve the retrieval miss, and the first step is an eval that catches the error, in a red-green-refactor methodology. |
| Which decision would this understanding change? | Whether the next step is to add that failing eval, or to change ranking so an existing eval can go green. |

## Evidence

- `backend/app/src/evals/agent/test_retriever.py` defines `test_retriever_retrieves_correct_page`. It builds the document retriever, asks “what Scaled Dot-Product Attention is?” with `limit=1`, and asserts `retrieved_pages[0].page_index == 3`.
- `build_document_retriever()` in `backend/app/src/app/cli/cli.py` loads every `document_entity` row through `load_stored_entities` and embeds with `GeminiEmbedder`. The eval calls that path with no injected entities.
- `EmbeddingPageRetriever.select_with_metadata` in `backend/app/src/app/agent/retriever.py` sums cosine scores for entities on the same page and returns pages in descending score.
- `backend/app/src/tests/agent/test_retriever.py` asserts `page_index == 3` in `test_select_with_metadata_returns_page_provenance_and_score` on one fixture entity already stored at page 3. The other tests in that file use fixture vectors and do not query the attention article.
- [2026-10-25-retriever-page-index.md](2026-10-25-retriever-page-index.md) records a run, with the local database available, where this query ranked page index 4 first (score 11.12017) and page index 3 sixth (score 9.14876). That session chose to assert index 3 and leave ranking unchanged.
- A first run on 2026-10-26 of `uv run --directory backend/app -m pytest src/evals/agent/test_retriever.py` failed in 262 seconds. The failure was `psycopg.errors.ConnectionTimeout` connecting to `localhost:5432` inside `load_stored_entities`, before the page-index assertion.
- A second run the same day, after the person said the database was up, failed in 2.28 seconds. The assertion was `assert 10 == 3`. The top result was document `fe368576-a8c9-4832-91a1-2f314208faa8`, page index 10, score 11.91825.
- A rank listing on that same database and query, `limit=15`, was: 10 (11.91825), 4 (11.12017), 3 (10.28174), 9 (9.47149), 11 (9.46939), then 6, 0, 5, 7, 1, 8, 2, 13, 14, 12. The top three pages share document `fe368576-a8c9-4832-91a1-2f314208faa8`.
- `just test` runs `uv run -m pytest` with no path. `just cov` runs pytest on `backend/agent/src/tests` and `backend/ingestion/src/tests` only. Source: `justfile`.

## Inferences

- The eval that names this miss is `test_retriever_retrieves_correct_page`. Its assertion is the ground truth from the page-index session. This follows from the eval file and that session.
- The tests in `backend/app/src/tests/agent/test_retriever.py` stay green while the article ranking is wrong, because their page index 3 comes from the fixture. This follows from that file.
- With the database accepting connections, the eval is red because the top page is index 10. The page-index assertion ran and failed. This follows from the second pytest run.
- The 2026-10-25 ranking is not the current ranking. Page 4 still scores 11.12017, and page 3 now scores 10.28174 at rank 3. Page 10 is ahead of both. This follows from the rank listing compared with that session.
- `just cov` does not run this eval. `just test`, given no path arguments, collects `test_*.py` from the repository root, which includes this file. This follows from the justfile and the absence of a pytest `testpaths` setting in `backend/app/pyproject.toml` and the root `pyproject.toml`.

## Shared model

The red check for this retrieval miss is `test_retriever_retrieves_correct_page` in `backend/app/src/evals/agent/test_retriever.py`. It asks “what Scaled Dot-Product Attention is?” and requires the top page index to be 3. It loads stored entities from Postgres and embeds the query. The in-memory retriever tests do not catch this miss.

**Red** here means that eval fails because the top page is not index 3. With the database up, that is what happened: the top page was index 10, score 11.91825, on document `fe368576-a8c9-4832-91a1-2f314208faa8`. Page 4 was second (11.12017) and page 3 was third (10.28174), on that same document.

## Gaps

- The current ranking differs from the 2026-10-25 record, which had page 4 first and page 3 sixth at score 9.14876. The mechanism of the current miss is recorded in [2026-10-26-why-summed-page-score-ranks-page-10.md](2026-10-26-why-summed-page-score-ranks-page-10.md).
- The person has not confirmed this shared model.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| | | | |

## Handoff for a human ADR

No ADR is named. The person has not chosen an option.

Context: the aligned page-index session chose to assert page index 3 and leave ranking unchanged. The person now wants to solve that miss, starting with a red eval. The eval `test_retriever_retrieves_correct_page` asserts index 3 against the live retriever. With Postgres up, that assertion failed: the top page was index 10 (score 11.91825) on document `fe368576-a8c9-4832-91a1-2f314208faa8`. Page 4 was second and page 3 third on the same document. The 2026-10-25 ranking, page 4 first and page 3 sixth, is no longer the current result.

Drivers in the person's words: "so I want to solve, at first do we have an eval that catches the error? Like in a red-green-refactor methodology".

Considered options: not chosen. One option is to treat this live eval as the red test and next change ranking so it goes green. Another is to add a check that fails on the ranking miss without a live database. Outcome stays open.

Open questions: the person has not chosen a ranking change. The summed page score is the recorded reason page 10 wins; see [2026-10-26-why-summed-page-score-ranks-page-10.md](2026-10-26-why-summed-page-score-ranks-page-10.md). No ADR is named.
