# Instructions for coding agents

This repository is a university laboratory submission: a multi-agent artist using
Yandex AI Studio Responses API and Image Generation API.

- Keep the full implementation visible in `Agent_Artist.ipynb`. `agent_artist.py`
  is its CLI counterpart; `scripts/build_notebook.py` synchronizes the notebook.
- Never commit `.env`, credentials, local caches or model weights. Do not include
  the teacher's credential-download URL in the public submission.
- Generated art must come from the recorded model calls. Never invent transcripts,
  execution outputs, scores, evaluation improvements, or participant contributions.
- A VLM review must actually receive the rendered image. Clearly distinguish its
  subjective rubric scores from independent human evaluation.
- Keep all candidate images, prompts and reviews, including rejected candidates.
  Select by the declared scoring rule rather than silently taking the last image.
- The `docs/` directory is a buildless, self-contained GitHub Pages gallery.
- Before handoff, validate notebook execution, linked assets, all four paintings,
  complete dialogues, and absence of secrets in tracked files.
- AI assistance and the initial task must be documented in `ai/` and `REPORT.md`.
