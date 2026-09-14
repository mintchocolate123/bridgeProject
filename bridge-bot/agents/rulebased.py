"""規則式 baseline。

刻意寫得很簡單,目的是產生真實的合約讓打牌階段能被測試,並在之後
作為 RAG 的對照組。它不代表任何正式的叫牌制度,不要拿它當標準答案。

叫牌:
    無人開叫且 12 點以上 -> 開叫最長花色的一階
    同伴已開叫且 6 點以上 -> 在合法範圍內叫最便宜的一階花色
    其餘一律 pass
打牌:
    首引出最長花色的最小牌,其餘情況跟牌出最小,不能跟牌時墊最小
"""

from agents.base import Agent, _Timed
from notation import PASS, SUITS, card_suit, is_contract_bid, rank_value, same_side

HCP = {"A": 4, "K": 3, "Q": 2, "J": 1}


def high_card_points(hand):
    return sum(HCP.get(c[1], 0) for c in hand)


def suit_lengths(hand):
    return {s: sum(1 for c in hand if card_suit(c) == s) for s in SUITS}


class RuleBasedAgent(Agent):
    name = "rulebased"

    def decide_bid(self, request):
        with _Timed() as t:
            call = self._choose_bid(request)
            response = {"schema_version": "0.1", "bid": call,
                        "explanation": f"{high_card_points(request['hand'])} HCP"}
        return response, {"agent": self.name, "latency_ms": t.ms,
                          "fallback_used": False}

    def _choose_bid(self, request):
        hand = request["hand"]
        legal = request["legal_bids"]
        hcp = high_card_points(hand)
        auction = request["auction"]
        me = request["me"]

        opened = any(is_contract_bid(e["bid"]) for e in auction)
        lengths = suit_lengths(hand)
        longest = max(SUITS, key=lambda s: (lengths[s], SUITS.index(s)))

        if not opened:
            if hcp >= 12 and f"1{longest}" in legal:
                return f"1{longest}"
            return PASS

        partner_opened = any(
            is_contract_bid(e["bid"]) and same_side(e["seat"], me) and e["seat"] != me
            for e in auction
        )
        already_bid = any(e["seat"] == me and is_contract_bid(e["bid"])
                          for e in auction)

        if partner_opened and not already_bid and hcp >= 6:
            for s in SUITS:
                if f"1{s}" in legal and lengths[s] >= 4:
                    return f"1{s}"

        return PASS

    def decide_play(self, request):
        with _Timed() as t:
            legal = request["legal_cards"]
            if not legal:
                raise ValueError("no legal cards; deal should already be over")

            leading = not request["current_trick"]["cards"]
            if leading:
                lengths = suit_lengths(legal)
                best = max(SUITS, key=lambda s: (lengths[s], SUITS.index(s)))
                candidates = [c for c in legal if card_suit(c) == best] or legal
            else:
                candidates = legal

            card = min(candidates, key=rank_value)
            response = {"schema_version": "0.1", "card": card,
                        "explanation": "lead longest suit" if leading
                                       else "lowest legal card"}
        return response, {"agent": self.name, "latency_ms": t.ms,
                          "fallback_used": False}
