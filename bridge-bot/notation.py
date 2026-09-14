"""標準橋牌記法,以及與 Brydz 線上格式的轉換。

標準記法(本專案內部一律使用):
    花色  C D H S N
    牌張  兩字元,花色在前,十寫作 T。例 SA HT D9 C2
    叫品  1C 3N 7S / P / X / XX
    座位  N E S W
"""

SUITS = ("C", "D", "H", "S")
STRAINS = ("C", "D", "H", "S", "N")
RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A")
SEATS = ("N", "E", "S", "W")

PASS = "P"
DOUBLE = "X"
REDOUBLE = "XX"

# 所有花色叫品,由低到高
CONTRACT_BIDS = tuple(
    f"{level}{strain}" for level in range(1, 8) for strain in STRAINS
)

_BID_RANK = {bid: i for i, bid in enumerate(CONTRACT_BIDS)}


def is_contract_bid(call):
    return call in _BID_RANK


def bid_rank(bid):
    """花色叫品的高低次序,數字越大越高。"""
    return _BID_RANK[bid]


def card_suit(card):
    return card[0]


def card_rank(card):
    return card[1]


def rank_value(card):
    """牌張大小,2 最小為 0,A 最大為 12。"""
    return RANKS.index(card[1])


def partner(seat):
    return SEATS[(SEATS.index(seat) + 2) % 4]


def next_seat(seat):
    return SEATS[(SEATS.index(seat) + 1) % 4]


def same_side(a, b):
    return a == b or partner(a) == b


# ---------------------------------------------------------------------------
# Brydz 線上格式轉換
#
# 以下對應關係已從 client/src/utils.tsx 確認。
# ---------------------------------------------------------------------------

_BRYDZ_TRUMP = {
    "clubs": "C",
    "diams": "D",
    "hearts": "H",
    "spades": "S",
    "no-trump": "N",
}

_TRUMP_TO_BRYDZ = {v: k for k, v in _BRYDZ_TRUMP.items()}

# utils.tsx: seats = {0:"South", 1:"West", 2:"North", 3:"East"}
_SEAT_BY_INDEX = ("S", "W", "N", "E")

# Brydz 的花色字串同時用於牌張的 suit 欄位
_BRYDZ_SUIT_TO_LETTER = {k: v for k, v in _BRYDZ_TRUMP.items() if v != "N"}
_LETTER_TO_BRYDZ_SUIT = {v: k for k, v in _BRYDZ_SUIT_TO_LETTER.items()}


def seat_from_index(index):
    return _SEAT_BY_INDEX[index]


def index_from_seat(seat):
    return _SEAT_BY_INDEX.index(seat)


def bid_from_brydz(payload):
    """{"value":"1","trump":"clubs","bidder":0} -> "1C"

    pass / X / XX 的 value 直接是 "pass"/"X"/"XX",trump 為 "none"。
    """
    value = str(payload["value"])

    if value == "pass":
        return PASS
    if value == "X":
        return DOUBLE
    if value == "XX":
        return REDOUBLE

    strain = _BRYDZ_TRUMP.get(payload["trump"])
    if strain is None:
        raise ValueError(f"unknown trump string: {payload['trump']!r}")
    return f"{value}{strain}"


def bid_to_brydz(call, seat):
    """"1C" -> {"value":"1","trump":"clubs","doubles":"","bidder":0}

    doubles 欄位存在於 client 的 Bid 介面但不在 BiddingOptions 產生的
    選項裡,這裡一併帶上,server 若忽略也無影響。
    """
    bidder = index_from_seat(seat)

    if call in (PASS, DOUBLE, REDOUBLE):
        value = "pass" if call == PASS else call
        doubles = "" if call == PASS else call
        return {"value": value, "trump": "none",
                "doubles": doubles, "bidder": bidder}

    level, strain = call[0], call[1]
    return {"value": level, "trump": _TRUMP_TO_BRYDZ[strain],
            "doubles": "", "bidder": bidder}


