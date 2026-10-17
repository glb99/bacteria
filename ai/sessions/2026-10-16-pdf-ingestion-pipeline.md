---
date: 2026-10-16
status: aligned
question: "How does the background job turn an uploaded PDF into a ready document?"
adr: ""
---

# How does the background job turn an uploaded PDF into a ready document?

## Why this session

The route session [2026-10-16-ingestion-rag-for-the-agent.md](2026-10-16-ingestion-rag-for-the-agent.md) is aligned. It chose an upload route and a read-by-id route for PDFs, with the frontend as the caller. The upload route starts a background job. This session is that job: how a PDF becomes ready. The person writes any ADR that comes out of it.

## Starting model

Carried from the route session, in the person's words:

> probably the bbest option is to process documents as images, then recognizing the elements

The same session also called this work a heavy processing pipeline managed by a background job. The falsifier there was "I dont know". The pipeline was not chosen.

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | "probably the bbest option is to process documents as images, then recognizing the elements" |
| Which decision does this understanding change? | "the V1 of the pipeline steps" |
| Which constraint will you not trade away? | "I don't know". Later, correcting the model: "but is it independent from the agent, this is a processing pipeline for the rag that then the agent will consume" |
| What observation would show that belief is wrong? | "the extracted text is not accurate" |

During the alignment restatement the person replaced the image-and-elements belief:

> Instead of processing each part of the document separatelly, we use a simpler pipeline of multimodal model calls to process it visually

## Evidence

- The route session is `aligned`. Its shared model says the upload route accepts a PDF, starts a background job, and returns an id with a not-ready status. The read-by-id route returns that status. The frontend reads it again until the PDF is ready. Constraints: "only pdfs for now" and "the front for now." Source: `ai/sessions/2026-10-16-ingestion-rag-for-the-agent.md`.
- A search of the repository on 2026-10-16 for `pdf`, `ocr`, `pymupdf`, `pdfminer`, `unstructured`, `tesseract`, `pillow`, and `poppler` in `*.py`, `*.toml`, `*.txt`, and `*.md` found matches only in the two ingestion session records. No pipeline code and no PDF library are in the tree.
- `backend/app/pyproject.toml` depends on FastAPI, `python-multipart`, and the database stack. It has no document-processing library. `backend/app/src/app/models.py` has users and items, not documents. `backend/agent/src/agent/context.py` assembles a message window and does not read a document.
- `backend/agent/src/agent/model.py` `GeminiClient.send` accepts message content as a string or as a list of blocks. The blocks it builds are text, function calls, and function responses. Any other block type raises `ContractError` with "unsupported content block type". The default model name in that client is `gemini-3.5-flash`. That client does not send an image.
- Gemini's document-understanding guide says a PDF request supports up to 50 MB or 1,000 pages, each page is handled as an image, and larger pages are scaled down to at most 3072×3072. The same guide says a long document can be split into multiple PDFs. Source: https://ai.google.dev/gemini-api/docs/document-processing (read 2026-10-16). Firebase's input guide says the same page and size caps and, for a long document, to consider splitting it. Source: https://firebase.google.com/docs/vertex-ai/input-file-requirements (read 2026-10-16).
- Claude's PDF guide caps a request at 600 pages, or 100 pages for a 200k-token model, and says dense PDFs can fill the context window before the page cap. It says to split large PDFs into chunks. Source: https://platform.claude.com/docs/en/build-with-claude/pdf-support (read 2026-10-16). Claude's help center says visual analysis of charts and graphics applies under 100 pages, and past that the PDF is processed as text only. Source: https://support.anthropic.com/en/articles/8241126-what-kinds-of-documents-can-i-upload-to-claude-ai (read 2026-10-16).
- Ma et al., "Locating Failure in Multi-Page Visually Rich Document Understanding" (arXiv:2608.07943, 2026-08-24), report that on their TLV setting accuracy falls from 64.6 on single-page questions to 38.6 once the evidence spans two pages. Withholding one required page drops accuracy from 38.6 to 18.5. They also report that vision does not replace a text channel. Source: https://arxiv.org/html/2608.07943 (read 2026-10-16).
- Chen et al., "Heading Hierarchy Reconstruction for Complex and Long Documents" (arXiv:2610.18238, 2026-10-13), write that vision-language models extract page-level elements accurately, and that input resolution and context length make it infeasible to process every page image of a long document in one call. Page-by-page heading predictions lose document-level consistency. Source: https://arxiv.org/abs/2610.18238 (read 2026-10-16).
- A vendor note from AnyFormat, last evaluated October 2026, says a whole file in one model call drops rows because the reply is shorter than the document and because the middle of a long input is read worse, citing Liu et al. 2023. It recommends reading page by page and then joining pieces that cross pages. Source: https://anyformat.ai/blog/ocr-scanned-pdf-poor-quality (read 2026-10-16). This is a vendor's claim. The output-length limit it describes matches the API caps above. The Liu citation was not re-read in this session.

