# Sessions

Newest first. Status values are defined in `../README.md`.

| Date | Question | Status | Record | ADR |
| --- | --- | --- | --- | --- |
| 2026-10-26 | Why does the retriever have select and select_with_metadata? | exploring | [2026-10-26-select-and-select-with-metadata.md](2026-10-26-select-and-select-with-metadata.md) | |
| 2026-10-26 | Where does the test for the new page score belong? | exploring | [2026-10-26-test-for-page-score.md](2026-10-26-test-for-page-score.md) | |
| 2026-10-26 | What is the standard retrieval score for papers and architecture articles? | exploring | [2026-10-26-standard-score-for-papers.md](2026-10-26-standard-score-for-papers.md) | |
| 2026-10-26 | What is the standard way to score a page from many entity vectors? | exploring | [2026-10-26-standard-page-score.md](2026-10-26-standard-page-score.md) | |
| 2026-10-26 | Why does the retriever return page 10 instead of the Scaled Dot-Product Attention page? | exploring | [2026-10-26-why-summed-page-score-ranks-page-10.md](2026-10-26-why-summed-page-score-ranks-page-10.md) | |
| 2026-10-26 | Do we have an eval that catches the retrieval error before we change ranking? | exploring | [2026-10-26-eval-catches-retrieval-miss.md](2026-10-26-eval-catches-retrieval-miss.md) | |
| 2026-10-25 | Should the retrieval eval expect page index 3? | exploring | [2026-10-25-retriever-page-index.md](2026-10-25-retriever-page-index.md) | |
| 2026-10-25 | Can we use Logfire as the observability backend instead of the console? | exploring | [2026-10-25-logfire-as-observability-backend.md](2026-10-25-logfire-as-observability-backend.md) | |
| 2026-10-25 | How could we add observability to the entire runtime? | exploring | [2026-10-25-entire-runtime-observability.md](2026-10-25-entire-runtime-observability.md) | |
| 2026-10-24 | How can I verify agent CLI article retrieval works? | aligned | [2026-10-24-verifying-cli-retrieval.md](2026-10-24-verifying-cli-retrieval.md) | |
| 2026-10-24 | Will the agent CLI retrieve pages from an uploaded article? | aligned | [2026-10-24-agent-cli-article-retrieval.md](2026-10-24-agent-cli-article-retrieval.md) | |
| 2026-10-24 | Where are the document page images stored? | aligned | [2026-10-24-image-storage-location.md](2026-10-24-image-storage-location.md) | |
| 2026-10-23 | How do we start observability with OpenTelemetry, from the basics? | aligned | [2026-10-23-opentelemetry-basics.md](2026-10-23-opentelemetry-basics.md) | |
| 2026-10-21 | Where does the page-image path live: a page model, or the document model? | aligned | [2026-10-21-page-image-path.md](2026-10-21-page-image-path.md) | |
| 2026-10-21 | How is EmbeddingPageRetriever initialized? | exploring | [2026-10-21-retriever-initialization.md](2026-10-21-retriever-initialization.md) | |
| 2026-10-20 | Should retrieval live in the ingestion package or in its own package? | exploring | [2026-10-20-retrieval-package.md](2026-10-20-retrieval-package.md) | |
| 2026-10-19 | How does the ingestion function divide one PDF into pages? | exploring | [2026-10-19-pdf-page-split.md](2026-10-19-pdf-page-split.md) | |
| 2026-10-19 | How could we implement observability for the agent, according to The Agent Stack Part 8? | exploring | [2026-10-19-agent-observability.md](2026-10-19-agent-observability.md) | |
| 2026-10-17 | How should the PDF processing pipeline work? | aligned | [2026-10-17-pdf-processing-pipeline.md](2026-10-17-pdf-processing-pipeline.md) | |
| 2026-10-16 | What does the read-by-id route return when a PDF is ready? | aligned | [2026-10-16-read-route-ready-result.md](2026-10-16-read-route-ready-result.md) | |
| 2026-10-16 | How do we know the PDF ingestion system works? | aligned | [2026-10-16-ingestion-evals.md](2026-10-16-ingestion-evals.md) | |
| 2026-10-16 | How does the background job turn an uploaded PDF into a ready document? | aligned | [2026-10-16-pdf-ingestion-pipeline.md](2026-10-16-pdf-ingestion-pipeline.md) | |
| 2026-10-16 | How should uploaded files become a RAG the agent uses? | aligned | [2026-10-16-ingestion-rag-for-the-agent.md](2026-10-16-ingestion-rag-for-the-agent.md) | |
| 2026-09-28 | Where should a user-scoped database session live? | aligned | [2026-09-28-user-scoped-database-session.md](2026-09-28-user-scoped-database-session.md) | 0006 |
| 2026-09-27 | How should the assistant work in this repository? | exploring | [2026-09-27-assistant-works-by-understanding.md](2026-09-27-assistant-works-by-understanding.md) | |
