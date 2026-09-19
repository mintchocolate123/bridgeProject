"""依觀看者過濾事件。

事件在房間裡保存完整內容,送出去之前才經過這裡。每個端點都必須透過
這裡取事件,不可以自己挑欄位,否則很容易漏遮。

觀看者:
    "N"/"E"/"S"/"W"  坐在該座位的玩家
    "public"         觀眾。比賽中只看得到明手
    "all"            主辦方。全部可見
"""

from bridge_core.notation import SEATS

VIEWERS = ("all", "public") + SEATS


def filter_event(event, viewer):
    """回傳這個觀看者可以看到的版本。"""
    if viewer == "all":
        return event

    kind = event["type"]

    if kind == "board_start":
        hands = event["hands"]
        return {**event, "hands": {s: (hands[s] if s == viewer else None) for s in SEATS}}

    if kind == "your_turn":
        if event["actor"] == viewer:
            return event
        # 其他人只知道在等誰,看不到局面內容
        return {k: v for k, v in event.items() if k not in ("request",)} | {"type": "turn"}

    return event


def events_since(room, since, viewer):
    """取出序號 >= since 的事件,依觀看者過濾。"""
    return [filter_event(e, viewer) for e in room.events[max(since, 0):]]