# server-utils.js 的牌組:rank 為小寫 'a' 'k' 'q' 'j',十為 '10'。
# 送出時必須維持小寫,否則 server 比對不到該張牌、不會從手牌移除。
_BRYDZ_SYMBOLS = {"spades": "\u2660", "hearts": "\u2665",
                  "clubs": "\u2663", "diams": "\u2666"}

PLACEHOLDER = None   # hideCards 會把看不見的牌換成 rank/suit 皆為 'none'


def card_from_brydz(payload):
    """{"rank":"a","suit":"spades","symbol":"..."} -> "SA"

    遮蔽過的 placeholder({"rank":"none","suit":"none"})回傳 None。
    """
    if payload["suit"] == "none" or payload["rank"] == "none":
        return PLACEHOLDER

    rank = str(payload["rank"]).upper()
    if rank == "10":
        rank = "T"
    suit = _BRYDZ_SUIT_TO_LETTER[payload["suit"]]
    return f"{suit}{rank}"


def card_to_brydz(card):
    """"SA" -> {"rank":"a","suit":"spades","symbol":"..."}"""
    rank = card_rank(card).lower()
    if rank == "t":
        rank = "10"
    suit = _LETTER_TO_BRYDZ_SUIT[card_suit(card)]
    return {"rank": rank, "suit": suit, "symbol": _BRYDZ_SYMBOLS[suit]}


def hands_from_brydz(payload):
    """[{"cards":[...],"player":0}, ...] -> {"S":[...],"W":[...],...}

    placeholder 會被濾掉,所以遮蔽過的手牌只會剩下看得見的牌。
    """
    result = {}
    for entry in payload:
        seat = seat_from_index(entry["player"])
        cards = [card_from_brydz(c) for c in entry["cards"]]
        result[seat] = [c for c in cards if c is not None]
    return result


# ---------------------------------------------------------------------------
# PBN / BEN API 格式
#
# BEN 的手牌是 PBN 點號分隔,黑桃到梅花:AK97543.K.T3.AK7
# 牌張是花色字母加點數,十用 T —— 與本檔的標準記法相同,不需轉換。
# 叫牌歷史用破折號分隔:P-1S-P-3N,加倍 X,無王寫 N。
# ---------------------------------------------------------------------------

_PBN_SUIT_ORDER = ("S", "H", "D", "C")


def hand_to_pbn(cards):
    """["SA","S7","HQ",...] -> "A7.Q...." """
    by_suit = {s: [] for s in _PBN_SUIT_ORDER}
    for c in cards:
        by_suit[card_suit(c)].append(card_rank(c))

    parts = []
    for s in _PBN_SUIT_ORDER:
        ranks = sorted(by_suit[s], key=lambda r: RANKS.index(r), reverse=True)
        parts.append("".join(ranks))
    return ".".join(parts)


def pbn_to_hand(pbn):
    """"AK97543.K.T3.AK7" -> ["SA","SK",...]。底線分隔也接受。"""
    parts = pbn.replace("_", ".").split(".")
    if len(parts) != 4:
        raise ValueError(f"bad PBN hand: {pbn!r}")

    cards = []
    for suit, ranks in zip(_PBN_SUIT_ORDER, parts):
        for r in ranks.upper():
            cards.append(f"{suit}{r}")
    return cards


def deal_to_pbn(hands_by_seat, first_seat="N"):
    """{"N":[...],...} -> "N:hand hand hand hand",順序由 first_seat 順時針。"""
    start = SEATS.index(first_seat)
    order = [SEATS[(start + i) % 4] for i in range(4)]
    return f"{first_seat}:" + " ".join(hand_to_pbn(hands_by_seat[s]) for s in order)


def auction_to_ctx(auction):
    """[{"seat":..,"bid":"1S"},...] -> "P-1S-P-3N" """
    return "-".join(e["bid"] for e in auction)


def played_to_ben(cards):
    """依時間順序的出牌 ["DJ","DK"] -> "DJDK" """
    return "".join(cards)


def vul_to_ben(vulnerability):
    """"none"/"NS"/"EW"/"both" -> BEN 的 vul 參數"""
    return {"none": "", "NS": "NS", "EW": "EW", "both": "Both"}[vulnerability]
