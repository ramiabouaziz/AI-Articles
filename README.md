# Redline Watch

Daily screen of newly published medical literature (PubMed, Zenodo) and health news (The Guardian) for signs of AI-assisted drafting. Results are published as a static dashboard on GitHub Pages.

**These are editorial leads, not findings.** Nothing here proves that a text was written by AI, and nothing here identifies which AI tool was used.

## Files

| File | Purpose |
| --- | --- |
| `redline-watch.html` | The dashboard. Add `?demo` to the address to preview it with sample data. |
| `results.json` | Written daily by the n8n workflow. Schema 2: `lastRun`, `runs` (per-day counts), `items` (flagged articles, kept 90 days). No article text is stored. |
| `vocab.json` | Word lists and thresholds, used by both the workflow and the page's checker. Edit this to tune the screen. |
| `n8n/redline-watch-v2.workflow.json` | The n8n workflow (v2.2). No keys inside until you paste yours in the `Config` node. |
| `detector/` | Optional free AI-text detector that runs in Docker on your own computer. See `detector/README.md`. |

## How an article is flagged

Three signals:

1. **Vocabulary drift.** Counts words reported as over-used in LLM-assisted writing. Needs at least 80 words and at least 2 strong words, so short texts and a single stray word never flag.
2. **Leftover chatbot phrases**, such as "as an AI language model".
3. **Local detector estimate (optional).** A free open-source model in the `detector/` container gives each text a 0-100 estimate. It is experimental and uncalibrated, and it is not a percentage of AI-written text.

Tiers:

- `strong`: a chatbot phrase, or elevated vocabulary drift (3 or more strong words at high density), or moderate vocabulary drift plus a detector estimate of 85 or more.
- `weak`: moderate vocabulary drift (at least 2 strong words).
- Everything else is counted but not listed.

The detector never publishes anything by itself. Its estimates appear only in the daily email (the "Highest detector estimates" table), because a public number next to a named article is a reputational risk if it is a false positive. To show estimates on the site, and to publish detector-only high scores as weak signals, set `publishDetectorScore` to `true` in the `Config` node.

## Setup (n8n, self-hosted)

1. Deactivate the old Redline Watch workflow.
2. Import `n8n/redline-watch-v2.workflow.json`.
3. Open the `Config` node and paste your Guardian API key over `PASTE_YOUR_GUARDIAN_KEY_HERE`. Do not export or commit the workflow after that.
4. Start the detector (see `detector/README.md`) and set `detectorUrl` in `Config`, or leave it empty to run without it.
5. Select your GitHub and Gmail credentials on their nodes if a warning shows.
6. Run it once manually. Check the email arrives and `results.json` gets a new commit. Then activate.

The daily email also lists the five highest vocabulary scores that were not flagged. They are not published; they are there to help you tune the thresholds in `vocab.json`.

## Known limits

- Thresholds in `vocab.json` (including `detectorHigh`) are not calibrated against a pre-2022 baseline yet.
- The detector model's accuracy on biomedical abstracts has not been measured here.
- Vocabulary patterns are weak evidence: formulaic, technical or non-native English writing can trigger false positives, and a clean result does not rule out AI assistance.
