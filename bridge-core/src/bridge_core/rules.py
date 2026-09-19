"""橋牌規則:合法叫品、合法出牌、叫牌結束、合約判定、贏墩。

全部是純函式,輸入資料、輸出結果,不保存任何狀態。Deal 狀態機建立在
這些函式之上,但需要時也可以單獨使用,例如離線分析一串叫牌歷史。

叫牌歷史的格式是 [{"seat": "N", "bid": "1C"}, ...],依時間順序。
一墩牌的格式是 [{"seat": "N", "card": "SA"}, ...],依出牌順序。
"""

from bridge_core.notation import (
    CONTRACT_BIDS,
    DOUBLE,
    PASS,
    REDOUBLE,
    bid_rank,
    card_suit,
    is_contract_bid,
    rank_value,
    same_side,
)


def _last_contract_bid(auction):
    """回傳 (叫品, 座位),沒有花色叫品時回傳 (None, None)。"""
    for entry in reversed(auction):
        if is_contract_bid(entry["bid"]):
            return entry["bid"], entry["seat"]
    return None, None


def _calls_since_last_contract_bid(auction):
    result = []
    for entry in reversed(auction):
        if is_contract_bid(entry["bid"]):
            break
        result.append(entry)
    result.reverse()
    return result


# ---------------------------------------------------------------------------
# 叫牌
# ---------------------------------------------------------------------------

def auction_is_over(auction):
    """叫牌是否結束。

    有人叫過花色後連續三個 pass 即結束;四家都沒有叫花色,則要四個 pass
    才結束(流局)。
    """
    if len(auction) < 3:
        return False
    if [e["bid"] for e in auction[-3:]] != [PASS, PASS, PASS]:
        return False

    if _last_contract_bid(auction)[0] is not None:
        return True
    return len(auction) >= 4


def legal_bids(auction, seat):
    """seat 此刻可以做出的所有叫品。不檢查是否輪到 seat。"""
    calls = [PASS]

    last_bid, last_bidder = _last_contract_bid(auction)

    if last_bid is None:
        calls.extend(CONTRACT_BIDS)
        return calls

    threshold = bid_rank(last_bid)
    calls.extend(b for b in CONTRACT_BIDS if bid_rank(b) > threshold)

    since = _calls_since_last_contract_bid(auction)
    doubled = any(e["bid"] == DOUBLE for e in since)
    redoubled = any(e["bid"] == REDOUBLE for e in since)

    if not doubled and not redoubled:
        # 只能加倍對方的合約
        if not same_side(last_bidder, seat):
            calls.append(DOUBLE)
    elif doubled and not redoubled:
        # 只能再加倍自己這方被加倍的合約
        if same_side(last_bidder, seat):
            calls.append(REDOUBLE)

    return calls


def resolve_contract(auction):
    """由完整的叫牌歷史判定合約。流局回傳 None。

    莊家是成約那一方中,最先叫出這個王牌花色的人,不一定是最後叫的人。
    例如 N 1H、S 4H,莊家是 N。
    """
    final_bid, final_seat = _last_contract_bid(auction)
    if final_bid is None:
        return None

    level, strain = int(final_bid[0]), final_bid[1]

    doubled = "none"
    for entry in _calls_since_last_contract_bid(auction):
        if entry["bid"] == DOUBLE:
            doubled = "doubled"
        elif entry["bid"] == REDOUBLE:
            doubled = "redoubled"

    declarer = next(
        e["seat"] for e in auction
        if is_contract_bid(e["bid"]) and e["bid"][1] == strain
        and same_side(e["seat"], final_seat)
    )

    return {"level": level, "strain": strain,
            "declarer": declarer, "doubled": doubled}


# ---------------------------------------------------------------------------
# 打牌
# ---------------------------------------------------------------------------

def legal_cards(hand, current_trick):
    """這一墩可以打出的牌。有首引花色就必須跟,沒有才能出別的。

    hand           該家尚未打出的牌
    current_trick  本墩已打出的牌,依順序
    """
    if not current_trick:
        return list(hand)

    lead_suit = card_suit(current_trick[0]["card"])
    follow = [c for c in hand if card_suit(c) == lead_suit]
    return follow if follow else list(hand)


def trick_winner(trick, strain):
    """一墩由誰贏得。有人出王牌就是王牌最大者,否則是首引花色最大者。"""
    lead_suit = card_suit(trick[0]["card"])
    candidates = [e for e in trick if card_suit(e["card"]) == strain]
    if strain == "N" or not candidates:
        candidates = [e for e in trick if card_suit(e["card"]) == lead_suit]

    return max(candidates, key=lambda e: rank_value(e["card"]))["seat"]
