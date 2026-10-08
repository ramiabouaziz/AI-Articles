# Redline Watch

Daily screen of newly published medical literature (PubMed, Zenodo) and health news (The Guardian) for signs of AI-assisted drafting. Results are published as a static dashboard on GitHub Pages.

**These are editorial leads, not findings.** Nothing here proves that a text was written by AI, and nothing here identifies which AI tool was used.

## Files

| File | Purpose |
| --- | --- |
| `redline-watch.html` | The dashboard. Add `?demo` to the address to preview it with sample data. |
| `results.json` | Written daily by the n8n workflow. Schema 2: `lastRun`, `runs` (per-day counts), `items` (flagged or detector-checked articles, kept 90 days). No article text is stored. |
| `vocab.json` | Word lists and thresholds, used by both the workflow and the page's checker. Edit this to tune the screen. |
| `n8n/redline-watch-v2.workflow.json` | The n8n workflow. No keys inside. |

## How an article is flagged

1. **Vocabulary drift.** Counts words reported as over-used in LLM-assisted writing. At least 80 words and at least 2 strong words are needed, so short texts and a single stray word never flag.
2. **AI-text detector (Sapling).** Run on a limited daily sample. Flagged items go first, then a round-robin sample across sources.
3. **Tier.** `strong` = leftover chatbot phrase, or both signals agree. `weak` = one signal. Otherwise `none`.

A detector score is a model's estimate for the text it saw. It is not the percentage of the article written by AI.

## Setup (n8n, self-hosted)

1. Deactivate the old Redline Watch workflow.
2. Import `n8n/redline-watch-v2.workflow.json`.
3. Create credentials: **Sapling** (Custom Auth, JSON `{"body": {"key": "..."}}`), **Guardian** (Query Auth, name `api-key`). GitHub and Gmail credentials can be reused.
4. Edit the queries and detector budget in the `Config` node.
5. Run once manually, check the email reports `0 detector errors`, then activate.

## Known limits

- Thresholds in `vocab.json` are not calibrated against a pre-2022 baseline yet.
- Detectors have false positives on short, formulaic or non-native English text.
