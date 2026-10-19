---
date: 2026-10-17
status: aligned
question: "How should the PDF processing pipeline work?"
adr: ""
---

# How should the PDF processing pipeline work?

## Why this session

The person wants to go deeper on the processing pipeline and asked the assistant to read Paul Iusztin, "Stop Converting Documents to Text. You're Doing It Wrong." (Decoding AI, 9 December 2025). The overlapping aligned session is [2026-10-16-pdf-ingestion-pipeline.md](2026-10-16-pdf-ingestion-pipeline.md), which chose the V1 steps. The person writes any ADR that comes out of this.

## Starting model

The opening request, recorded so it is not lost:

> I want to get deeper into how the processing pipeline should work, please read this: https://www.decodingai.com/p/stop-converting-documents-to-text

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | "first, separate the pages, then applying entity recognition to each of them, for extracting diagrams, text... Then embedding that entities into vectors" |
| Which decision does this understanding change? | "I dont know" |
| Which constraint will you not trade away? | "I dont know" |
| What observation would show that belief is wrong? | "something seen in the article or cited paper could make me change my understanding" |

## Evidence

- The person believes the pipeline is: separate the pages, apply entity recognition to each page for extracting diagrams and text, then embed those entities into vectors. They do not know which decision that changes, and they do not know a constraint they will not trade away. Something in the article or a cited paper could change the belief. Source: this session's starting model, 2026-10-17.
- The aligned pipeline session chose three V1 steps: separate the uploaded PDF into pages, run one visual multimodal call per page, and join the extracted text in page order. During that session the person set aside processing each part of the document separately. Source: `ai/sessions/2026-10-16-pdf-ingestion-pipeline.md`.
- The aligned evals session chose entity recognition on a PDF page as the first check. A golden page lists the diagrams, tables, and text blocks. Each entry records where it sits and the text inside the block. Source: `ai/sessions/2026-10-16-ingestion-evals.md`.
- `backend/ingestion/src/ingestion/page.py` defines `PageExtractor.extract_page`. It takes one page as bytes and returns a string. `backend/ingestion/src/ingestion/evals.py` compares that string with one expected string. `backend/ingestion/src/entity_extractor.py` defines a `Box` with a label and edges on a 0–1000 scale, and `extract_entities` splits a string and keeps capitalized words. Nothing in that package embeds a vector.
- Paul Iusztin, "Stop Converting Documents to Text. You're Doing It Wrong." (Decoding AI, 9 December 2025), https://www.decodingai.com/p/stop-converting-documents-to-text, read 2026-10-17. He describes a traditional document workflow of preprocessing, layout detection, OCR plus a specialized model per structure, then structured output. He writes that translating a diagram or a chart into text drops spatial relationships, colors, and context. He says a PDF page can be treated as an image that a multimodal model sees. His diagram example sends one page image to Gemini and asks for 2D bounding boxes of the diagrams. He writes that ColPali showed vision-language models retrieve documents by looking at them rather than by extracting text. For the agent store, he assumes a vector database of images, PDFs converted to images, and text, queried with a multimodal embedding model. Earlier in the same article he names CLIP, OpenCLIP, and SigLIP as image encoders used for multimodal similarity. His reference 5 lists the ColPali authors as "Fostiropoulos, I., et al."
- Faysse, Sibille, Wu, Omrani, Viaud, Hudelot, and Colombo, "ColPali: Efficient Document Retrieval with Vision Language Models" (arXiv:2407.01449v6, last revised 28 February 2025, published at ICLR 2025), https://arxiv.org/html/2407.01449v6, read 2026-10-17. The abstract says modern retrieval indexes the text extracted from pages through lengthy and brittle processes, and proposes retrieval by directly embedding the images of the document pages. Section 1 describes the standard ingestion those systems use: a PDF parser or OCR, layout detection, chunking, and an optional caption of visually rich elements. Section 2 says the task is page-level retrieval, and that a page is the atomic retrieved element: the question is whether the correct document page is retrieved. Section 4 defines ColPali as a PaliGemma-3B model that emits a ColBERT-style multi-vector for a page image: one 128-dimensional vector per text or image token. The query is matched by late interaction, the sum over query vectors of each vector's maximum dot product with a page vector. That sum is one score for the whole page. Section 3.2 reports that contrastive vision-language encoders, including SigLIP-So400m/14, lagged the text pipelines on ViDoRe, and that adding OCR or captions of figures improved the text pipeline at a large indexing cost. The abstract says ColPali largely outperforms those modern document retrieval pipelines and is simpler and faster to index.

