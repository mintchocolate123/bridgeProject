"""以自建的 RAG 服務作為決策模組。

介面定義見 agent-interface.md。服務是無狀態的,每次請求帶完整局面。

同一支程式可以同時接多個 RAG 服務——不同版本跑在不同 port,指定給
不同座位就能直接對打。name 會寫進決策紀錄,用來區分是哪一版的結果。
"""

import logging
from urllib.parse import urlparse

import requests

from agents.base import Agent, _Timed

log = logging.getLogger(__name__)


class RagAgent(Agent):
    def __init__(self, base_url="http://localhost:8001", timeout=30,
                 label=None, fallback=None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.fallback = fallback          # 服務失效時改用的 agent

        # 在讀到服務回報的版本之前,先用 port 當名稱
        self._label = label
        port = urlparse(self.base_url).port
        self.name = f"rag:{label or port or self.base_url}"

    def decide_bid(self, request):
        return self._decide("/decide/bid", request, "bid", "legal_bids",
                            lambda r: self.fallback.decide_bid(r))

    def decide_play(self, request):
        return self._decide("/decide/play", request, "card", "legal_cards",
                            lambda r: self.fallback.decide_play(r))

    def _decide(self, path, request, key, legal_key, fallback_call):
        error = None

        with _Timed() as t:
            try:
                response = self._post(path, request)
                action = response[key]
                if action not in request[legal_key]:
                    raise ValueError(f"{action!r} not in {legal_key}")

            except Exception as exc:
                if self.fallback is None:
                    raise
                error = str(exc)
                log.warning("%s failed (%s), falling back",
                            self.name, _short(error))
                response, _ = fallback_call(request)

        meta = {"agent": self.name, "latency_ms": t.ms,
                "fallback_used": error is not None}
        if error:
            meta["error"] = error
        return response, meta

    def _post(self, path, payload):
        r = requests.post(f"{self.base_url}{path}", json=payload,
                          timeout=self.timeout)
        if not r.ok:
            raise RuntimeError(f"{path} {r.status_code}: {r.text[:300]}")

        data = r.json()
        if isinstance(data, dict) and "error" in data:
            raise RuntimeError(f"{path}: {data['error']}")
        return data

    def health(self):
        """啟動前確認服務活著,順便取得版本標記。

        服務回報版本時,名稱改成 rag:<版本>,例如 rag:v2。決策紀錄與平台
        上顯示的都是這個名稱,換了 port 也分得出是哪一版。
        """
        try:
            r = requests.get(f"{self.base_url}/health", timeout=5)
            info = r.json() if r.ok else None
        except Exception:
            return None
        if isinstance(info, dict) and info.get("version") and not self._label:
            self.name = f"rag:{info['version']}"
        return info


def _short(message, limit=120):
    """把多行的例外訊息壓成一行,避免 log 被塞爆。"""
    message = " ".join(str(message).split())
    return message if len(message) <= limit else message[:limit] + "..."
