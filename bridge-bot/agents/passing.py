"""最簡單的決策模組,用來驗證連線與流程。

叫牌一律 pass,打牌一律出最小的合法牌。
不做任何判斷,所以任何異常都是上層的問題,不是它的。
"""

from agents.base import Agent, _Timed
from notation import PASS, rank_value


class PassingAgent(Agent):
    name = "passing"

    def decide_bid(self, request):
        with _Timed() as t:
            assert PASS in request["legal_bids"]
            response = {"schema_version": "0.1", "bid": PASS,
                        "explanation": "fixed pass"}
        return response, {"agent": self.name, "latency_ms": t.ms,
                          "fallback_used": False}

    def decide_play(self, request):
        with _Timed() as t:
            if not request["legal_cards"]:
                raise ValueError("no legal cards; deal should already be over")
            card = min(request["legal_cards"], key=rank_value)
            response = {"schema_version": "0.1", "card": card,
                        "explanation": "lowest legal card"}
        return response, {"agent": self.name, "latency_ms": t.ms,
                          "fallback_used": False}
