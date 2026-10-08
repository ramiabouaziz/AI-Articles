# Redline Watch detector (free, runs on your own computer)

A small web service that wraps an open-source AI-text classifier
([`fakespot-ai/roberta-base-ai-text-detection-v1`](https://huggingface.co/fakespot-ai/roberta-base-ai-text-detection-v1), Apache-2.0, about 125M parameters, CPU only).
The n8n workflow sends it the day's article texts and gets back an estimate from 0 to 100 for each one.

**What the number is:** the model's probability that a text is AI-generated. It is not "the percentage of the text written by AI", it is not calibrated, and it can be wrong in both directions (formal, technical or non-native English is often over-scored; lightly edited AI text is often missed). English only.

**Privacy:** after the model is downloaded once from Hugging Face, article texts go only from n8n to this container on your own computer.

## Start it (Windows, Docker Desktop)

1. Open Docker Desktop and wait until it says it is running.
2. In PowerShell:
   ```powershell
   git clone https://github.com/ramiabouaziz/AI-Articles.git
   cd AI-Articles\detector
   docker compose up -d --build
   ```
   The first build downloads PyTorch (a few hundred MB) and the first start downloads the model (about 500 MB). Expect several minutes. Later starts take seconds because the model is kept in a Docker volume.
3. Open http://localhost:8000/health in the browser. You want `"status": "ok"` and `"aiHigherThanHuman": true`.
   - `loading`: wait a minute and refresh.
   - `check-labels`: the service could not be sure which output class means "AI". Look at `labels`, then set `AI_LABEL` in `docker-compose.yml` (for example `AI_LABEL: "ai"`) and run `docker compose up -d`.
   - `error`: the message says why (usually the model download was blocked).
4. Optional manual test:
   ```powershell
   Invoke-RestMethod -Method Post -Uri http://localhost:8000/score -ContentType 'application/json' -Body '{"items":[{"id":"t","text":"Paste a paragraph of at least a few sentences here."}]}'
   ```

## Connect n8n

In the workflow's `Config` node set `detectorUrl`:

| How n8n runs | detectorUrl |
| --- | --- |
| In Docker | `http://host.docker.internal:8000` |
| Directly on Windows (npm / desktop app) | `http://localhost:8000` |

If n8n is in Docker and still cannot connect, change the port line in `docker-compose.yml` to `"8000:8000"` and run `docker compose up -d`.

The computer, Docker Desktop and n8n all need to be running at 07:00. In Docker Desktop settings, turn on "Start Docker Desktop when you sign in". The container restarts with it.

## Notes

- Long texts are split into chunks of up to 512 tokens (first 4 chunks) and the chunk scores are averaged.
- Short texts (under 80 words) are not scored by the workflow.
- The model is not pinned to a fixed revision. Re-check `/health` after rebuilding the image.
- Tests for the service logic (no model needed): `pip install fastapi httpx && python test_app.py`.
