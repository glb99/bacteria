---
date: 2026-10-26
status: exploring
question: "What is the standard way to score a page from many entity vectors?"
adr: ""
---

# What is the standard way to score a page from many entity vectors?

## Why this session

[2026-10-26-why-summed-page-score-ranks-page-10.md](2026-10-26-why-summed-page-score-ranks-page-10.md) found that the page score is a sum of entity cosines, and that the best entity is already on page 3. The person asked for the standard way to score a page, and said they do not want a ranking rule chosen because it fits this kind of document.

## Starting model

> what is the standarized way of doig it? I don't want to use a different top page algorithm only because it would work for this type of documents

The person then asked whether ColPali's sum belongs to ColPali's embedding method: "so, colipal suggests the sum, but for their concrete embedding metodology?"

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | They want the standardized page score. They do not want a top-page algorithm chosen because it works for this type of document. They read ColPali's sum as tied to ColPali's embedding method. |
| Which decision would this understanding change? | Which reduction replaces the sum in `EmbeddingPageRetriever`, if any. |

## Evidence

- `EmbeddingPageRetriever` embeds the query once and adds `_cosine` for every entity on a page. Source: `backend/app/src/app/agent/retriever.py`. `GeminiEmbedder.__call__` returns one vector for the whole input text. Source: `backend/app/src/app/llm/embeddings.py`.
- The aligned processing session kept this first pipeline: one query vector compared with one vector per recognized entity. It left ColPali's per-token late interaction out of that pipeline. Source: [2026-10-17-pdf-processing-pipeline.md](2026-10-17-pdf-processing-pipeline.md), confirmed with "yes".
- Khattab and Zaharia, "ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction over BERT" (arXiv:2004.12832v2, SIGIR 2020), section 3.3, equation (3). The relevance score is a sum of maximum similarities. For each query embedding, take its maximum cosine against the document embeddings, then add those maxima. The sum has one term per query embedding. https://arxiv.org/html/2004.12832v2
- Faysse et al., "ColPali" (arXiv:2407.01449v6), section 4.1, equation (1), read 2026-10-26. The query and the page are each a bag of vectors, \(\mathbf{E_q}\) with \(N_q\) vectors and \(\mathbf{E_d}\) with \(N_d\) vectors. The late interaction score is the sum over the query vectors of each query vector's maximum dot product with a page vector: \(\mathrm{LI}(q,d)=\sum_{i=1}^{N_q}\max_{j=1}^{N_d}\langle\mathbf{E_q}^{(i)}|\mathbf{E_d}^{(j)}\rangle\). Section 4.1 projects every language-model output token, text or image, to a 128-dimensional vector. Section 4.2 appends five expansion tokens to the query, so \(N_q\) counts query tokens plus those five. Section 5 contrasts this with BiPali, the single-vector bi-encoder from the same backbone: one pooled representation and one similarity, and the multi-vector late interaction is the step-change over that bi-encoder. https://arxiv.org/html/2407.01449v6
- Lee, Sung, Kang, and Chen, "Phrase Retrieval Learns Passage Retrieval, Too" (arXiv:2109.08133), equation (3). With one query vector and many phrase vectors, the passage score is the maximum phrase score inside the passage. https://arxiv.org/html/2109.08133v1
- On the stored Transformer paper, the same query, one query vector: the max entity cosine ranks page 3 first (0.8925) and page 10 tenth (0.6558). The sum ranks page 10 first because that page has 21 entities. Source: [2026-10-26-why-summed-page-score-ranks-page-10.md](2026-10-26-why-summed-page-score-ranks-page-10.md).

## Inferences

- ColPali's sum is the late-interaction operator for the two bags its model emits. \(N_q\) is the number of query-token vectors, including five expansion tokens. \(N_d\) is the number of image-patch vectors from the page image. Each query vector adds one term, its best dot product with a patch. The page's patch count changes which patch wins the max. It does not change how many terms the sum has. This follows from equation (1), section 4.1, and section 4.2.
- The same paper's single-vector model, BiPali, does not use that sum. It matches one query representation to one page representation. The sum appears when they keep one vector per token and per patch. This follows from section 5.
- With the one query vector this pipeline already stores and compares, MaxSim has a single term. That term is the best entity cosine on the page. This follows from equation (3) with one query embedding, and it is the same reduction DensePhrases writes as the passage score. It is the standard operator applied to the current embedding shape. It is not a rule derived from bibliography pages.
- The current page score adds a term for every entity. The number of terms is the number of boxes on the page. Any page with more positively scored boxes can outrank the page that holds the closest box. The citation page is one case of that count. This follows from `retriever.py` and the score table.
- Mean cosine also removes the count, and for this query it ranks page 3 first. It is not the operator in ColBERT equation (3) or in the DensePhrases passage score. This follows from those formulas and from the score table.

## Shared model

The standard score for many stored vectors is MaxSim. Each query vector contributes its best similarity to any stored vector on the page, and those best similarities are added. The sum has one term per query vector.

This pipeline embeds the query as one vector and each recognized entity as one vector. Under MaxSim that page score is the single best entity cosine. The page returned for `limit=1` is the page that holds the closest entity. DensePhrases states that same max for one query vector and many phrase vectors.

The score in `EmbeddingPageRetriever` is a different reduction: it adds every entity cosine. That total grows with the number of entities on the page whenever those cosines are positive. That growth is a property of the sum, for any document whose pages contain different numbers of entities.

**MaxSim** in this session means that operator. ColPali equation (1) is the same sum, written for their embeddings: one 128-dimensional vector per query token and one per image patch. The sum is part of that embedding method. It is the score those bags are trained and queried with. A single pooled vector, which is BiPali in the same paper, uses one similarity and no sum over patches.

The processing session left that query-side split out of the first pipeline. The one-vector case of the same operator is the best entity on the page.

## Gaps

- The person has not chosen whether to use the one-vector case of MaxSim, to add query-token vectors and the full operator, or to keep the sum.
- Mean cosine is recorded only as a different reduction. No source in this session names it as the standard page score.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| | | | |

## Handoff for a human ADR

No ADR is named. The person has not chosen an option.

Context: the retriever adds every entity cosine on a page. For the attention query that sum ranks a 21-entity bibliography page above the page that holds the closest entity. The person wants the standard score and does not want a rule chosen because it fits this kind of document. The confirmed first pipeline compares one query vector with entity vectors and leaves per-token late interaction for later.

Drivers in the person's words: "what is the standarized way of doig it? I don't want to use a different top page algorithm only because it would work for this type of documents".

Considered options: (1) keep the sum of every entity cosine; (2) use the one-vector case of MaxSim, which is the best entity cosine on the page; (3) embed the query as one vector per token and use the full MaxSim sum. Option 2 is equation (3) when the query has one vector, and it is the DensePhrases passage score. Option 3 is the operator ColBERT and ColPali define, and this repository already left it out of the first pipeline. The person has not chosen.

Consequences: option 2 changes the page score without a new embedding shape, and on the current stored document it returns page 3 for this query. Option 3 needs query-side vectors that `GeminiEmbedder` does not return. Option 1 keeps a score that increases with the entity count. No change has been made.

Confirmation: not yet.

More Information in the person's words: "what is the standarized way of doig it? I don't want to use a different top page algorithm only because it would work for this type of documents"; "so, colipal suggests the sum, but for their concrete embedding metodology?"

Open questions: which of the three options they want. The score used for papers and technical articles is recorded in [2026-10-26-standard-score-for-papers.md](2026-10-26-standard-score-for-papers.md). No ADR is named.
