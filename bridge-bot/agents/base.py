"""決策模組的抽象介面。

decide_bid / decide_play 都回傳 (response, meta):
  response 依照 agent-interface.md 的回應格式,至少含 bid 或 card
  meta     供記錄用,例如 {"agent": "...", "latency_ms": 12, "fallback_used": False}

實作必須保證回傳的動作在請求的 legal_bids / legal_cards 之內。
"""

import time


class Agent:
    name = "base"

    def decide_bid(self, request):
        raise NotImplementedError

    def decide_play(self, request):
        raise NotImplementedError


class _Timed:
    """量測耗時的小工具,供各實作共用。"""

    def __enter__(self):
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.ms = int((time.perf_counter() - self._t0) * 1000)
        return False