## Inferences

- A **page** in this session is one page of the uploaded PDF, held as an image. A **recognized entity** is one diagram or text region the recognition step returns for that page. The ellipsis in "diagrams, text..." is still unnamed. An **entity vector** is the embedding of one recognized entity. A **page-image index** is ColPali's index: many vectors taken from the page image itself, matched to a query by late interaction. A query **token** is one piece of the query after the model's tokenizer splits it. A page **patch** is one cell of the grid the vision encoder cuts the page image into. Each token and each patch has its own vector. Evidence: the person's belief, Faysse et al. section 4, and the person's question on 2026-10-17, "Does it mean that the query is divided by parts?"
- Separating the PDF into pages is the first step of the belief and the first step of the aligned V1 list. Evidence: the starting model and the pipeline session.
- The recognition step in the belief matches the first check the evals session already chose: diagrams and text blocks on a page, with a place and, for text, the text inside. The article's diagram example is the same shape of call: one page image in, boxes out. Evidence: the evals session, Iusztin's object-detection example, and `Box` in `entity_extractor.py`. That code's `extract_entities` reads a string. It does not perform the visual call.
- Embedding those entities is a different index from the page-image index. ColPali embeds the page image and reports that this outperformed pipelines which first extract text, layout, OCR'd figures, or captions and then embed that extracted material. Evidence: Faysse et al. abstract, section 1, and section 3.2. The article points at that paper for the retrieval claim. Evidence: Iusztin, the paragraph after the diagram example.
- The article also names CLIP-style image encoders and a store of whole images. On ViDoRe those contrastive encoders lagged the text pipelines, while ColPali's multi-vector index did not. Evidence: Iusztin's encoder paragraph and Faysse et al. section 3.2. The article and the paper it cites describe two embeddings. The belief names a third: one vector per extracted entity.
- The person left the decision and the constraint as "I dont know". The prior sessions still hold their own choices until this person revises them. The belief revises the aligned V1 product: that session joins extracted text and set per-part recognition aside. This belief makes recognition a pipeline step and stores entity vectors. Evidence: the starting-model answers and the pipeline session. The pipeline session's gaps now record that disagreement.
- The observation inside the named sources that bears on the belief is ColPali's result: on ViDoRe, embedding the page image as multi-vectors beat the extract-then-embed pipelines. The person has not said whether that result changes the belief. Evidence: the falsifier answer and Faysse et al.

## Shared model

The person confirmed this paragraph with "yes" on 2026-10-17.

For now, the pipeline splits the PDF into pages. A foundation model recognizes the diagrams and the text blocks. Each of those entities is embedded as a vector. The query is embedded as one vector and compared with those entity vectors. ColPali's page grid and the per-token score stay out of this first pipeline. Later, those paper techniques can be implemented to see if they improve the result. What "improves" means is still unnamed.

A **page** is one page of the uploaded PDF, held as an image. **Entity recognition** is the foundation-model step that boxes the diagrams and the text blocks on that page. **Entity embedding** stores one vector per recognized entity. A **patch** is one cell of the regular grid a vision encoder cuts a page image into. A **token** is one piece of a query after the tokenizer splits the words. **Late interaction** gives each query token its best score against the patches on a page and adds those scores into one page score. ColPali retrieves the page with the highest page score. The authors are Faysse, Sibille, Wu, Omrani, Viaud, Hudelot, and Colombo. The article's reference 5 names Fostiropoulos.

