# incoming/

**The upload path (custom function, see AGENTS.md §4).**

Drop research files here:

- `.md` / `.txt` → read directly by the `external_research` vendor
- `.pdf` → convert to markdown first (pymupdf for text PDFs; marker-pdf for tables/scans), then leave the `.md` here

Rules:

- **Newest file wins** — the vendor reads the highest-mtime file in this folder (archive/ is never read).
- **Consume-once** — after a run reads it, the file is moved to `incoming/archive/`. Re-read for a later run by moving it back.
- Unsupported files (e.g. `.pdf` not yet converted) are left in place and block reading until converted.
- Hidden files (`.DS_Store` etc.) are ignored.

Processed files land in `incoming/archive/`.