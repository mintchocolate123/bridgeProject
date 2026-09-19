import random

import pytest

from bridge_core import Deal, DealOver, IllegalAction, NotYourTurn
from bridge_core.notation import SEATS, card_suit
from bridge_core.score import score_deal

# 每家拿一整個花色,推理起來最清楚:N 黑桃、E 紅心、S 方塊、W 梅花
SUIT_HANDS = {
    "N": [f"S{r}" for r in "23456789TJQKA"],
    "E": [f"H{r}" for r in "23456789TJQKA"],
    "S": [f"D{r}" for r in "23456789TJQKA"],
    "W": [f"C{r}" for r in "23456789TJQKA"],
}


def bid_all(deal, *calls):
    for call in calls:
        deal.apply(deal.to_act().actor, call)


def contract_1s_by_n():
    """N 1S 成約,莊家 N、明手 S、首引 E。"""
    d = Deal(SUIT_HANDS, dealer="N", board_id="t")
    bid_all(d, "1S", "P", "P", "P")
    return d


# -- 建立 -------------------------------------------------------------------

def test_rejects_bad_hands():
    bad = dict(SUIT_HANDS, N=SUIT_HANDS["N"][:12] + ["HA"])
    with pytest.raises(ValueError):
        Deal(bad)
    with pytest.raises(ValueError):
        Deal(dict(SUIT_HANDS, N=SUIT_HANDS["N"][:12]))
    with pytest.raises(ValueError):
        Deal(SUIT_HANDS, dealer="X")


def test_from_board():
    d = Deal.from_board(6, rng=random.Random(1))
    assert d.dealer == "E" and d.vulnerability == "EW" and d.board_id == "board-6"
    assert Deal.from_board(6, rng=random.Random(1)).initial_hands == d.initial_hands


# -- 叫牌 -------------------------------------------------------------------

def test_bidding_turns():
    d = Deal(SUIT_HANDS, dealer="E")
    assert d.to_act().seat == "E" and d.to_act().phase == "bid"
    with pytest.raises(NotYourTurn):
        d.apply("N", "P")
    d.apply("E", "1H")
    assert d.to_act().actor == "S"
    assert d.legal_actions("N") == []
    assert "X" in d.legal_actions("S")


def test_illegal_and_normalized_bids():
    d = Deal(SUIT_HANDS, dealer="N")
    d.apply("N", "2H")
    with pytest.raises(IllegalAction):
        d.apply("E", "1S")            # 叫得比前面低
    with pytest.raises(IllegalAction):
        d.apply("E", "XX")            # 沒有被加倍
    with pytest.raises(IllegalAction):
        d.apply("E", "8S")
    with pytest.raises(IllegalAction):
        d.apply("E", 3)
    d.apply("E", "3nt")               # 寬鬆輸入
    d.apply("S", "dbl")
    with pytest.raises(IllegalAction):
        d.apply("W", "X")             # 3N 是同伴 E 叫的,不能加倍自己人
    d.apply("W", "rdbl")              # 但可以再加倍
    d.apply("N", "pass")
    assert [e["bid"] for e in d.auction] == ["2H", "3N", "X", "XX", "P"]


def test_rejected_action_leaves_state_unchanged():
    d = Deal(SUIT_HANDS, dealer="N")
    d.apply("N", "1C")
    before = d.to_dict()
    for bad in (("N", "P"), ("E", "1C"), ("E", "zz")):
        with pytest.raises((NotYourTurn, IllegalAction)):
            d.apply(*bad)
    assert d.to_dict() == before


def test_pass_out_needs_four_passes():
    d = Deal(SUIT_HANDS, dealer="N")
    bid_all(d, "P", "P", "P")
    assert not d.finished
    events = d.apply("W", "P")
    assert d.finished and d.passed_out and d.to_act() is None
    assert [e["type"] for e in events] == ["bid", "auction_end", "deal_end"]
    assert d.result() == {"contract": None, "passed_out": True, "declarer": None,
                          "tricks": None, "score": 0, "ns_score": 0}
    with pytest.raises(DealOver):
        d.apply("N", "P")


def test_auction_end_event():
    d = Deal(SUIT_HANDS, dealer="N", board_id="b1")
    bid_all(d, "1S", "P", "P")
    events = d.apply("W", "P")
    end = events[-1]
    assert end["type"] == "auction_end" and end["board_id"] == "b1"
    assert end["declarer"] == "N" and end["dummy"] == "S" and end["leader"] == "E"
    assert d.phase == "playing"


