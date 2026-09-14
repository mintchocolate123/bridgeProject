"""RAG 服務範本。

這是一層薄薄的 HTTP 外殼,把你的 RAG 包成 bot 可以呼叫的介面。
服務必須是無狀態的:每次請求都帶完整局面,不要在這裡維護對局狀態。

啟動:
    pip install fastapi uvicorn
    uvicorn rag_service:app --port 8001

兩個版本同時跑就用不同 port:
    uvicorn rag_service:app --port 8001
    uvicorn rag_service_v2:app --port 8002

然後:
    python main.py --deals 50 --ns rag@http://localhost:8001 \
                              --ew rag@http://localhost:8002
"""

from fastapi import FastAPI
from pydantic import BaseModel

VERSION = "v0.1-skeleton"

app = FastAPI()


# ---------------------------------------------------------------------------
# 請求格式。欄位說明見 agent-interface.md。
# 用 dict 接收,不要求嚴格結構,方便之後加欄位不用改這裡。
# ---------------------------------------------------------------------------

class BidRequest(BaseModel):
    hand: list[str]               # ["SA","SK","HQ",...] 只有自己的 13 張
    auction: list[dict]           # [{"seat":"N","bid":"1C"}, ...]
    legal_bids: list[str]         # 回傳值必須在這裡面
    me: str                       # N/E/S/W
    dealer: str
    vulnerability: str            # none/NS/EW/both
    board_id: str | None = None
    system: str | None = None
    masked: bool = True


class PlayRequest(BaseModel):
    hand: list[str]               # 這一手要打的那家的剩牌
    dummy: list[str] | None       # 明手剩牌,首引前為 None
    legal_cards: list[str]
    me: str
    playing_for: str              # 莊家代打明手時與 me 不同
    contract: dict                # {"level","strain","declarer","doubled"}
    auction: list[dict]
    completed_tricks: list[dict]
    current_trick: dict
    dealer: str
    vulnerability: str
    board_id: str | None = None
    me_hand: list[str] | None = None   # me 自己的牌(代打明手時才有意義)
    masked: bool = True


# ---------------------------------------------------------------------------
# 端點
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "version": VERSION}


@app.post("/decide/bid")
def decide_bid(request: BidRequest):
    bid, explanation, retrieved = choose_bid(request)

    # 保險:自己先擋掉非法叫品,不要讓 bot 端才發現
    if bid not in request.legal_bids:
        return {"error": f"illegal bid {bid!r}"}

    return {
        "schema_version": "0.1",
        "bid": bid,
        "explanation": explanation,
        "retrieved": retrieved,
        "version": VERSION,
    }


@app.post("/decide/play")
def decide_play(request: PlayRequest):
    card, explanation, retrieved = choose_card(request)

    if card not in request.legal_cards:
        return {"error": f"illegal card {card!r}"}

    return {
        "schema_version": "0.1",
        "card": card,
        "explanation": explanation,
        "retrieved": retrieved,
        "version": VERSION,
    }


# ---------------------------------------------------------------------------
# 以下換成你的 RAG
# ---------------------------------------------------------------------------

def choose_bid(request):
    """回傳 (叫品, 解釋, 檢索結果)。

    叫品用標準記法:1C 2H 3N 7S,pass 是 P,加倍 X,再加倍 XX。

    retrieved 是你檢索到的片段,格式自訂但建議至少有 doc_id 和 snippet。
    它會被完整寫進 decisions.jsonl,是你之後做消融實驗、證明檢索有效的
    唯一證據,不要省略。
    """
    # === 你的 RAG 從這裡開始 ===
    #
    # 1. 把 request 整理成查詢:手牌、牌力、牌型、目前叫牌進度
    # 2. 檢索相關的叫牌知識
    # 3. 交給模型決定叫品
    # 4. 確認結果在 request.legal_bids 裡,不在就退而求其次
    #
    # === 到這裡結束 ===

    return "P", "skeleton always passes", []


def choose_card(request):
    """回傳 (牌張, 解釋, 檢索結果)。

    牌張用兩字元:SA HT D9 C2,十寫作 T。
    """
    return request.legal_cards[0], "skeleton plays first legal card", []
