from bridge_core import Deal
from bridge_core.notation import is_call

from agents import make_agent
from main import build_agents, run_deal, run_deals


class Illegal:
    name = "illegal"

    def decide_bid(self, request):
        return {"bid": "8S"}, {"agent": self.name}


def test_same_seed_same_boards():
    agents = build_agents("rulebased", "rulebased")
    a = run_deals(agents, 6, seed=9)
    b = run_deals(agents, 6, seed=9)
    assert [r["hands"] for r in a] == [r["hands"] for r in b]
    assert [r["ns_score"] for r in a] == [r["ns_score"] for r in b]
    # 標準 16 副循環:第 1 到 4 副的發牌者是北東南西
    assert [r["dealer"] for r in a[:4]] == ["N", "E", "S", "W"]
    assert [r["vulnerability"] for r in a[:4]] == ["none", "NS", "EW", "both"]


def test_result_replays_with_bridge_core():
    agents = build_agents("rulebased", "rulebased")
    for r in run_deals(agents, 5, seed=3):
        replayed = Deal.from_dict(r)
        assert replayed.finished
        assert replayed.result()["ns_score"] == r["ns_score"]


def test_no_play_stops_after_auction():
    agents = build_agents("rulebased", "rulebased")
    results = run_deals(agents, 20, seed=4, play_out=False)
    contracted = [r for r in results if r["contract"]]
    assert contracted
    for r in contracted:
        assert r["tricks"] is None and r["error"] is None
        assert all(is_call(h["action"]) for h in r["history"])     # 只有叫品,沒有出牌


def test_illegal_move_is_recorded_not_replaced():
    agents = {s: make_agent("rulebased") for s in "NESW"}
    agents["N"] = Illegal()
    r = run_deal(Deal.from_board(1), agents)
    assert r["error"] and "illegal" in r["error"]
    assert r["history"] == []


def test_decisions_are_logged_with_masking():
    seen = []
    agents = build_agents("rulebased", "rulebased")
    run_deal(Deal.from_board(1), agents, on_decision=lambda *a: seen.append(a))
    assert seen and all(req["masked"] and "all_hands" not in req for _, req, _, _ in seen)
    seen.clear()
    run_deal(Deal.from_board(1), agents, on_decision=lambda *a: seen.append(a), reveal_all=True)
    assert all("all_hands" in req for _, req, _, _ in seen)
