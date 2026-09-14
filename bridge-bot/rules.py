"""合法動作計算。

這一層決定 RAG 能選什麼。RAG 回傳不在清單內的動作一律視為失敗,
因此這裡的正確性直接影響整個系統的穩定度。
"""

from notation import (
    CONTRACT_BIDS,
    DOUBLE,
    PASS,
    REDOUBLE,
    bid_rank,
    card_suit,
    is_contract_bid,
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


def auction_is_over(auction):
    """叫牌是否結束。

    有人成約後連續三個 pass 即結束;開局無人成約時需要四個 pass(流局)。
    """
    if len(auction) < 3:
        return False
    if [e["bid"] for e in auction[-3:]] != [PASS, PASS, PASS]:
        return False

    if _last_contract_bid(auction)[0] is not None:
        return True
    return len(auction) >= 4 and all(e["bid"] == PASS for e in auction[:4])


def legal_bids(auction, me):
    """回傳 me 現在可以做出的所有叫品。"""
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
        if not same_side(last_bidder, me):
            calls.append(DOUBLE)
    elif doubled and not redoubled:
        # 只能再加倍自己這方被加倍的合約
        if same_side(last_bidder, me):
            calls.append(REDOUBLE)

    return calls


def legal_cards(hand, current_trick_cards):
    """回傳這一墩可以打出的牌。

    hand                該家尚未打出的牌
    current_trick_cards 本墩已打出的牌,依順序,格式 [{"seat":..,"card":..}]
    """
    if not current_trick_cards:
        return list(hand)

    lead_suit = card_suit(current_trick_cards[0]["card"])
    follow = [c for c in hand if card_suit(c) == lead_suit]

    return follow if follow else list(hand)


def trick_winner(trick_cards, trump):
    """判斷一墩由誰贏得。

    trick_cards 四張牌,格式同上
    trump       "C"/"D"/"H"/"S"/"N"
    """
    from notation import rank_value

    lead_suit = card_suit(trick_cards[0]["card"])
    candidates = [e for e in trick_cards if card_suit(e["card"]) == trump]
    if trump == "N" or not candidates:
        candidates = [e for e in trick_cards if card_suit(e["card"]) == lead_suit]

    best = max(candidates, key=lambda e: rank_value(e["card"]))
    return best["seat"]
