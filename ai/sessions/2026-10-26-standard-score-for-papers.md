---
date: 2026-10-26
status: exploring
question: "What is the standard retrieval score for papers and architecture articles?"
adr: ""
---

# What is the standard retrieval score for papers and architecture articles?

## Why this session

The person asked for the standard way to score documents of the kind this repository vectorizes: papers and architecture articles. The page-score session is [2026-10-26-standard-page-score.md](2026-10-26-standard-page-score.md). The confirmed first pipeline is in [2026-10-17-pdf-processing-pipeline.md](2026-10-17-pdf-processing-pipeline.md).

## Starting model

> so what is the standard way of doing it for documents kie the ones we want to vectorize (papers, architecture articles...)

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | The standard score depends on the document class. They named papers and architecture articles as the documents to vectorize. |
| Which decision would this understanding change? | Which score to use for that class, given the entity vectors the first pipeline already stores. |

## Evidence

- The confirmed first pipeline splits the PDF into pages, recognizes diagrams and text blocks, embeds each entity, and compares one query vector with those entity vectors. ColPali's patch grid and per-token query score stay out of that pipeline. Source: [2026-10-17-pdf-processing-pipeline.md](2026-10-17-pdf-processing-pipeline.md), confirmed with "yes".
- Faysse et al., "ColPali" (arXiv:2407.01449v6), section 1 and section 3.2, read 2026-10-26. They describe the industrial ingestion of a PDF as parsing or OCR, layout detection, chunking, and an optional caption of figures. Section 3.2 says a representative industrial setup uses Unstructured at high resolution: layout detection, OCR, table reconstruction, and by-title chunking that keeps section boundaries. In the text-only configuration, figures, images, and tables are dropped as noise. Two extensions keep them: OCR the visual elements into their own chunks, or caption them with a vision-language model. Text chunks are embedded with BM25 or BGE-M3. "Chunks are embedded and scored independently, and page-level scores are obtained by max-pooling over the page's chunk scores." The authors add that they validated max-pooling over sub-page chunks as more effective than concatenating every chunk on the page and embedding that page as one vector. https://arxiv.org/html/2407.01449v6
- The same paper, Table 1. ViDoRe's academic tasks include arXivQA, "Scientific Figures from arXiv", and a practical task of scientific documents related to AI. The retrieved unit is the page. Section 5 reports that ColPali's multi-vector late interaction outperforms the Unstructured pipelines on those tasks, with the largest gaps on infographics, figures, and tables.
- ColPali equation (1), recorded in [2026-10-26-standard-page-score.md](2026-10-26-standard-page-score.md): the sum runs over query vectors, and each term is that query vector's best match among the page vectors.
- `EmbeddingPageRetriever` adds every entity cosine on a page. Source: `backend/app/src/app/agent/retriever.py`.

## Inferences

- For papers and visually rich technical articles, the pipeline ColPali calls the industrial standard is: detect structure, make one chunk per textual or visual region, embed and score each chunk on its own, and take the page score as the best chunk score on that page. This follows from section 3.2. Max-pooling is the page reduction they use and the one they found better than embedding the whole page as a single concatenated vector. The paper does not report a comparison against summing chunk scores.
- That page reduction is the one-vector case of MaxSim. A page of citations scores as its closest citation, not as the total of every citation. This follows from section 3.2 together with equation (1) when the query has one vector.
- The method that paper proposes for this same class, including scientific figures and AI papers, is a different index: one vector per image patch, one vector per query token, late interaction, and the page as the result. The processing session left that index for a later comparison. This follows from Table 1, section 5, and the confirmed first pipeline.
- The stored entity pipeline is in the industrial family: regions are embedded separately and one query vector is compared with them. Its current page score, the sum of every entity, is not the max-pool that section 3.2 uses to turn those chunk scores into a page score. This follows from `retriever.py` and section 3.2.
- No source in this session names a separate standard for architecture articles. The closest named class is ViDoRe's scientific and figure-heavy documents. This follows from Table 1.

## Shared model

Papers and diagram-heavy technical articles have two standards in the ColPali paper, and they score a page differently from a sum of every region.

The industrial standard detects layout, chunks by section, and embeds each chunk. Figures are either dropped, OCR'd into their own chunks, or captioned. Each chunk has one score against the query. The page score is the maximum chunk score on that page. ColPali's authors use that max when they reproduce this pipeline, and they found it better than gluing the page's chunks into one vector.

The alternative they propose for this class embeds the page image as one vector per patch and the query as one vector per token, then adds each query token's best patch match. That sum has one term per query token. The processing session kept that alternative out of the first pipeline.

This repository's first pipeline is in the industrial family: one vector per diagram or text block, one query vector. The matching page score in that family is the best entity on the page.

**Industrial page score** in this session means that max over chunk scores, as written in ColPali section 3.2.

## Gaps

- The person has not chosen the industrial page score, the full ColPali index, or the current sum.
- Architecture articles are not a separate corpus in the sources read here. They are included only as diagram-heavy technical documents.
- Section 3.2 does not publish a sum-of-chunk-scores baseline. The claim that max-pooling beat summing is not in the paper.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| | | | |

## Handoff for a human ADR

No ADR is named. The person has not chosen an option.

Context: the retriever sums every entity cosine. The person wants the standard treatment for papers and architecture articles, not a rule chosen for one PDF. The confirmed first pipeline embeds each diagram and text block and compares one query vector. ColPali's patch index was left for later.

Drivers in the person's words: "so what is the standard way of doing it for documents kie the ones we want to vectorize (papers, architecture articles...)".

Considered options: (1) keep the sum of entity cosines; (2) use the industrial page score, the max entity cosine on the page; (3) move to ColPali's page-image vectors and late interaction. Option 2 is the page reduction section 3.2 uses for chunked scientific and technical PDFs, and it matches the embedding shape already stored. Option 3 is the method that paper reports as stronger on ViDoRe, including arXiv figures and AI papers. The person has not chosen.

Consequences: option 2 changes only the reduction in `EmbeddingPageRetriever`. Option 3 replaces the entity index. Option 1 keeps a page total that grows with the number of entities. No change has been made.

Confirmation: not yet.

More Information in the person's words: "so what is the standard way of doing it for documents kie the ones we want to vectorize (papers, architecture articles...)".

Open questions: which option they want. The person next asked for a failing test of the new behaviour in the code that owns it. See [2026-10-26-test-for-page-score.md](2026-10-26-test-for-page-score.md). No source here isolates architecture articles from other diagram-heavy technical documents. No ADR is named.
