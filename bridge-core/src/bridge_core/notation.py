"""標準記法與 PBN 轉換。

整個專案內部一律使用以下記法:
    花色  C D H S,無王為 N
    牌張  兩字元,花色在前,十寫作 T。例 SA HT D9 C2
    叫品  1C 3N 7S / P / X / XX
    座位  N E S W
    局況  none / NS / EW / both

PBN 是橋牌界交換牌局的標準格式,比賽匯入牌局與 BEN 引擎都使用它。
"""

SUITS = ("C", "D", "H", "S")
STRAINS = ("C", "D", "H", "S", "N")
RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A")
SEATS = ("N", "E", "S", "W")
VULNERABILITIES = ("none", "NS", "EW", "both")

PASS = "P"
DOUBLE = "X"
REDOUBLE = "XX"

# 所有花色叫品,由低到高
CONTRACT_BIDS = tuple(
    f"{level}{strain}" for level in range(1, 8) for strain in STRAINS
)
ALL_CALLS = (PASS, DOUBLE, REDOUBLE) + CONTRACT_BIDS

FULL_DECK = tuple(s + r for s in SUITS for r in RANKS)

_BID_RANK = {bid: i for i, bid in enumerate(CONTRACT_BIDS)}
_CARDS = frozenset(FULL_DECK)


# ---------------------------------------------------------------------------
# 叫品
# ---------------------------------------------------------------------------

def is_contract_bid(call):
    return call in _BID_RANK


def is_call(call):
    return call in ALL_CALLS


def bid_rank(bid):
    """花色叫品的高低次序,數字越大越高。"""
    return _BID_RANK[bid]


# ---------------------------------------------------------------------------
# 牌張
# ---------------------------------------------------------------------------

def is_card(card):
    return card in _CARDS


def card_suit(card):
    return card[0]


def card_rank(card):
    return card[1]


def rank_value(card):
    """牌張大小,2 最小為 0,A 最大為 12。"""
    return RANKS.index(card[1])


def sort_hand(cards):
    """依黑桃、紅心、方塊、梅花,各花色由大到小排序。顯示用。"""
    order = {"S": 0, "H": 1, "D": 2, "C": 3}
    return sorted(cards, key=lambda c: (order[card_suit(c)], -rank_value(c)))


# ---------------------------------------------------------------------------
# 座位
# ---------------------------------------------------------------------------

def partner(seat):
    return SEATS[(SEATS.index(seat) + 2) % 4]


def next_seat(seat):
    return SEATS[(SEATS.index(seat) + 1) % 4]


def same_side(a, b):
    return a == b or partner(a) == b


def side_of(seat):
    return "NS" if seat in ("N", "S") else "EW"


def is_vulnerable(seat, vulnerability):
    return vulnerability == "both" or vulnerability == side_of(seat)


# ---------------------------------------------------------------------------
# PBN
#
# 手牌:黑桃到梅花,點號分隔,例 AK97543.K.T3.AK7
# 整副牌:"N:手牌 手牌 手牌 手牌",從指定座位開始順時針
# ---------------------------------------------------------------------------

_PBN_SUIT_ORDER = ("S", "H", "D", "C")


def hand_to_pbn(cards):
    """["SA","S7","HQ",...] -> "A7.Q.." """
    by_suit = {s: [] for s in _PBN_SUIT_ORDER}
    for c in cards:
        by_suit[card_suit(c)].append(card_rank(c))

    parts = []
    for s in _PBN_SUIT_ORDER:
        ranks = sorted(by_suit[s], key=RANKS.index, reverse=True)
        parts.append("".join(ranks))
    return ".".join(parts)


def pbn_to_hand(pbn):
    """"AK97543.K.T3.AK7" -> ["SA","SK",...]。底線分隔也接受,缺的花色用 - 或空字串。"""
    parts = pbn.strip().replace("_", ".").split(".")
    if len(parts) != 4:
        raise ValueError(f"bad PBN hand: {pbn!r}")

    cards = []
    for suit, ranks in zip(_PBN_SUIT_ORDER, parts):
        if ranks == "-":
            continue
        for r in ranks.upper():
            if r not in RANKS:
                raise ValueError(f"bad rank {r!r} in PBN hand {pbn!r}")
            cards.append(f"{suit}{r}")
    return cards


def deal_to_pbn(hands_by_seat, first_seat="N"):
    """{"N":[...],...} -> "N:hand hand hand hand" """
    start = SEATS.index(first_seat)
    order = [SEATS[(start + i) % 4] for i in range(4)]
    return f"{first_seat}:" + " ".join(hand_to_pbn(hands_by_seat[s]) for s in order)


def pbn_to_deal(pbn):
    """"N:hand hand hand hand" -> {"N":[...],"E":[...],"S":[...],"W":[...]}"""
    first, sep, rest = pbn.strip().partition(":")
    if not sep or first.upper() not in SEATS:
        raise ValueError(f"bad PBN deal: {pbn!r}")

    hands = rest.split()
    if len(hands) != 4:
        raise ValueError(f"PBN deal must have 4 hands: {pbn!r}")

    start = SEATS.index(first.upper())
    return {SEATS[(start + i) % 4]: pbn_to_hand(h) for i, h in enumerate(hands)}