# -- 打牌 -------------------------------------------------------------------

def test_dummy_is_played_by_declarer():
    d = contract_1s_by_n()
    assert d.to_act().seat == "E"
    d.apply("E", "H2")                       # 首引
    turn = d.to_act()
    assert turn.seat == "S" and turn.actor == "N"   # 明手的回合,莊家決定
    with pytest.raises(NotYourTurn):
        d.apply("S", "D2")                   # 明手自己不能出
    assert d.legal_actions("S") == []
    assert sorted(d.legal_actions("N")) == sorted(SUIT_HANDS["S"])  # 莊家看到的是明手的牌
    events = d.apply("N", "D2")
    assert events[0]["seat"] == "S" and events[0]["played_by"] == "N"
    assert "D2" not in d.view("all")["hands"]["S"]


def test_dummy_revealed_once_after_lead():
    d = contract_1s_by_n()
    assert not d.dummy_revealed
    events = d.apply("E", "H2")
    revealed = [e for e in events if e["type"] == "dummy_revealed"]
    assert len(revealed) == 1 and revealed[0]["seat"] == "S"
    assert len(revealed[0]["hand"]) == 13
    events = d.apply("N", "D2")
    assert not any(e["type"] == "dummy_revealed" for e in events)


def test_follow_suit_enforced():
    hands = {
        "N": ["SA", "SK", "HA", "HK", "HQ", "HJ", "HT", "H9", "H8", "H7", "H6", "H5", "H4"],
        "E": ["SQ", "SJ", "DA", "DK", "DQ", "DJ", "DT", "D9", "D8", "D7", "D6", "D5", "D4"],
        "S": ["ST", "S9", "CA", "CK", "CQ", "CJ", "CT", "C9", "C8", "C7", "C6", "C5", "C4"],
        "W": ["S8", "S7", "S6", "S5", "S4", "S3", "S2", "H3", "H2", "D3", "D2", "C3", "C2"],
    }
    d = Deal(hands, dealer="N")
    bid_all(d, "1N", "P", "P", "P")          # 莊家 N,首引 E
    d.apply("E", "SQ")
    with pytest.raises(IllegalAction):
        d.apply("N", "CA")                   # 輪到明手 S,有黑桃必須跟
    assert d.legal_actions("N") == ["ST", "S9"]


def test_trick_and_leader():
    d = contract_1s_by_n()
    d.apply("E", "HA")
    d.apply("N", "D2")    # 明手
    d.apply("W", "C2")
    events = d.apply("N", "S2")                # 莊家王吃
    trick = [e for e in events if e["type"] == "trick"][0]
    assert trick["winner"] == "N" and trick["number"] == 1
    assert trick["counts"] == {"NS": 1, "EW": 0}
    assert d.to_act().seat == "N"              # 贏家先出


def test_full_deal_result():
    d = contract_1s_by_n()
    while not d.finished:
        turn = d.to_act()
        d.apply(turn.actor, d.default_action(turn.actor))
    # 黑桃是王,N 手上全是王牌,每一墩都是 N 贏
    r = d.result()
    assert r["tricks"] == 13 and r["declarer"] == "N"
    # 1S 無局超六:基本 30 + 部分分 50 + 超墩 6x30
    assert r["score"] == r["ns_score"] == 30 + 50 + 180
    assert d.trick_counts() == {"NS": 13, "EW": 0}
    assert all(c == 0 for c in d.view()["hand_counts"].values())


def test_default_action():
    d = Deal(SUIT_HANDS, dealer="N")
    assert d.default_action("N") == "P"
    assert d.default_action("E") is None
    d = contract_1s_by_n()
    assert d.default_action("E") == "H2"


# -- 視角 -------------------------------------------------------------------

def test_view_masking():
    d = contract_1s_by_n()
    v = d.view("W")
    assert v["hands"]["W"] is not None
    assert all(v["hands"][s] is None for s in "NES")
    assert v["hand_counts"]["N"] == 13
    assert all(h is None for h in d.view("public")["hands"].values())
    assert all(h is not None for h in d.view("all")["hands"].values())

    d.apply("E", "H2")                         # 首引後明手 S 公開
    v = d.view("W")
    assert v["hands"]["S"] is not None and v["hands"]["N"] is None
    pub = d.view("public")["hands"]
    assert pub["S"] is not None and all(pub[s] is None for s in "NEW")

    with pytest.raises(ValueError):
        d.view("X")


