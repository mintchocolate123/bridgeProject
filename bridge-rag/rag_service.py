"""RAG 決策服務:把某一個版本的 RAG 包成 bot 可以呼叫的 HTTP 介面。

這一層只負責收發,不含任何 RAG 邏輯。RAG 本身寫在 versions/ 底下,一個
版本一個檔案。服務是無狀態的:每次請求都帶完整局面,不要在這裡保存
對局狀態。它也不知道平台、房間、回合的存在,那些是 bridge-bot 的事。

啟動(選一個版本、給一個 port):
    python rag_service.py --version v1 --port 8001

兩個版本同時跑就開兩個程序,用不同 port:
    python rag_service.py --version v1 --port 8001
    python rag_service.py --version v2 --port 8002

bot 用網址選要接哪一個:
    python play.py --agent rag@http://localhost:8002 --room K7P2QX
"""

import argparse
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

import versions

log = logging.getLogger("rag_service")

DEFAULT_VERSION = os.environ.get("RAG_VERSION", "v0")


# ---------------------------------------------------------------------------
# 請求格式。bot 送來的就是平台(bridge-core)產生的局面,原封不動。
# extra="allow":之後平台多了欄位,這裡不用改也收得到。
# ---------------------------------------------------------------------------

class BidRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    hand: list[str]               # 自己的 13 張
    auction: list[dict]           # [{"seat":"N","bid":"1C"}, ...]
    legal_bids: list[str]         # 回傳值必須在這裡面
    me: str                       # N/E/S/W
    dealer: str
    vulnerability: str            # none/NS/EW/both
    board_id: Optional[str] = None
    system: Optional[str] = None
    masked: bool = True


class PlayRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    hand: list[str]               # 這一手要出牌的那家的剩牌
    dummy: Optional[list[str]]    # 明手剩牌,首引前為 None
    legal_cards: list[str]
    me: str
    playing_for: str              # 莊家替明手出牌時與 me 不同
    contract: dict                # {"level","strain","declarer","doubled"}
    auction: list[dict]
    completed_tricks: list[dict]
    current_trick: dict           # {"leader","cards"}
    dealer: str
    vulnerability: str
    board_id: Optional[str] = None
    me_hand: Optional[list[str]] = None
    masked: bool = True


# ---------------------------------------------------------------------------
# 服務
# ---------------------------------------------------------------------------

def create_app(version=DEFAULT_VERSION):
    rag = versions.load(version)          # 版本名稱打錯就在啟動時失敗,不要等到第一手

    @asynccontextmanager
    async def lifespan(app):
        if callable(getattr(rag, "setup", None)):
            log.info("載入 %s", version)
            rag.setup()
        log.info("RAG %s 就緒:%s", version, getattr(rag, "DESCRIPTION", ""))
        yield

    app = FastAPI(title=f"Bridge RAG {version}", lifespan=lifespan)

    @app.get("/health")
    def health():
        # bot 用這裡的 version 標記決策紀錄,所以要能分辨是哪一版
        return {"status": "ok", "version": version,
                "description": getattr(rag, "DESCRIPTION", "")}

    @app.post("/decide/bid")
    def decide_bid(request: BidRequest):
        bid, explanation, retrieved = rag.choose_bid(request)
        # 先在這裡擋掉不合法的叫品。bot 收到錯誤會改用備援動作,並記下原因
        if bid not in request.legal_bids:
            raise HTTPException(422, f"{version} returned illegal bid {bid!r}")
        return {"schema_version": "0.1", "bid": bid, "explanation": explanation,
                "retrieved": retrieved, "version": version}

    @app.post("/decide/play")
    def decide_play(request: PlayRequest):
        card, explanation, retrieved = rag.choose_card(request)
        if card not in request.legal_cards:
            raise HTTPException(422, f"{version} returned illegal card {card!r}")
        return {"schema_version": "0.1", "card": card, "explanation": explanation,
                "retrieved": retrieved, "version": version}

    return app


app = create_app()          # 給 `uvicorn rag_service:app` 用,版本由 RAG_VERSION 決定


def main():
    import uvicorn

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", default=DEFAULT_VERSION,
                   help=f"要跑的版本,可選:{', '.join(versions.available())}")
    p.add_argument("--port", type=int, default=8001)
    p.add_argument("--host", default="127.0.0.1")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    uvicorn.run(create_app(args.version), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
