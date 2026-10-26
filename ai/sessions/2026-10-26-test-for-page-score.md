---
date: 2026-10-26
status: exploring
question: "Where does the test for the new page score belong?"
adr: ""
---

# Where does the test for the new page score belong?

## Why this session

The person wants a failing test for the new page score before changing the retriever, in the part of the code that owns that score. The score for papers and technical articles is the industrial page score in [2026-10-26-standard-score-for-papers.md](2026-10-26-standard-score-for-papers.md): the best entity cosine on the page.

## Starting model

> so first I would want to define a test that catches, the new behaviour we want, in the exact part of the code it should, so guide me

They then asked which directory: "in the evals/ or in tests/?"

They then asked whether the new test would resemble the existing one: "would it be similar to tests like test_select_returns_the_highest_scoring_page_image? Explain me how it works"

They then asked what carries the vector: "but are pages vectorized, or entities?"

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | The next step is a test that catches the new behaviour, placed in the exact part of the code that owns it. |
| Which decision would this understanding change? | Which test defines the page score before `EmbeddingPageRetriever` changes. |

## Evidence

- `process_document` writes one page image per page and calls `embed(label.encode())` once per non-empty detected label. Source: `backend/app/src/app/api/services/document_service.py`. `Page` stores `document_id`, `page_index`, and `image_path`, and has no vector. `DocumentEntity` stores the label, the box, the page index, and the vector. Source: `backend/app/src/app/models.py`.
- `EmbeddingPageRetriever.select_with_metadata` embeds the query once, adds `_cosine` for every entity that shares a document id and page index, and sorts pages by that sum. `select` returns the page images from that ranking. Source: `backend/app/src/app/agent/retriever.py`. The class docstring says entity scores on the same page are added. The only other `embed(...)` call under `backend/app/src` is a protocol test.
- `backend/app/src/tests/agent/test_retriever.py` builds `EmbeddingPageRetriever` with an in-memory `embed` callable and `StoredEntity` values. No database and no Gemini call. `test_select_returns_the_highest_scoring_page_image` puts two perfect matches on page 1 and one zero match on page 0. The sum and the best-entity score both rank page 1 first. `test_select_with_metadata_returns_page_provenance_and_score` uses one entity, so its score of `1.0` is both the sum and the max.
- `backend/app/src/evals/agent/test_retriever.py` calls `build_document_retriever()`, which loads stored entities and embeds the query with `GeminiEmbedder`. It asserts the top page index is 3 for the attention question. A run with the database up failed with `assert 10 == 3`. Source: [2026-10-26-eval-catches-retrieval-miss.md](2026-10-26-eval-catches-retrieval-miss.md).
- With query vector `[1.0, 0.0]`, three entities `[0.6, 0.8]` have cosine `0.6` each and a page sum of `1.8`. One entity `[1.0, 0.0]` has cosine `1.0`. The current sum ranks the three-entity page first. The best-entity score ranks the single-entity page first and reports score `1.0`. This follows from `_cosine` in `retriever.py`.

## Inferences

- The behaviour to lock is the industrial page score: the returned page is the page of the closest entity, and the reported score is that entity's cosine. This follows from the papers session and from the code that adds cosines.
- That behaviour is owned by `select_with_metadata`. A test of it belongs in `backend/app/src/tests/agent/test_retriever.py`, beside the tests that already construct `EmbeddingPageRetriever` with fixed vectors. This follows from the two test files.
- The existing unit tests stay green if the sum changes to a max, because their fixtures never make the sum and the max disagree. They do not catch the new behaviour. This follows from those fixtures.
- The article eval catches a wrong page on one stored document. It also runs parsing, embeddings, and the database. It does not isolate the page score. This follows from `build_document_retriever` and the eval body.
- A unit test with the three-against-one fixture above fails on the current sum and passes when the page score is the best entity cosine. The eval remains the later check that the stored article returns page 3. This follows from the cosine arithmetic and the eval assertion.

## Shared model

Entities are vectorized. A page is the image file for one page index, and it has no vector of its own. Each diagram or text block on that page is an entity: its label is embedded, and that vector is stored with the page index. The retriever scores those entity vectors and returns the page image.

The new behaviour is the industrial page score. For one query vector, the page returned by `EmbeddingPageRetriever` is the page that holds the closest entity, and `RetrievedPage.score` is that entity's cosine.

The test that catches it is a unit test in `backend/app/src/tests/agent/test_retriever.py`. It calls `select_with_metadata` with a fixed embedder. One page has several moderate entity cosines whose sum is larger. Another page has one higher cosine. The assertion is the page index and the score of that closer entity. Today the sum returns the crowded page, so the test is red before any production change.

The article eval in `backend/app/src/evals/agent/test_retriever.py` stays the check that the stored paper returns page 3. It is not the test that defines the page score.

**Page-score test** in this session means that unit test.

## Gaps

- The test has not been written. The person asked to be guided.
- The person asked whether the new test goes in `evals/` or `tests/`. The answer recorded here is `tests/`. They have not confirmed that in their own words.
- `select` was removed after this record. The page-score test calls `select_with_metadata`. Image bytes are `RetrievedPage.content`.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| | | | |

## Handoff for a human ADR

No ADR is named. The person has not chosen an option.

Context: the retriever sums entity cosines. The industrial page score for the current one-vector pipeline is the best entity cosine. The person wants a failing test for that behaviour in the code that owns it, before changing the retriever.

Drivers in the person's words: "so first I would want to define a test that catches, the new behaviour we want, in the exact part of the code it should, so guide me".

Considered options: (1) extend the live article eval only; (2) add the page-score test in `tests/agent/test_retriever.py` and leave the article eval as the later end-to-end check. The guidance in this session describes option 2. The person has not confirmed it, and the test file has not been edited.

Consequences: option 2 fails on the current sum and names the scoring rule without a database or an embedding API. Option 1 keeps failing for every cause that can rank a stored page above page 3. No test has been added.

Confirmation: not yet.

More Information in the person's words: "so first I would want to define a test that catches, the new behaviour we want, in the exact part of the code it should, so guide me".

Open questions: whether they want the test written next. No ADR is named.
