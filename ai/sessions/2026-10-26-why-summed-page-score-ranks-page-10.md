---
date: 2026-10-26
status: exploring
question: "Why does the retriever return page 10 instead of the Scaled Dot-Product Attention page?"
adr: ""
---

# Why does the retriever return page 10 instead of the Scaled Dot-Product Attention page?

## Why this session

The eval in [2026-10-26-eval-catches-retrieval-miss.md](2026-10-26-eval-catches-retrieval-miss.md) is red: for “what Scaled Dot-Product Attention is?” the top page is index 10. The person asked what fails.

## Starting model

> so explain me with detail what do you think fails

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | They asked for an explanation of the failure. They have not stated their own cause. |
| Which decision would this understanding change? | Which ranking change would make `test_retriever_retrieves_correct_page` pass. |

## Evidence

- `EmbeddingPageRetriever.select_with_metadata` in `backend/app/src/app/agent/retriever.py` embeds the query once, adds `_cosine` for every entity on a page, and sorts pages by that sum. `limit=1` returns the page with the largest sum.
- `process_document` in `backend/app/src/app/api/services/document_service.py` embeds each non-empty detected label and stores that vector on `document_entity`. The retriever scores those stored vectors. It does not read the label text at query time.
- A breakdown on 2026-10-26, same query, same database, 189 entities across 15 pages of document `fe368576-a8c9-4832-91a1-2f314208faa8`:

  | Page | Entities | Sum | Max entity | Mean |
  | --- | --- | --- | --- | --- |
  | 10 | 21 | 11.9182 | 0.6558 | 0.5675 |
  | 4 | 17 | 11.1202 | 0.7255 | 0.6541 |
  | 3 | 14 | 10.2817 | 0.8925 | 0.7344 |

- Sorted by the single best entity, page 3 is first (0.8925) and page 10 is tenth (0.6558). Sorted by mean cosine, page 3 is first (0.7344) and page 10 is near the bottom of the article pages (0.5675).
- The strongest entities on page 3 are the section heading `3.2.1 Scaled Dot-Product Attention` (0.8925), `Scaled Dot-Product Attention diagram` (0.8801), and the sentence that begins `We call our particular attention "Scaled Dot-Product Attention"` (0.8258).
- The strongest entities on page 10 are bibliography lines. The best is a citation of Yoon Kim et al., Structured attention networks, at 0.6558. The next five are also citations that mention attention.
- Page 4’s strongest entities are the multi-head attention formulas and the paragraphs that follow section 3.2.1. Its best entity scores 0.7255.
- Each of page 3’s top six entity scores is higher than each of page 10’s top six.

## Inferences

- The query embedding and the stored heading agree. The best match in the corpus is the Scaled Dot-Product Attention heading on page 3. This follows from the per-entity cosines.
- Page 10 ranks first because the page score is a sum. Twenty-one citation boxes, each with a middling cosine, add up to more than fourteen stronger boxes on page 3. This follows from the sum table and the labels on page 10.
- A page score that used the best entity, or the mean cosine, would rank page 3 first for this query. This follows from the same table. That is an observation about this query, not a decision to change the retriever.
- The same sum explains the 2026-10-25 result that page 4 outranked page 3. Page 4 has more boxes than page 3, and those boxes are about attention, so their sum can pass the page that holds the heading. This follows from the retriever code and that session’s ranks. Today’s entity counts put page 10 ahead of page 4.

## Shared model

The retriever finds the right text and then ranks the wrong page. Each stored box is embedded from its label. For this query, the closest box is the heading `3.2.1 Scaled Dot-Product Attention` on page 3, cosine 0.8925. The page score is the sum of every box on the page. Page 10 is a bibliography page with 21 citation boxes. Their cosines sit around 0.55 to 0.66, and the sum is 11.9182. Page 3 has 14 boxes and a higher mean, 0.7344, but a lower sum, 10.2817. With `limit=1`, the eval receives page 10.

**Page score** in this session means that sum. The failure, relative to the agreed ground truth that the top page is index 3, is the page score. The embedding of the heading is the strongest match in the stored set.

## Gaps

- The person has not chosen whether the page score should stay a sum, become the best entity, become the mean, or become some other reduction.
- Why today’s entity set differs from the 2026-10-25 ranking is unchecked. The sum rule accounts for both rankings.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| | | | |

## Handoff for a human ADR

No ADR is named. The person has not chosen an option.

Context: the aligned page-index session says the eval should expect page index 3 for this query. The live eval fails because the top page is 10. The heading, the diagram label, and the definition sentence are stored on page 3 and are the closest entities to the query. `EmbeddingPageRetriever` adds every entity cosine on a page and returns the page with the largest sum. Page 10 has 21 bibliography boxes and the largest sum.

Drivers in the person's words: "so explain me with detail what do you think fails". The earlier driver for the red eval is "so I want to solve, at first do we have an eval that catches the error? Like in a red-green-refactor methodology".

Considered options: (1) keep the sum; (2) rank a page by its best entity; (3) rank a page by the mean cosine; (4) some other reduction. For this query, option 2 and option 3 both put page 3 first, and option 1 puts page 10 first. The person has not chosen.

Consequences: keeping the sum lets a page with many moderately related boxes outrank the page that contains the closest box. Changing the reduction changes which page `limit=1` returns and whether `test_retriever_retrieves_correct_page` passes. No change has been made.

Confirmation: not yet.

More Information in the person's words: "so explain me with detail what do you think fails".

Open questions: which page-score reduction they want. The standard operator is recorded in [2026-10-26-standard-page-score.md](2026-10-26-standard-page-score.md). No ADR is named.
