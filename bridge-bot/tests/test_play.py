"""play.py 的決策保護:不需要平台,用假的 agent 測。"""

import time

from play import decide

BID_REQ = {"legal_bids": ["P", "1C", "1D", "X"], "hand": [], "auction": [], "me": "N"}
PLAY_REQ = {"legal_cards": ["S2", "S9"], "current_trick": {"cards": []}}


class Fake:
    name = "fake"

    def __init__(self, bid=None, card=None, sleep=0, error=None):
        self.bid, self.card, self.sleep, self.error = bid, card, sleep, error

    def decide_bid(self, request):
        time.sleep(self.sleep)
        if self.error:
            raise self.error
        return {"bid": self.bid}, {"agent": self.name, "fallback_used": False}

    def decide_play(self, request):
        time.sleep(self.sleep)
        if self.error:
            raise self.error
        return {"card": self.card}, {"agent": self.name, "fallback_used": False}


class Broken:
    def decide_bid(self, request):
        raise RuntimeError("fallback down")

    decide_play = decide_bid


def test_good_decision_passes_through():
    action, response, meta = decide(Fake(bid="1D"), Fake(bid="P"), "bid", BID_REQ, budget=5)
    assert action == "1D" and not meta["fallback_used"]


def test_illegal_uses_fallback():
    action, _, meta = decide(Fake(bid="7N"), Fake(bid="P"), "bid", BID_REQ, budget=5)
    assert action == "P" and meta["fallback_used"] and "not legal" in meta["error"]


def test_exception_uses_fallback():
    action, _, meta = decide(Fake(error=ConnectionError("rag down")), Fake(card="S9"),
                             "play", PLAY_REQ, budget=5)
    assert action == "S9" and meta["fallback_used"] and "rag down" in meta["error"]


def test_slow_agent_hits_budget():
    started = time.perf_counter()
    action, _, meta = decide(Fake(bid="1C", sleep=3), Fake(bid="P"), "bid", BID_REQ, budget=0.3)
    assert time.perf_counter() - started < 1.5
    assert action == "P" and "TimeoutError" in meta["error"]


def test_broken_fallback_still_legal():
    action, _, meta = decide(Fake(bid="9Z"), Broken(), "bid", BID_REQ, budget=5)
    assert action == "P" and meta["fallback_used"]
    action, _, _ = decide(Fake(card="HA"), Broken(), "play", PLAY_REQ, budget=5)
    assert action == "S2"
