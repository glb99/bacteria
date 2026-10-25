---
date: 2026-10-24
status: aligned
question: "Where are the document page images stored?"
adr: ""
---

# Where are the document page images stored?

## Why this session

Locate the persisted images rendered from uploaded PDF pages.

## Starting model

The person clarified that “data/document” means “the folder in which the images are stored.” They expected to have that folder both in the container and in the local project, and said easy access matters during development.

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | “having that folder in both the container and in the local projet” |
| Which decision would this understanding change? | No change requested now; they asked for an explanation. |
| Which constraint will you not trade away? | “easy for now the development phas” |
| What observation would show that belief is wrong? | Not provided. |

## Evidence

- Before implementation, `docker-compose.yml` set `DOCUMENTS_DIR=/data/documents` for the backend and mounted the named Docker volume `documents` at `/data/documents`.
- `backend/app/src/app/core/config.py` defaults `DOCUMENTS_DIR` to `documents` when not overridden.
- `backend/app/src/app/api/services/document_service.py` stores page images under `DOCUMENTS_DIR/<document-id>/<page-index>.png`.
- Before implementation, the running Compose project had the volume `bacteria_documents`. `docker volume inspect` reported its Docker Engine mountpoint as `/var/lib/docker/volumes/bacteria_documents/_data`.
- Before implementation, a read-only listing inside the backend container found 7 PDFs, 30 PNG page images, and 2 document subfolders under `/data/documents`. Some uploaded PDFs have no page-image folder.
- In the repository working tree, neither `.\documents` nor `.\backend\app\documents` exists. The root listing also contains no `documents` directory.
- `.gitignore` currently has no rule to ignore a future root-level `documents` folder.
- The person confirmed that the shared model is accurate, wants local document files kept out of Git, and chose “Just explain; no change yet.”
- After asking how to implement the local folder, the person explicitly requested implementation (“do it”).
- The backend was stopped and all current volume contents were copied into the previously absent root `.\documents` folder. The copy contains 7 PDFs and 30 PNG page images, matching the earlier listing inside the running backend.
- `docker-compose.yml` now bind-mounts `./documents` at `/data/documents`; `.gitignore` excludes `/documents/`. The old `bacteria_documents` named volume has not been removed.
- `docker compose config --quiet` passed. After recreating the backend, its health endpoint returned HTTP 200 and the container saw all 7 PDFs and 30 PNGs through `/data/documents`. `git check-ignore` confirmed the local document images are ignored.

## Inferences

- With the Compose backend, rendered page images are written inside the `documents` named volume at `/data/documents/<document-id>/<page-index>.png`. The host-side physical volume location depends on the Docker engine and volume configuration.
- The current volume contains persisted uploads and rendered page images, so this is not just an empty configured path.
- A project-local bind mount can replace the backend's `documents: /data/documents` mount with `./documents:/data/documents`, while leaving `DOCUMENTS_DIR` unchanged. The top-level `documents:` volume declaration would then be unused and removable.
- Switching the mount without first copying the volume contents would make the backend use the project folder instead of the existing volume; the old named volume would remain but its files would not be visible at `/data/documents`.
- The requested implementation uses the bind mount and preserves the existing files by copying them first. The old named volume is intentionally retained as a rollback copy.

## Shared model

The backend stores page images at `/data/documents/<document-id>/<page-index>.png`. Compose now maps that container path to the root project folder `.\documents`, which is excluded from Git. Existing uploads and rendered images were copied from the named volume before the mount change. The old named volume remains available as a rollback copy.

## Gaps

- The person did not provide a specific falsifying observation.
- The old named volume still contains a duplicate copy and is intentionally not removed.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| Is the shared model accurate? | A named volume persists locally but is managed by Docker rather than appearing in the project; a bind mount would make a project-local folder. | “Yes” | Yes |
| Should the files be easy to browse during development? | Yes; that is the stated constraint. | “easy for now the development phas” | Yes |
| Should Compose be changed now? | The person decides whether to switch to a project-local bind mount or keep Docker-managed storage. | First: “Just explain; no change yet.” Later: “do it” | Yes |

## Handoff for a human ADR

No ADR is named. The person expected the documents folder both in the container and in the local project. Their driver is easy file access during development, and they want local document files excluded from Git. Considered options: keep the named Docker volume, or use a project-local bind mount. The person chose the bind mount (“do it”) because the local project folder makes development files easy to access. Compose now maps `./documents:/data/documents`, keeps `DOCUMENTS_DIR` unchanged, removes the unused named-volume declaration, and `.gitignore` excludes `/documents/`. Before switching, the existing volume contents (7 PDFs and 30 PNGs) were copied to `.\documents`. Compose validation passed, the backend health check returned HTTP 200, and the container sees all 7 PDFs and 30 PNGs from the bind mount. The old `bacteria_documents` volume remains intact as a rollback copy.
