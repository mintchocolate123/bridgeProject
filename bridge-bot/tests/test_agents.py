import random

import pytest
from bridge_core import Deal

from agents import make_agent, parse_spec
from agents.ben import auction_to_ctx, played_to_ben, vul_to_ben
from main import run_deal


@pytest.mark.parametrize("spec", ["rulebased", "passing"])
def test_agents_only_make_legal_moves(spec):
    """在 bridge-core 裁判下打 200 副,任何不合法動作都會被記成錯誤。"""
    agent = make_agent(spec)
    agents = {s: agent for s in "NESW"}
    rng = random.Random(1)
    for n in range(1, 201):
        r = run_deal(Deal.from_board(n, rng=rng), agents)
        assert r["error"] is None, r["error"]
        if spec == "passing":
            assert r["passed_out"]


def test_rulebased_reaches_contracts():
    agent = make_agent("rulebased")
    rng = random.Random(2)
    results = [run_deal(Deal.from_board(n, rng=rng), {s: agent for s in "NESW"}) for n in range(1, 51)]
    played = [r for r in results if r["contract"]]
    assert len(played) > 25
    assert all(0 <= r["tricks"] <= 13 for r in played)


def test_parse_spec():
    assert parse_spec("rag@http://localhost:8002") == ("rag", "http://localhost:8002")
    assert parse_spec("BEN")[0] == "ben"
    with pytest.raises(ValueError):
        parse_spec("gpt")


def test_ben_formats():
    auction = [{"seat": "N", "bid": "P"}, {"seat": "E", "bid": "1S"}, {"seat": "S", "bid": "X"}]
    assert auction_to_ctx(auction) == "P-1S-X"
    assert auction_to_ctx([]) == ""
    assert played_to_ben(["DJ", "DK"]) == "DJDK"
    assert [vul_to_ben(v) for v in ("none", "NS", "EW", "both")] == ["", "NS", "EW", "Both"]


def test_rag_name_comes_from_service_version(monkeypatch):
    from agents.rag import RagAgent

    class Resp:
        ok = True

        def json(self):
            return {"status": "ok", "version": "v2"}

    monkeypatch.setattr("agents.rag.requests.get", lambda *a, **k: Resp())
    agent = RagAgent("http://localhost:8002")
    assert agent.name == "rag:8002"
    agent.health()
    assert agent.name == "rag:v2"
    assert RagAgent("http://localhost:8002", label="mine").name == "rag:mine"
