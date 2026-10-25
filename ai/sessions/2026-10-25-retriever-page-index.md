---
date: 2026-10-25
status: aligned
question: "Should the retrieval eval expect page index 3?"
adr: ""
---

# Should the retrieval eval expect page index 3?

## Why this session

Determine whether the expected result in the retriever eval agrees with the repository's page-index convention and actual retrieval result.

## Starting model

The person suspects the eval should retrieve index 3 rather than index 4.

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | The eval should retrieve index 3. |
| Which decision would this understanding change? | Whether the eval should assert index 3 or index 4. |
| Which constraint will you not trade away? | Not supplied. |
| What observation would show that belief is wrong? | Not supplied. |

## Evidence

- `backend/app/src/app/api/services/document_service.py` uses `enumerate(iterate_pages(...))` as `page_index`, so indexes are zero-based.
- `backend/app/src/tests/api/services/test_process_document.py` asserts that two sequential pages are stored with indexes `[0, 1]`.
- `backend/app/src/app/agent/retriever.py` sums cosine similarities for all entities on a page and ranks pages by descending summed score.
- `backend/app/src/evals/agent/test_retriever.py` asks “what Scaled Dot-Product Attention is?” and currently expects page index 4.
- Runtime check of the eval retriever against the configured local data returned page index 4 at rank 1 (score 11.12017) and page index 3 at rank 6 (score 9.14876).
- Stored entity labels for page index 3 include `3.2.1 Scaled Dot-Product Attention` and explanatory text defining it. Page index 4 begins with continuation text (“output values. These are concatenated...”) and later sections. Thus the relevant section heading is on zero-based page index 3, the fourth PDF page; index 4 is the fifth page.
- The interview prompts about decision drivers, constraint, and falsifier were left blank.

## Inferences

- If the eval's intended ground truth is the page containing the section titled “Scaled Dot-Product Attention,” index 3 is the correct expected page, based on the ingestion indexing convention and stored labels.
- The current eval expectation of 4 records the current retriever's observed top result rather than the page containing the target section. This follows from the eval and runtime rank output.
- The retriever is not returning index 3 as its top result because it aggregates cosine scores across page entities; index 3 ranks sixth for this query. The test expectation alone does not correct that retrieval behavior.

## Shared model

Provisional: page indexes are zero-based. For the “Scaled Dot-Product Attention” section heading, the expected page is index 3. The current retrieval algorithm ranks index 4 first and index 3 sixth for the query, so the current assertion of 4 reflects actual behavior, not the page that contains the section heading.

## Gaps

- The person chose to make the eval assert index 3 only, letting it expose the retrieval miss; changing ranking behavior is outside this choice.
- A separate non-negotiable constraint and falsifier were not supplied.
- The runtime check depended on the currently configured local database and Gemini embedding behavior; results may change as stored entities or model behavior change.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| Which index contains the section heading? | Index 3, because ingestion indexes from zero and the stored section heading is on the fourth PDF page. | “the Scaled Dot-Product Attention section is in 3.png” | Yes |
| Why does the current test expect 4? | The retriever currently ranks index 4 first; index 3 is rank 6. | The user chose to assert ground truth at index 3, exposing the retrieval miss. | Yes |
| What change should follow? | Correct the expected page index to 3; leave retrieval algorithm changes for a separate request. | Chose “ground_truth_only”. | Yes |

## Handoff for a human ADR

No ADR is named.

Context: The person suspects the retriever eval should expect page index 3 instead of 4. Ingestion uses zero-based page indexes. Stored labels place the target section heading on index 3; index 4 contains continuation text. However, the current embedding retriever ranks index 4 first and index 3 sixth for this query, and the eval currently asserts the observed top result.

Considered outcomes: (1) change the expected index to 3, making the eval fail and exposing the retrieval miss; (2) keep the current expected index 4 as a behavioral snapshot; (3) improve retrieval ranking and update the eval to assert index 3. The person chose outcome 1: assert ground truth only and let the test expose the miss, because the section is in `3.png`.

Consequences: the eval will fail until retrieval is corrected; that failure distinguishes correctness ground truth from current output. No retrieval algorithm change was selected.

Confirmation: the person restated the page location as “the Scaled Dot-Product Attention section is in 3.png” and chose `ground_truth_only`.

More Information in the person's words: “look at the test, shouldn't it retrieve index 3?”; “the Scaled Dot-Product Attention section is in 3.png”.

Open questions: what retrieval change will make index 3 rank first; the person did not state a separate constraint or falsifier. No ADR is named.
