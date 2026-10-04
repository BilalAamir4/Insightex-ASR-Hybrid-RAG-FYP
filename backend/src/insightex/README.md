# insightex (package root)

Backend package for Insightex, a timestamp-grounded knowledge base for code-switched (Urdu + English) lecture videos.
Each sub-package is a pipeline stage or service layer. Stages that use a GPU model run as separate processes
(never two CUDA models at once; see `docs/MODELS.md` and `CLAUDE.md`).

Status: skeleton only.