def test_view_after_finish():
    d = Deal(SUIT_HANDS, dealer="N")
    bid_all(d, "P", "P", "P", "P")
    assert d.view("E")["hands"]["N"] is None
    assert d.view("E", reveal_finished=True)["hands"]["N"] is not None


def test_view_turn():
    d = contract_1s_by_n()
    d.apply("E", "H2")
    assert d.view("all")["turn"] == {"seat": "S", "actor": "N", "phase": "play"}


# -- 決策請求 ---------------------------------------------------------------

def test_request_for_bid():
    d = Deal(SUIT_HANDS, dealer="N", board_id="b")
    r = d.request_for("N")
    assert r["me"] == "N" and r["hand"] == d.initial_hands["N"]
    assert r["masked"] is True and "all_hands" not in r
    assert len(r["legal_bids"]) == 36
    assert d.request_for("E") is None
    assert d.request_for("N", reveal_all=True)["all_hands"]["E"] == d.initial_hands["E"]


def test_request_for_play():
    d = contract_1s_by_n()
    r = d.request_for("E")                     # 首引,明手還沒攤開
    assert r["playing_for"] == "E" and r["dummy"] is None
    d.apply("E", "H2")

    r = d.request_for("N")                     # 莊家替明手出
    assert r["me"] == "N" and r["playing_for"] == "S"
    assert r["hand"] == d.view()["hands"]["S"]
    assert r["me_hand"] == d.view()["hands"]["N"]
    assert r["dummy"] is None                  # 打的就是明手,不重複放
    assert r["current_trick"]["cards"] == [{"seat": "E", "card": "H2"}]
    d.apply("N", "D2")

    r = d.request_for("W")                     # 防家看得到明手
    assert r["dummy"] == d.view()["hands"]["S"]
    assert r["legal_cards"] == d.legal_actions("W")


# -- 序列化 -----------------------------------------------------------------

def test_round_trip_mid_deal():
    d = contract_1s_by_n()
    d.apply("E", "H2")
    d.apply("N", "D2")
    d2 = Deal.from_dict(d.to_dict())
    assert d2.view("all") == d.view("all")
    assert d2.to_act() == d.to_act()


def test_copy_is_independent():
    d = contract_1s_by_n()
    c = d.copy()
    c.apply("E", "H2")
    assert d.to_act().seat == "E"


# -- 隨機壓力測試 -----------------------------------------------------------

def play_random(seed):
    rng = random.Random(seed)
    d = Deal.from_board(seed % 16 + 1, rng=rng, board_id=f"r{seed}")
    events = []
    while not d.finished:
        turn = d.to_act()
        legal = d.legal_actions(turn.actor)
        # 叫牌偏向 pass,不然隨機叫會一路叫到 7 階
        if turn.phase == "bid" and rng.random() < 0.7:
            action = "P"
        else:
            action = rng.choice(legal)
        events.extend(d.apply(turn.actor, action))
    return d, events


@pytest.mark.parametrize("seed", range(300))
def test_random_deals_invariants(seed):
    d, events = play_random(seed)
    r = d.result()

    if d.passed_out:
        assert r["score"] == 0
        return

    cards = [e["card"] for e in events if e["type"] == "card"]
    assert len(cards) == 52 and len(set(cards)) == 52
    assert sorted(cards) == sorted(c for h in d.initial_hands.values() for c in h)

    tricks = [e for e in events if e["type"] == "trick"]
    assert len(tricks) == 13

    # 重新走一遍手牌,確認每一家要嘛跟了首引花色,要嘛當時手上沒有這個花色
    hands = {s: set(h) for s, h in d.initial_hands.items()}
    for t in tricks:
        assert {c["seat"] for c in t["cards"]} == set(SEATS)
        lead = card_suit(t["cards"][0]["card"])
        for c in t["cards"][1:]:
            if card_suit(c["card"]) != lead:
                assert not any(card_suit(x) == lead for x in hands[c["seat"]]), (t, c)
        for c in t["cards"]:
            hands[c["seat"]].remove(c["card"])

    assert sum(d.trick_counts().values()) == 13
    assert (r["score"], r["ns_score"]) == score_deal(d.contract, r["tricks"], d.vulnerability)
    assert sum(1 for e in events if e["type"] == "dummy_revealed") == 1
    assert Deal.from_dict(d.to_dict()).view("all") == d.view("all")
