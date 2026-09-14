"""以 BEN 的 REST API 作為決策模組。

BEN 是無狀態的:每次請求都要帶完整的牌局資訊,輪次與贏墩由 Table 負責。

注意事項(取自官方的網站整合指南):
  - 明手出牌時要送莊家的座位與手牌,明手的手牌放 dummy 參數,
    否則會得到 "Called as dummy or with wrong dealer / seat"
  - 首引用 /lead,之後才用 /play
  - 容器剛啟動時第一次請求要 5~15 秒,模型是延遲載入的
  - 推論是單執行緒的,不要對同一個容器併發請求
"""

import logging

import requests

from agents.base import Agent, _Timed
from notation import (
    auction_to_ctx,
    hand_to_pbn,
    partner,
    played_to_ben,
    vul_to_ben,
)

log = logging.getLogger(__name__)


class BenAgent(Agent):
    name = "ben"

    def __init__(self, base_url="http://localhost:8085", timeout=180,
                 details=True, tournament=None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.details = details
        self.tournament = tournament

    # -- 叫牌 ---------------------------------------------------------------

    def decide_bid(self, request):
        params = {
            "hand": hand_to_pbn(request["hand"]),
            "seat": request["me"],
            "dealer": request["dealer"],
            "vul": vul_to_ben(request["vulnerability"]),
            "ctx": auction_to_ctx(request["auction"]),
        }
        if self.details:
            params["details"] = "true"
        if self.tournament:
            params["tournament"] = self.tournament

        with _Timed() as t:
            data = self._get("/bid", params)
            call = _normalize_bid(data["bid"])

        response = {
            "schema_version": "0.1",
            "bid": call,
            "explanation": data.get("explanation"),
            "confidence": _top_score(data.get("candidates"), "call"),
            "alternatives": _alternatives(data.get("candidates"), "call",
                                          _normalize_bid),
            "raw": {k: data.get(k) for k in ("who", "quality", "alert",
                                             "hcp", "shape")},
        }
        return response, {"agent": self.name, "latency_ms": t.ms,
                          "fallback_used": False}

    # -- 打牌 ---------------------------------------------------------------

    def decide_play(self, request):
        contract = request["contract"]
        declarer = contract["declarer"]
        dummy_seat = partner(declarer)
        actor = request["playing_for"]

        # 明手的牌由莊家決定:seat 與 hand 送莊家的,明手的放 dummy。
        # 送明手座位會得到 "Called as dummy or with wrong dealer / seat"。
        if actor == dummy_seat:
            seat = declarer
            hand = request["me_hand"]        # 莊家自己的牌
            dummy = request["hand"]          # 這一手要打的明手的牌
        else:
            seat = actor
            hand = request["hand"]
            dummy = request["dummy"]

        played = [e["card"] for trick in request["completed_tricks"]
                  for e in trick["cards"]]
        played += [e["card"] for e in request["current_trick"]["cards"]]

        params = {
            "hand": hand_to_pbn(hand),
            "seat": seat,
            "dealer": request["dealer"],
            "vul": vul_to_ben(request["vulnerability"]),
            "ctx": auction_to_ctx(request["auction"]),
        }
        if self.details:
            params["details"] = "true"

        with _Timed() as t:
            if not played:
                data = self._get("/lead", params)
            else:
                params["dummy"] = hand_to_pbn(dummy or [])
                params["played"] = played_to_ben(played)
                data = self._get("/play", params)

            card = data["card"].upper()

        response = {
            "schema_version": "0.1",
            "card": card,
            "explanation": data.get("who"),
            "confidence": _top_score(data.get("candidates"), "card"),
            "alternatives": _alternatives(data.get("candidates"), "card",
                                          str.upper),
            "raw": {k: data.get(k) for k in ("who", "quality")},
        }
        return response, {"agent": self.name, "latency_ms": t.ms,
                          "fallback_used": False}

    # -- 共用 ---------------------------------------------------------------

    def _get(self, path, params):
        r = requests.get(f"{self.base_url}{path}", params=params,
                         timeout=self.timeout)

        if not r.ok:
            # BEN 的錯誤說明在回應內容裡,不要被 raise_for_status 吞掉
            raise RuntimeError(f"BEN {path} {r.status_code}: {r.text[:400]} "
                               f"(params={params})")

        data = r.json()
        if isinstance(data, dict) and "error" in data:
            raise RuntimeError(f"BEN {path}: {data['error']} (params={params})")
        return data

    def warm_up(self):
        """讓模型先載入,避免第一次決策特別慢。

        用 /bid 而非 /autoplay:後者要叫完打完一整局,動輒 45 秒以上,
        對暖機而言沒有必要。

        注意 BEN 會檢查 dealer、ctx 長度與 seat 三者是否吻合,不吻合會回
        "Dealer x, auction [...], and seat y do not match!"。這裡用發牌者
        自己第一個開叫的情境,ctx 為空。
        """
        self._get("/bid", {
            "hand": "AK97543.K.T3.AK7",
            "seat": "N", "dealer": "N", "vul": "", "ctx": "",
        })


def _normalize_bid(bid):
    """BEN 回傳 PASS/X/XX 或 1S 這類字串,轉成本專案的標準記法。"""
    b = str(bid).strip().upper()
    if b in ("PASS", "P", "--"):
        return "P"
    if b in ("X", "DB", "DBL", "DOUBLE"):
        return "X"
    if b in ("XX", "RD", "REDOUBLE"):
        return "XX"
    return b.replace("NT", "N")


def _top_score(candidates, key):
    if not candidates:
        return None
    return candidates[0].get("insta_score")


def _alternatives(candidates, key, convert):
    if not candidates:
        return []
    out = []
    for c in candidates[1:4]:
        value = c.get(key)
        if value is None:
            continue
        out.append({key: convert(value), "confidence": c.get("insta_score")})
    return out
