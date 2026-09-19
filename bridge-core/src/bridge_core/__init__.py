"""橋牌裁判程式庫。

純邏輯,零相依,不碰網路、執行緒、檔案。平台後端與本機實驗工具共用。

    from bridge_core import Deal

    deal = Deal.from_board(1)
    while not deal.finished:
        turn = deal.to_act()
        request = deal.request_for(turn.actor)
        action = my_agent.decide(request)
        events = deal.apply(turn.actor, action)
    print(deal.result())
"""

from bridge_core.boards import (
    board_dealer,
    board_vulnerability,
    random_hands,
    validate_hands,
)
from bridge_core.deal import VIEWERS, Deal, Turn
from bridge_core.errors import DealOver, IllegalAction, NotYourTurn, RefereeError
from bridge_core.score import imps, score_contract, score_deal

__all__ = [
    "Deal", "Turn", "VIEWERS",
    "RefereeError", "NotYourTurn", "IllegalAction", "DealOver",
    "board_dealer", "board_vulnerability", "random_hands", "validate_hands",
    "score_contract", "score_deal", "imps",
]

__version__ = "0.1.0"