The first pipeline and ColPali both start by splitting the PDF into pages. The next cut differs. This pipeline boxes diagrams and text blocks and embeds those boxes. ColPali embeds the page grid. A patch can cover a corner of a diagram, a few words, or both. On ViDoRe, that page-image index scored higher than pipelines that extract text, detect layout, OCR figures, or caption figures and then embed the result. The person had that result and kept the entity pipeline for now. The earlier falsifier was a claim in the article or a cited paper. That claim did not replace the approach. The later check is an implementation of the paper's techniques.

The aligned V1 session joins extracted text and sets per-part recognition aside. This confirmed model stores entity vectors instead. The evals session still uses entity recognition as its first check, and that check lists tables as well as diagrams and text blocks.

## Gaps

The person confirmed the model with these left open:

- What "improves" means is unnamed. No metric, no golden set, and no threshold are named for the later comparison. Their "yes" accepted that sentence and did not name the observation.
- The constraint they will not trade away is "I dont know".
- "diagrams, text..." leaves other entity kinds unnamed. The evals session also lists tables.
- Whether the text inside a block is stored beside its vector is unstated. The read-by-id session keeps extracted text off that route.
- What the entity comparison returns, a page or an entity, is unstated. An earlier restatement said the page. That restatement was partial, and the confirmed paragraph stops at the comparison.
- On 2026-10-17 this file said `extract_entities` splits a string and keeps capitalized words. On 2026-10-19 that function loads a PNG path and `GeminiMultimodalClient.send` posts those bytes with mime type `image/png`. The package still does not embed a vector.
- On 2026-10-19 the person chose each paginator page as the bytes of a single-page PDF, sent to the entity call as `application/pdf`, with no PNG from the paginator. That replaces "a page is held as an image" for the paginator. The provider still handles the PDF page as an image inside the model call. The later record is [2026-10-19-pdf-page-split.md](2026-10-19-pdf-page-split.md). This session's shared model was not revised in place.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| Restate the shared model. | Both start by splitting the PDF into pages. The person's pipeline then uses a foundation model to box diagrams and text blocks and embeds those entities. ColPali does not recognize entities. PaliGemma cuts the page image into a regular grid of cells, embeds each cell, embeds each query token, adds one best match per token into a page score, and retrieves the page with the highest page score. | "first the pdf is divided by pages, then an entity recognition, in our case separated by some entities like diagrams, text blocks by using a foundation model, in the case of the paper a specialized model is used, that in that case divides the documments into cells, then that elements are embedded into the database, and finally when the query comes, it is also embedded and compared with the entities or cells, the puntuations are added and the page that contains elements with the highest puntuation is the one retrieved" | partial |
| For now, is the pipeline the entity approach, with paper techniques tried later to see if they improve? | Their words. | "so I think our approach is fine for now, and then we can implement some paper techniques to see if it improves" | yes |
| Does the decision paragraph match? | The paragraph in the shared model, including "What improves means is still unnamed." | "yes" | yes |

## Handoff for a human ADR

One record, not written. The person confirmed the choice on 2026-10-17. The aligned V1 handoff in [2026-10-16-pdf-ingestion-pipeline.md](2026-10-16-pdf-ingestion-pipeline.md) records the earlier joined-text steps. This handoff is the one to reopen for the retrieval store.

### How the PDF processing pipeline works — revisit this section

Suggested title, for the person to keep or replace: "Define what the PDF pipeline stores for retrieval."

#### Context to carry

The person wants to go deeper on the processing pipeline and named Iusztin's article. Their belief is page separation, entity recognition for diagrams and text, then a vector per entity. They do not know which decision that changes, and they do not know a constraint they will not trade away. Something in the article or a cited paper could change the belief.

