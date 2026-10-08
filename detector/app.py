"""Redline Watch detector service.

A small local HTTP wrapper around an open-source AI-text classifier.
n8n sends it article texts and gets back an estimate (0-100) per text.

The score is the model's probability that the text is AI-generated. It is an
uncalibrated estimate, not "the percentage of the text written by AI".
"""
import os
import re
import time
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

MODEL_ID = os.environ.get("MODEL_ID", "fakespot-ai/roberta-base-ai-text-detection-v1")
AI_LABEL = os.environ.get("AI_LABEL", "").strip()
MAX_LEN = int(os.environ.get("MAX_LEN", "512"))
MAX_CHUNKS = int(os.environ.get("MAX_CHUNKS", "4"))
BATCH = int(os.environ.get("BATCH", "8"))
MAX_ITEMS = int(os.environ.get("MAX_ITEMS", "300"))
MAX_CHARS = int(os.environ.get("MAX_CHARS", "12000"))

AI_HINTS = {"ai", "fake", "machine", "generated", "llm", "gpt", "synthetic"}
HUMAN_HINTS = {"human", "real", "genuine", "authentic", "original"}

# Used only for the startup sanity check (the AI sample should score higher).
HUMAN_SAMPLE = (
    "We enrolled 212 patients from three clinics in 2019. Honestly the follow-up was messy: "
    "about a fifth moved away, and two sites changed their forms halfway through, so we had to "
    "re-code a lot of the baseline data by hand. Pain scores dropped in both arms, but the "
    "difference between them was small and the confidence interval crossed zero."
)
AI_SAMPLE = (
    "In this comprehensive study, we delve into the intricate and multifaceted landscape of "
    "patient care. Our meticulous analysis underscores the pivotal role of robust screening, "
    "showcasing a plethora of findings that foster a holistic paradigm. Furthermore, these results "
    "serve as a testament to the importance of coordinated care and highlight the crucial need for "
    "continued research in this ever-evolving field."
)


def clean_text(text: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", str(text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _tokens(label: str):
    return {t for t in re.split(r"[^a-z0-9]+", str(label).lower()) if t}


def pick_ai_index(id2label: dict, override: str = ""):
    """Return (index of the 'AI' class, guessed). guessed=True means the labels gave no clue."""
    labels = {int(k): str(v) for k, v in id2label.items()}
    if override:
        for k, v in labels.items():
            if v.lower() == override.lower() or str(k) == override:
                return k, False
        raise ValueError("AI_LABEL=%r does not match any label in %r" % (override, labels))
    ai = [k for k, v in labels.items() if _tokens(v) & AI_HINTS and not _tokens(v) & HUMAN_HINTS]
    if len(ai) == 1:
        return ai[0], False
    human = [k for k, v in labels.items() if _tokens(v) & HUMAN_HINTS]
    if len(labels) == 2 and len(human) == 1:
        return [k for k in labels if k != human[0]][0], False
    return (1 if 1 in labels else max(labels)), True


def average(values):
    return sum(values) / len(values) if values else 0.0


class HFScorer:
    """Real model. Needs torch + transformers (installed in the Docker image)."""

    def __init__(self, model_id=MODEL_ID, ai_label=AI_LABEL, max_len=MAX_LEN,
                 max_chunks=MAX_CHUNKS, batch=BATCH):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.model_id = model_id
        self.max_len = max_len
        self.max_chunks = max_chunks
        self.batch = batch
        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_id).eval()
        self.id2label = {int(k): str(v) for k, v in self.model.config.id2label.items()}
        self.ai_index, self.guessed = pick_ai_index(self.id2label, ai_label)

    def _chunks(self, text):
        enc = self.tok(
            text, truncation=True, max_length=self.max_len, stride=64,
            return_overflowing_tokens=True, add_special_tokens=True,
        )
        ids = list(enc["input_ids"])
        # A tiny trailing chunk is mostly overlap and tells us little.
        if len(ids) > 1 and len(ids[-1]) < 32:
            ids = ids[:-1]
        return ids[: self.max_chunks]

    def score(self, texts):
        torch = self.torch
        all_chunks, owner = [], []
        for n, text in enumerate(texts):
            for c in self._chunks(text):
                all_chunks.append(c)
                owner.append(n)
        probs = [[] for _ in texts]
        with torch.no_grad():
            for i in range(0, len(all_chunks), self.batch):
                part = all_chunks[i:i + self.batch]
                batch = self.tok.pad({"input_ids": part}, return_tensors="pt")
                logits = self.model(**batch).logits
                p = torch.softmax(logits, dim=-1)[:, self.ai_index].tolist()
                for j, v in enumerate(p):
                    probs[owner[i + j]].append(v)
        return [{"score": average(p) * 100.0, "chunks": len(p)} for p in probs]

    def info(self):
        return {
            "model": self.model_id,
            "labels": self.id2label,
            "aiLabel": self.id2label[self.ai_index],
            "aiLabelGuessed": self.guessed,
        }


class Item(BaseModel):
    id: str
    text: str


class ScoreRequest(BaseModel):
    items: List[Item]


def create_app(scorer=None):
    state = {"scorer": scorer, "sanity": None, "error": None}

    @asynccontextmanager
    async def lifespan(_app):
        if state["scorer"] is None:
            try:
                state["scorer"] = HFScorer()
            except Exception as e:  # keep the process up so /health can explain what failed
                state["error"] = "%s: %s" % (type(e).__name__, e)
        if state["scorer"] is not None:
            try:
                h, a = state["scorer"].score([clean_text(HUMAN_SAMPLE), clean_text(AI_SAMPLE)])
                state["sanity"] = {
                    "humanSample": round(h["score"], 1),
                    "aiSample": round(a["score"], 1),
                    "aiHigherThanHuman": a["score"] > h["score"],
                }
            except Exception as e:
                state["error"] = "sanity check failed: %s: %s" % (type(e).__name__, e)
        yield

    app = FastAPI(title="Redline Watch detector", lifespan=lifespan)

    @app.get("/health")
    def health():
        s = state["scorer"]
        if s is None:
            return {"status": "error" if state["error"] else "loading", "error": state["error"]}
        info = s.info() if hasattr(s, "info") else {}
        ok = bool(state["sanity"] and state["sanity"]["aiHigherThanHuman"]) and not info.get("aiLabelGuessed")
        return {"status": "ok" if ok else "check-labels", "sanity": state["sanity"], "error": state["error"], **info}

    @app.post("/score")
    def score(req: ScoreRequest):
        s = state["scorer"]
        if s is None:
            raise HTTPException(status_code=503, detail=state["error"] or "model is still loading")
        if len(req.items) > MAX_ITEMS:
            raise HTTPException(status_code=413, detail="too many items (max %d)" % MAX_ITEMS)
        started = time.time()
        cleaned = [clean_text(i.text)[:MAX_CHARS] for i in req.items]
        results = []
        todo = [n for n, t in enumerate(cleaned) if t]
        scored = s.score([cleaned[n] for n in todo]) if todo else []
        by_index = dict(zip(todo, scored))
        for n, item in enumerate(req.items):
            r = by_index.get(n)
            results.append({
                "id": item.id,
                "score": round(r["score"], 1) if r else None,
                "chunks": r["chunks"] if r else 0,
            })
        return {
            "model": getattr(s, "model_id", "custom"),
            "count": len(results),
            "elapsedMs": int((time.time() - started) * 1000),
            "results": results,
        }

    return app


app = create_app()
