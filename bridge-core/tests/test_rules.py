from bridge_core.notation import (
    CONTRACT_BIDS, DOUBLE, REDOUBLE, hand_to_pbn, next_seat, partner,
    pbn_to_deal, pbn_to_hand, deal_to_pbn, same_side, sort_hand,
)
from bridge_core.rules import (
    auction_is_over, legal_bids, legal_cards, resolve_contract, trick_winner,
)


def A(*pairs):
    return [{"seat": s, "bid": b} for s, b in pairs]


def T(*pairs):
    return [{"seat": s, "card": c} for s, c in pairs]


# -- 記法 -------------------------------------------------------------------

def test_seats():
    assert partner("N") == "S" and partner("E") == "W"
    assert next_seat("W") == "N"
    assert same_side("N", "S") and not same_side("N", "E")


def test_pbn_round_trip():
    hand = ["SA", "SK", "S9", "S7", "S5", "S4", "S3", "HK", "DT", "D3", "CA", "CK", "C7"]
    assert hand_to_pbn(hand) == "AK97543.K.T3.AK7"
    assert sorted(pbn_to_hand("AK97543.K.T3.AK7")) == sorted(hand)
    assert pbn_to_hand("AK97543_K_T3_AK7") == pbn_to_hand("AK97543.K.T3.AK7")
    assert hand_to_pbn([]) == "..."
    assert pbn_to_hand("-.-.-.-") == []


def test_pbn_deal():
    pbn = "N:862.62.AQT52.A96 AQJT9.Q875.97.K7 7543.AT943.8.JT8 K.KJ.KJ643.Q5432"
    deal = pbn_to_deal(pbn)
    assert set(deal) == {"N", "E", "S", "W"}
    assert all(len(h) == 13 for h in deal.values())
    assert deal_to_pbn(deal) == pbn
    assert pbn_to_deal(deal_to_pbn(deal, "E")) == deal


def test_sort_hand():
    assert sort_hand(["C2", "SA", "H9", "S3", "DK"]) == ["SA", "S3", "H9", "DK", "C2"]


# -- 叫牌 -------------------------------------------------------------------

def test_opening_bids():
    lb = legal_bids(A(), "N")
    assert len(lb) == 36
    assert DOUBLE not in lb and REDOUBLE not in lb


def test_double_only_opponents():
    lb = legal_bids(A(("N", "1C")), "E")
    assert DOUBLE in lb and REDOUBLE not in lb
    assert "1D" in lb and "1C" not in lb
    assert len(lb) == 1 + 34 + 1
    assert DOUBLE not in legal_bids(A(("N", "1C")), "S")


def test_redouble():
    assert REDOUBLE in legal_bids(A(("N", "1C"), ("E", "X")), "S")
    lb = legal_bids(A(("N", "1C"), ("E", "X")), "W")
    assert DOUBLE not in lb and REDOUBLE not in lb
    lb = legal_bids(A(("N", "1C"), ("E", "X"), ("S", "XX")), "W")
    assert DOUBLE not in lb and REDOUBLE not in lb


def test_new_bid_clears_double():
    assert DOUBLE in legal_bids(A(("N", "1C"), ("E", "X"), ("S", "XX"), ("W", "2C")), "N")


def test_top_contract():
    lb = legal_bids(A(("N", "7N")), "E")
    assert lb == ["P", "X"]


def test_auction_end():
    assert not auction_is_over(A(("N", "P"), ("E", "P"), ("S", "P")))
    assert auction_is_over(A(("N", "P"), ("E", "P"), ("S", "P"), ("W", "P")))
    assert auction_is_over(A(("N", "1C"), ("E", "P"), ("S", "P"), ("W", "P")))
    assert not auction_is_over(A(("N", "1C"), ("E", "P"), ("S", "P")))
    assert auction_is_over(A(("N", "P"), ("E", "1C"), ("S", "P"), ("W", "P"), ("N", "P")))


def test_resolve_contract():
    assert resolve_contract(A(("N", "P"), ("E", "P"), ("S", "P"), ("W", "P"))) is None

    c = resolve_contract(A(("N", "1H"), ("E", "P"), ("S", "4H"), ("W", "P"), ("N", "P"), ("E", "P")))
    assert c == {"level": 4, "strain": "H", "declarer": "N", "doubled": "none"}

    c = resolve_contract(A(("N", "1S"), ("E", "X"), ("S", "P"), ("W", "P"), ("N", "P")))
    assert c["doubled"] == "doubled"

    c = resolve_contract(A(("N", "1S"), ("E", "X"), ("S", "XX"), ("W", "P"), ("N", "P"), ("E", "P")))
    assert c["doubled"] == "redoubled"

    # 加倍後有人改叫,加倍失效
    c = resolve_contract(A(("N", "1S"), ("E", "X"), ("S", "2S"), ("W", "P"), ("N", "P"), ("E", "P")))
    assert c["doubled"] == "none" and c["declarer"] == "N"

    # 對手先叫過同花色不影響莊家判定
    c = resolve_contract(A(("N", "1H"), ("E", "2H"), ("S", "3H"), ("W", "P"), ("N", "P"), ("E", "P")))
    assert c["declarer"] == "N"


# -- 打牌 -------------------------------------------------------------------

def test_follow_suit():
    hand = ["SA", "S7", "HQ", "D9"]
    assert legal_cards(hand, []) == hand
    assert legal_cards(hand, T(("E", "SK"))) == ["SA", "S7"]
    assert legal_cards(hand, T(("E", "CK"))) == hand


def test_trick_winner():
    t = T(("N", "HA"), ("E", "H2"), ("S", "SK"), ("W", "H5"))
    assert trick_winner(t, "N") == "N"
    assert trick_winner(t, "S") == "S"
    assert trick_winner(t, "H") == "N"
    # 墊牌不管多大都不贏
    t = T(("N", "H2"), ("E", "SA"), ("S", "H3"), ("W", "CA"))
    assert trick_winner(t, "N") == "S"