## Inferences

- V1 is the ordered steps of the background job the upload route starts. The route session already fixed the file kind and the caller. Evidence: the decision answer and the aligned route session.
- The person has no pipeline constraint of their own. The route constraints still apply: PDFs only, frontend only. Evidence: "I don't know" and the route session.
- The person replaced the per-part belief during alignment. V1 is a simpler pipeline of multimodal model calls that process the document visually, instead of processing each part separately. Evidence: their restatement.
- Those calls still have to produce extracted text. The belief is wrong when that text is not accurate. Evidence: the falsifier, which they have not replaced.
- The pipeline is independent of the agent. It builds the RAG. The agent consumes that RAG afterward. Evidence: the person's correction, in their words, "but is it independent from the agent, this is a processing pipeline for the rag that then the agent will consume".
- The agent's `GeminiClient` is not this pipeline. It sends text and tool blocks and rejects other content blocks. Evidence: `model.py`. That fact supports the separation. It does not choose the client the pipeline uses.
- "Ready" on the read route is the job having finished. The person has not said what finished work the route returns besides a status. The falsifier implies the finished work includes extracted text. Evidence: the route session's status words and the falsifier.
- The person chose that list. Their answer to "Is page, then one visual call per page, then join in order, the V1 you want?" was "yes". The because-clause they accepted is the one in the previous inference: text accuracy under provider vision limits and reply length. A page split does not restore a table or heading that crosses a page. Typical PDF length and the provider remain unstated.

## Shared model

This session decides the V1 steps of the background job. That job is the one the upload route starts for a PDF. The read-by-id route stays not-ready until the job finishes, then the frontend sees ready. Only PDFs, and only the frontend, for now. The person has no further constraint.

A **pipeline step** is one ordered piece of that job. **V1** is the first list of those steps. **Extracted text** is text the job produces from the PDF. A **multimodal model call** is a model request that sees the document visually and returns a result.

The person revised the pipeline, in their words: "Instead of processing each part of the document separatelly, we use a simpler pipeline of multimodal model calls to process it visually." Processing each part separately is out. The calls are wrong when the extracted text is not accurate.

The pipeline is independent of the agent. It is the processing that builds the RAG. The agent consumes that RAG afterward. The agent's `GeminiClient` is a separate caller: it sends text and tool blocks and rejects other blocks. This session does not put the visual calls on that client.

The upload is one complete PDF. The person chose the V1 steps: separate that PDF into pages, run one visual multimodal call per page, and join the extracted text in page order. One call receives one page. Processing the whole PDF in one call is the option they set aside.

A table or a heading that crosses a page boundary is not repaired in V1. What "accurate" means, what the read route returns besides the status, the model provider, a typical PDF length, and how the agent consumes the RAG remain unstated. The person confirmed this paragraph, including those open items, with "yes that matches".

## Gaps

- On 2026-10-17 the person confirmed a later model: split the PDF into pages, recognize diagrams and text blocks with a foundation model, embed each entity, and compare one query vector with those vectors. Paper techniques wait for a later comparison. That reopens per-part recognition, which this session set aside, and it replaces the joined extracted text with entity vectors. This session's shared model was not revised in place. The later record is [2026-10-17-pdf-processing-pipeline.md](2026-10-17-pdf-processing-pipeline.md).
- The person confirmed the chosen steps and the open items with "yes that matches".
- A table or a heading that crosses a page boundary is split and V1 does not stitch it. Typical PDF length and the model provider are unstated.
- How the agent consumes the RAG is outside this session. The person said the agent consumes it and did not say how.
- What "accurate" means is unstated. No sample PDF, no comparison, and no threshold are named.
- What the read-by-id route returns once the status is ready, besides the status, is unstated. The route session stopped at the status.
- How the agent consumes the RAG is outside this session. The person has said that consumption happens after the pipeline and has not said how.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| Restate the shared model. | This session lists the V1 steps of the PDF background job. The believed steps are process the document as images, then recognize the elements. Those steps are wrong when the extracted text is not accurate. The list is not chosen yet. | "Instead of processing each part of the document separatelly, we use a simpler pipeline of multimodal model calls to process it visually" | no |
| Confirm the revised model: visual multimodal calls, independent of the agent, building the RAG the agent later consumes, wrong when the extracted text is not accurate. | That paragraph. | "yes it matches" | yes |
| What does one multimodal call receive? | A whole PDF, one page, or something else. | "the upload would be od one complete pdf, we should decide ifg it is better to have a first step for separating it page per page, or processing it at once" | partial |
| Is V1 page, then one visual call per page, then join in order? | The person's choice. | "yes" | yes |
| Confirm the paragraph that records those steps and the open items. | That paragraph, including the open items. | "yes that matches" | yes |

