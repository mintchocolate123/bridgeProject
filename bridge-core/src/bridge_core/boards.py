"""發牌與牌號。

複式橋牌每副牌有編號,發牌者與局況由編號決定,16 副一個循環。比賽時
兩桌打同一副牌,這個對應必須一致,所以集中在這裡。
"""

import random

from bridge_core.notation import FULL_DECK, SEATS, is_card

# 標準的 16 副牌局況循環,索引 0 對應第 1 副
_VULNERABILITY_CYCLE = (
    "none", "NS", "EW", "both",
    "NS", "EW", "both", "none",
    "EW", "both", "none", "NS",
    "both", "none", "NS", "EW",
)


def board_dealer(board_number):
    """第 n 副牌的發牌者。1 號 N、2 號 E,依此類推。"""
    if board_number < 1:
        raise ValueError("board number starts at 1")
    return SEATS[(board_number - 1) % 4]


def board_vulnerability(board_number):
    """第 n 副牌的局況。"""
    if board_number < 1:
        raise ValueError("board number starts at 1")
    return _VULNERABILITY_CYCLE[(board_number - 1) % 16]


def random_hands(rng=None):
    """隨機發一副牌。給 rng 可以重現,例如 random.Random(seed)。"""
    rng = rng or random.Random()
    deck = list(FULL_DECK)
    rng.shuffle(deck)
    return {seat: sorted(deck[i * 13:(i + 1) * 13]) for i, seat in enumerate(SEATS)}


def validate_hands(hands):
    """確認是一副完整合法的牌:四家各 13 張,52 張不重複。有問題就拋 ValueError。"""
    if set(hands) != set(SEATS):
        raise ValueError(f"hands must have exactly the seats {SEATS}")

    seen = set()
    for seat in SEATS:
        cards = hands[seat]
        if len(cards) != 13:
            raise ValueError(f"{seat} has {len(cards)} cards, expected 13")
        for card in cards:
            if not is_card(card):
                raise ValueError(f"{seat} has invalid card {card!r}")
            if card in seen:
                raise ValueError(f"card {card} dealt twice")
            seen.add(card)
