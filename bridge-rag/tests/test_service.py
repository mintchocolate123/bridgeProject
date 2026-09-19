"""用 bridge-core 產生真實局面測服務,確保格式和平台送來的一樣。"""

import random

import pytest
from bridge_core import Deal
from fastapi.testclient import TestClient

import versions
from rag_service import create_app


def requests_from_real_deal():
    """打一副牌,收集叫牌與出牌各一個真實的 request。"""
    deal = Deal.from_board(1, rng=random.Random(3))
    bid_req = play_req = None
    script = iter(["1N", "P", "P", "P"])
    while not deal.finished:
        turn = deal.to_act()
        req = deal.request_for(turn.actor)
        if turn.phase == "bid":
            bid_req = bid_req or req
            deal.apply(turn.actor, next(script))
        else:
            if deal.dummy_revealed and turn.seat == deal.dummy:
                play_req = req                   # 莊家替明手出牌,最複雜的情況
                break
            deal.apply(turn.actor, req["legal_cards"][0])
    return bid_req, play_req


@pytest.fixture
def client():
    with TestClient(create_app("v0")) as c:
        yield c


def test_health_reports_version(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["version"] == "v0"


def test_bid_and_play_with_platform_requests(client):
    bid_req, play_req = requests_from_real_deal()
    r = client.post("/decide/bid", json=bid_req)
    assert r.status_code == 200, r.text
    assert r.json()["bid"] in bid_req["legal_bids"] and r.json()["version"] == "v0"

    assert play_req["playing_for"] != play_req["me"]
    r = client.post("/decide/play", json=play_req)
    assert r.status_code == 200, r.text
    assert r.json()["card"] in play_req["legal_cards"]


def test_illegal_answer_is_rejected(client, monkeypatch):
    bid_req, _ = requests_from_real_deal()
    monkeypatch.setattr(versions.load("v0"), "choose_bid", lambda req: ("8S", "", []))
    r = client.post("/decide/bid", json=bid_req)
    assert r.status_code == 422 and "illegal" in r.text


def test_unknown_version_fails_at_startup():
    with pytest.raises(ValueError, match="unknown RAG version"):
        create_app("v999")


def test_every_version_is_loadable():
    for name in versions.available():
        module = versions.load(name)
        assert module.DESCRIPTION
