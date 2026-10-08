"""Tests for the service logic. They use a fake scorer, so no model download is needed.
Run:  pip install fastapi httpx && python -m pytest detector/test_app.py   (or: python detector/test_app.py)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from fastapi.testclient import TestClient  # noqa: E402

import app as svc  # noqa: E402


class FakeScorer:
    model_id = "fake"

    def info(self):
        return {"model": "fake", "labels": {0: "human", 1: "ai"}, "aiLabel": "ai", "aiLabelGuessed": False}

    def score(self, texts):
        # more "delve"/"tapestry" => higher score; deterministic
        out = []
        for t in texts:
            hits = sum(t.lower().count(w) for w in ("delve", "tapestry", "intricate", "multifaceted"))
            out.append({"score": min(99.0, 10.0 + 30.0 * hits), "chunks": 1})
        return out


def test_pick_ai_index():
    assert svc.pick_ai_index({0: "Human", 1: "AI"}) == (1, False)
    assert svc.pick_ai_index({0: "AI", 1: "Human"}) == (0, False)
    assert svc.pick_ai_index({0: "real", 1: "fake"}) == (1, False)
    assert svc.pick_ai_index({0: "LABEL_0", 1: "LABEL_1"}) == (1, True)       # no clue: guessed
    assert svc.pick_ai_index({0: "human", 1: "machine-generated"}) == (1, False)
    assert svc.pick_ai_index({0: "LABEL_0", 1: "LABEL_1"}, "0") == (0, False)  # override by index
    assert svc.pick_ai_index({0: "x", 1: "y"}, "Y") == (1, False)               # override by name
    try:
        svc.pick_ai_index({0: "x", 1: "y"}, "nope")
        assert False
    except ValueError:
        pass


def test_clean_text():
    assert svc.clean_text("a \n\n b\t\tc\x00d") == "a b c d"
    assert svc.clean_text(None) == ""


def test_score_endpoint():
    with TestClient(svc.create_app(FakeScorer())) as c:
        h = c.get("/health").json()
        assert h["status"] == "ok" and h["sanity"]["aiHigherThanHuman"] is True
        r = c.post("/score", json={"items": [
            {"id": "a", "text": "Plain clinical text about patients and outcomes."},
            {"id": "b", "text": "We delve into the intricate tapestry of care."},
            {"id": "c", "text": "   "},
        ]})
        assert r.status_code == 200
        res = {x["id"]: x for x in r.json()["results"]}
        assert res["a"]["score"] == 10.0
        assert res["b"]["score"] > res["a"]["score"]
        assert res["c"]["score"] is None and res["c"]["chunks"] == 0   # empty text: no score
        assert [x["id"] for x in r.json()["results"]] == ["a", "b", "c"]  # order kept


def test_empty_and_too_many():
    with TestClient(svc.create_app(FakeScorer())) as c:
        assert c.post("/score", json={"items": []}).json()["results"] == []
        big = {"items": [{"id": str(i), "text": "x"} for i in range(svc.MAX_ITEMS + 1)]}
        assert c.post("/score", json=big).status_code == 413
        assert c.post("/score", json={"nope": 1}).status_code == 422


def test_model_failed_to_load():
    class Broken:
        def __init__(self):
            raise RuntimeError("no network")

    orig = svc.HFScorer
    svc.HFScorer = Broken
    try:
        with TestClient(svc.create_app(None)) as c:
            assert c.get("/health").json()["status"] == "error"
            assert c.post("/score", json={"items": [{"id": "a", "text": "hi"}]}).status_code == 503
    finally:
        svc.HFScorer = orig


def test_guessed_labels_flagged():
    class Guessy(FakeScorer):
        def info(self):
            return {"model": "g", "labels": {0: "LABEL_0", 1: "LABEL_1"}, "aiLabel": "LABEL_1", "aiLabelGuessed": True}

    with TestClient(svc.create_app(Guessy())) as c:
        assert c.get("/health").json()["status"] == "check-labels"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