The aligned route session chose an upload route and a read-by-id route, PDFs only, frontend only. The aligned pipeline session chose: split into pages, one visual call per page, join the extracted text. It set per-part recognition aside. The aligned evals session chose entity recognition on a page as the first check. The aligned read-route session returns processing state and leaves the extracted text off that response. The agent consumes the RAG later, and how is unstated. No ingestion ADR is written.

#### Decision drivers

- The belief, in their words: "first, separate the pages, then applying entity recognition to each of them, for extracting diagrams, text... Then embedding that entities into vectors".
- "I dont know" for the decision this changes, and "I dont know" for the constraint.
- The belief changes if something in the article or a cited paper shows it is wrong. Their words: "something seen in the article or cited paper could make me change my understanding".
- Carried from the aligned sessions, until the person withdraws them: "only pdfs for now", "the front for now", and the pipeline stays independent of the agent.

#### Considered options

- Chosen in the aligned pipeline session, and superseded for the retrieval store by the outcome below: separate the PDF into pages, one visual call per page, join the extracted text in page order.
- Chosen and confirmed in this session: separate the pages, recognize diagrams and text blocks with a foundation model, embed each entity, and compare one query vector with those entity vectors.
- Described by ColPali, left for a later comparison: embed each page image as one vector per patch, embed the query as one vector per token, score them by late interaction, and return the page. The paper reports this outperformed extract-then-embed pipelines on ViDoRe.
- Named by the person's question on 2026-10-17, left with the other paper techniques: keep the diagrams and text boxes, and let each query token score against those boxes.
- Shown in the article as a call, and already the first eval check: send one page image to a multimodal model and get back the diagrams as boxes. The article also names CLIP-style embeddings of whole images. On ViDoRe those encoders lagged the text pipelines.

#### Decision outcome to write

Confirmed by the person with "yes": for now, split the PDF into pages, use a foundation model to recognize diagrams and text blocks, embed each entity as a vector, and compare one query vector with those entity vectors. ColPali's page grid and the per-token score stay out of this first pipeline. Later, those paper techniques can be implemented to see if they improve the result. What "improves" means stays unnamed.

Because they had the ColPali result in front of them and still wanted this sequence. Their words: "so I think our approach is fine for now, and then we can implement some paper techniques to see if it improves." The ViDoRe result describes a stronger page-image index. A claim in the article or a cited paper was the earlier falsifier, and it did not by itself replace the approach.

#### Consequences

- The first pipeline stores a vector per recognized diagram and text block. It does not store ColPali's patch grid.
- The query in that first pipeline is one vector compared with the entity vectors.
- A later change can add paper techniques, including the page-image index and late interaction, and the comparison asks whether that improves the result.
- What "improves" means is still unstated. The current code still returns one string per page and compares that string with an expected string. It does not embed a vector.

#### Confirmation

- The person confirmed the decision paragraph with "yes" on 2026-10-17. That confirmation includes the open meaning of "improves." They did not name the observation that would show a later paper technique improved the result.

#### More Information

> I want to get deeper into how the processing pipeline should work, please read this: https://www.decodingai.com/p/stop-converting-documents-to-text

> first, separate the pages, then applying entity recognition to each of them, for extracting diagrams, text... Then embedding that entities into vectors

> I dont know

> something seen in the article or cited paper could make me change my understanding

> first the pdf is divided by pages, then an entity recognition, in our case separated by some entities like diagrams, text blocks by using a foundation model, in the case of the paper a specialized model is used, that in that case divides the documments into cells, then that elements are embedded into the database, and finally when the query comes, it is also embedded and compared with the entities or cells, the puntuations are added and the page that contains elements with the highest puntuation is the one retrieved

> but in our case, will each query token score with our diagrams and text boxs instead of grid cells?

> so I think our approach is fine for now, and then we can implement some paper techniques to see if it improves

> yes

#### Left open for the person

- What "improves" means. The person confirmed the paragraph that leaves it unnamed.
- The constraint they will not trade away. Their answer was "I dont know".
- Which entity kinds the ellipsis includes, and where the text inside a block is stored.
- What the entity comparison returns.