## Handoff for a human ADR

One record, not written. The person chose the V1 step list and confirmed the shared model, including the open items.

### V1 steps of the PDF background job — revisit this section

Suggested title, for the person to keep or replace: "Define the V1 PDF ingestion steps."

#### Context to carry

The aligned route session chose an upload route and a read-by-id route. The upload starts a background job and returns not-ready. The frontend reads the id until the status is ready. Only PDFs, and only the frontend, for now.

This session decides "the V1 of the pipeline steps." The person first believed the job would process documents as images and then recognize the elements. During alignment they replaced that, in their words: "Instead of processing each part of the document separatelly, we use a simpler pipeline of multimodal model calls to process it visually." The observation that shows the pipeline wrong, in their words: "the extracted text is not accurate."

Nothing in the repository reads a PDF today. `GeminiClient` in `backend/agent/src/agent/model.py` is the agent's caller. It sends text and tool blocks and rejects other content blocks. The person says this pipeline is independent of that agent.

#### Decision drivers

- The route session's "only pdfs for now" and "the front for now."
- The person said "I don't know" when asked for a pipeline constraint, then added one: the pipeline is independent of the agent. It builds the RAG. The agent consumes that RAG afterward.
- The belief fails when the extracted text is not accurate.

#### Considered options

- Set aside by the person during alignment: process each part of the document separately, which was the earlier "recognize the elements" direction.
- Named, not yet a step list: a simpler pipeline of multimodal model calls that process the document visually. The check is still the accuracy of the extracted text.
- Named by the person, not chosen: the upload is one complete PDF, then either a first step separates it page by page, or the pipeline processes it at once. Their words: "the upload would be od one complete pdf, we should decide ifg it is better to have a first step for separating it page per page, or processing it at once".
- Chosen by the person: V1 separates the PDF into pages, sends one visual multimodal call per page, and joins the extracted text in page order. They answered "yes" to that list.

#### Decision outcome to write

Chosen by the person: separate the uploaded PDF into pages, run one visual multimodal call per page, and join the extracted text in page order. Their word was "yes" to that list.

Because the extracted text has to stay accurate, and a single call stops being reliably visual as the PDF lengthens and cannot write the whole document back in one reply. Sources for that because-clause are in Evidence. The person accepted the list that rests on it.

Processing the whole PDF in one call is set aside. Per-part element recognition is set aside. The pipeline stays independent of the agent.

#### Consequences

- The upload still accepts one complete PDF. The job's first step splits it.
- One multimodal call receives one page and returns that page's text.
- The joined text is the extracted text the falsifier checks.
- A table or a heading that crosses a page boundary is not repaired in V1.
- The read route can become ready when every page has returned and the text is joined. What else that response carries is still unstated.
- The agent does not run these calls. It consumes the RAG later, and how is still unstated.
- The model provider and a typical PDF length are unstated. A one-page PDF still follows the same three steps.

#### Confirmation

- A multi-page PDF produces one piece of text per page, joined in page order.
- A call receives one page.
- The job does not send the whole PDF to one call.

#### More Information

> probably the bbest option is to process documents as images, then recognizing the elements

> Instead of processing each part of the document separatelly, we use a simpler pipeline of multimodal model calls to process it visually

> the extracted text is not accurate

> but is it independent from the agent, this is a processing pipeline for the rag that then the agent will consume

> the upload would be od one complete pdf, we should decide ifg it is better to have a first step for separating it page per page, or processing it at once

#### Left open for the person

- What "accurate" means.
- What the read route returns when the status is ready, besides the status.
- Whether a later version stitches tables and headings that cross a page.
- How the agent consumes the RAG.
- The model provider, and a typical PDF length.
