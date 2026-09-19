"""房間:一張牌桌的完整生命週期。

入座、開始、發回合、收動作、逾時代打、換下一副、結束。規則本身交給
bridge-core 的 Deal,這裡只管「誰、什麼時候、能不能」。

本模組不碰 HTTP、不碰資料庫、不開執行緒,也不自己計時。時間由注入的
clock 提供,逾時由外部定期呼叫 check_timeout() 觸發。這樣測試時可以直接
快轉時鐘,不用真的等 300 秒。

所有會改變狀態的方法都假設呼叫端已經確保同一時間只有一個人在呼叫
(平台是單一事件迴圈,天然滿足這點)。
"""

import hashlib
import random
import secrets
import time
from datetime import datetime, timezone

from bridge_core import (
    Deal,
    IllegalAction,
    board_dealer,
    board_vulnerability,
    random_hands,
    validate_hands,
)
from bridge_core.notation import SEATS

from bridge_platform import config
from bridge_platform.errors import Conflict, Invalid, NotFound

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # 去掉容易看錯的 I O 0 1
ENDED = ("finished", "aborted", "expired")


def new_room_code(rng=None):
    rng = rng or secrets.SystemRandom()
    return "".join(rng.choice(_CODE_ALPHABET) for _ in range(6))


def new_token():
    return "pt_" + secrets.token_urlsafe(24)


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).astimezone().isoformat(timespec="seconds")


def make_boards(count, seed=None, first_board=1):
    """依種子產生 count 副牌。同一個種子永遠得到同一批牌。"""
    rng = random.Random(seed)
    return [{"number": first_board + i, "hands": random_hands(rng)} for i in range(count)]


def normalize_join(name, seat):
    """驗證並整理入座參數,回傳 (名稱, 座位或 None)。開房前先檢查,避免留下空房間。"""
    name = (name or "").strip() if isinstance(name, str) else ""
    if not 1 <= len(name) <= config.MAX_NAME_LENGTH:
        raise Invalid(f"name must be 1 to {config.MAX_NAME_LENGTH} characters")
    if seat is not None:
        seat = str(seat).upper()
        if seat not in SEATS:
            raise Invalid(f"seat must be one of {SEATS}")
    return name, seat


class Player:
    def __init__(self, name, token_hash, joined_at):
        self.name = name
        self.token_hash = token_hash
        self.joined_at = joined_at
        self.consecutive_timeouts = 0
        self.total_timeouts = 0

    def to_dict(self):
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data):
        p = cls(data["name"], data["token_hash"], data["joined_at"])
        p.consecutive_timeouts = data.get("consecutive_timeouts", 0)
        p.total_timeouts = data.get("total_timeouts", 0)
        return p


class Room:
    def __init__(self, code, boards, options=None, created_by="bot", clock=time.time,
                 turn_timeout=None, max_timeouts=None, waiting_expire=None):
        if not boards:
            raise Invalid("a room needs at least one board")
        for b in boards:
            validate_hands(b["hands"])

        self.code = code
        self.boards = [{"number": b["number"], "hands": b["hands"]} for b in boards]
        self.options = dict(options or {})
        self.created_by = created_by
        self.clock = clock

        self.turn_timeout = turn_timeout if turn_timeout is not None else config.TURN_TIMEOUT_S
        self.max_timeouts = max_timeouts if max_timeouts is not None else config.MAX_CONSECUTIVE_TIMEOUTS
        self.waiting_expire = waiting_expire if waiting_expire is not None else config.WAITING_EXPIRE_S

        self.status = "waiting"
        self.seats = {s: None for s in SEATS}
        self.created_at = clock()
        self.started_at = None
        self.ended_at = None
        self.end_reason = None
        self.ended_by_seat = None

        self.board_index = -1
        self.deal = None
        self.played = []               # 已結束各副牌的 Deal.to_dict()
        self.results = []              # 各副牌的結果

        self.turn = None               # {"turn_id","board","seat","actor","phase","deadline"}
        self.turn_counter = 0
        self.events = []

    # -- 入座 ---------------------------------------------------------------

    def join(self, name, seat=None):
        """坐進座位,回傳 (座位, token)。token 只在這裡出現一次。"""
        if self.status != "waiting":
            raise Conflict(f"room {self.code} is {self.status}", code="room_not_waiting")

        name, seat = normalize_join(name, seat)

        if seat is None:
            free = [s for s in SEATS if self.seats[s] is None]
            if not free:
                raise Conflict("no free seat", code="room_full")
            seat = free[0]
        elif self.seats[seat] is not None:
            raise Conflict(f"seat {seat} is taken", code="seat_taken")

        token = new_token()
        self.seats[seat] = Player(name, hash_token(token), self.clock())
        self._emit({"type": "room_update", "status": self.status, "seats": self.seat_names()})

        if all(self.seats[s] is not None for s in SEATS):
            self._start()
        return seat, token

    def leave(self, seat):
        if self.status != "waiting":
            raise Conflict("cannot leave after the room has started", code="room_not_waiting")
        self.seats[seat] = None
        self._emit({"type": "room_update", "status": self.status, "seats": self.seat_names()})

    def seat_of(self, token_hash):
        for seat, player in self.seats.items():
            if player is not None and secrets.compare_digest(player.token_hash, token_hash):
                return seat
        return None

    def seat_names(self):
        return {s: (p.name if p else None) for s, p in self.seats.items()}

    # -- 對局流程 -----------------------------------------------------------

    def _start(self):
        self.status = "playing"
        self.started_at = self.clock()
        self._emit({"type": "room_update", "status": self.status, "seats": self.seat_names()})
        self._start_board(0)

    def _start_board(self, index):
        spec = self.boards[index]
        n = spec["number"]
        self.board_index = index
        self.deal = Deal(spec["hands"], dealer=board_dealer(n),
                         vulnerability=board_vulnerability(n), board_id=f"{self.code}-{n}")
        self._emit({"type": "board_start", "board": n, "index": index + 1,
                    "total": len(self.boards), "dealer": self.deal.dealer,
                    "vulnerability": self.deal.vulnerability,
                    "hands": self.deal.initial_hands})
        self._issue_turn()

    @property
    def board_number(self):
        return self.boards[self.board_index]["number"] if self.board_index >= 0 else None

    def _issue_turn(self):
        t = self.deal.to_act()
        self.turn_counter += 1
        now = self.clock()
        self.turn = {
            "turn_id": f"t_{self.turn_counter:06d}",
            "board": self.board_number,
            "seat": t.seat,
            "actor": t.actor,
            "phase": t.phase,
            "issued_at": now,
            "deadline": now + self.turn_timeout,
        }
        self._emit(self._your_turn_event())

    def _your_turn_event(self):
        t = self.turn
        return {"type": "your_turn", "turn_id": t["turn_id"], "board": t["board"],
                "seat": t["seat"], "actor": t["actor"], "phase": t["phase"],
                "deadline": iso(t["deadline"]),
                "request": self.deal.request_for(t["actor"])}

    def act(self, seat, turn_id, action):
        """bot 送出動作。回傳 {"accepted", "action", "next_turn_id"}。"""
        if self.status != "playing":
            raise Conflict(f"room {self.code} is {self.status}", code="room_not_playing")
        if self.turn is None or turn_id != self.turn["turn_id"]:
            raise Conflict(f"turn {turn_id} is not the current turn", code="stale_turn")
        if seat != self.turn["actor"]:
            raise Conflict(f"it is {self.turn['actor']}'s turn, not {seat}", code="not_your_turn")

        try:
            normalized = self._apply(action, auto=False)
        except IllegalAction as exc:
            raise Invalid(str(exc), code="illegal_action") from None

        self.seats[seat].consecutive_timeouts = 0

        next_turn = None
        if self.turn is not None and self.turn["actor"] == seat:
            next_turn = self.turn["turn_id"]
        return {"accepted": True, "action": normalized, "next_turn_id": next_turn}

    def _apply(self, action, auto):
        """把動作交給裁判,並把裁判的事件轉成平台事件。不合法會拋 IllegalAction,狀態不變。"""
        actor = self.turn["actor"]
        events = self.deal.apply(actor, action)
        normalized = self.deal.history[-1]["action"]
        board = self.board_number
        self.turn = None

        for e in events:
            e = dict(e)
            e.pop("board_id", None)
            if e["type"] == "deal_end":
                e["type"] = "board_end"
            if e["type"] in ("bid", "card"):
                e["auto"] = auto
            self._emit({**e, "board": board})

        if self.deal.finished:
            self.played.append(self.deal.to_dict())
            self.results.append({"board": board, **self.deal.result()})
            if self.board_index + 1 < len(self.boards):
                self._start_board(self.board_index + 1)
            else:
                self._end("finished")
        else:
            self._issue_turn()

        return normalized

    # -- 逾時與結束 ---------------------------------------------------------

    def check_timeout(self, now=None):
        """若目前回合已過截止時間就處理逾時。有處理回傳 True。"""
        if self.status != "playing" or self.turn is None:
            return False
        now = self.clock() if now is None else now
        if now < self.turn["deadline"]:
            return False

        seat = self.turn["actor"]
        player = self.seats[seat]
        player.consecutive_timeouts += 1
        player.total_timeouts += 1
        self._emit({"type": "timeout", "board": self.board_number, "seat": seat,
                    "turn_id": self.turn["turn_id"],
                    "consecutive": player.consecutive_timeouts})

        if player.consecutive_timeouts >= self.max_timeouts:
            self._end("aborted", reason="timeout", seat=seat)
        else:
            self._apply(self.deal.default_action(seat), auto=True)
        return True

    def check_expired(self, now=None):
        """等待中的房間太久沒坐滿就關閉。有關閉回傳 True。"""
        if self.status != "waiting":
            return False
        now = self.clock() if now is None else now
        if now - self.created_at < self.waiting_expire:
            return False
        self._end("expired", reason="not enough players")
        return True

    def abort(self, reason="aborted by admin"):
        if self.status in ENDED:
            raise Conflict(f"room {self.code} already {self.status}", code="room_not_playing")
        self._end("aborted", reason=reason)

    def _end(self, status, reason=None, seat=None):
        # 打到一半的牌也存下來,紀錄才完整;它不會出現在 results 裡
        if self.deal is not None and not self.deal.finished:
            self.played.append({**self.deal.to_dict(), "incomplete": True})

        self.status = status
        self.turn = None
        self.ended_at = self.clock()
        self.end_reason = reason
        self.ended_by_seat = seat
        self._emit({"type": "room_end", "status": status, "reason": reason,
                    "seat": seat, "results": list(self.results)})

    @property
    def ended(self):
        return self.status in ENDED

    # -- 事件 ---------------------------------------------------------------

    def _emit(self, event):
        record = {"seq": len(self.events), "ts": iso(self.clock()), **event}
        self.events.append(record)
        return record

    # -- 對外的畫面 ---------------------------------------------------------

    def summary(self):
        return {
            "room_code": self.code,
            "status": self.status,
            "seats": self.seat_names(),
            "boards": len(self.boards),
            "board": self.board_number,
            "board_index": self.board_index + 1 if self.board_index >= 0 else 0,
            "created_by": self.created_by,
            "created_at": iso(self.created_at),
            "ended_reason": self.end_reason,
            "ended_by_seat": self.ended_by_seat,
        }

    def public_turn(self):
        if self.turn is None:
            return None
        t = self.turn
        return {"turn_id": t["turn_id"], "board": t["board"], "seat": t["seat"],
                "actor": t["actor"], "phase": t["phase"], "deadline": iso(t["deadline"])}

    def state(self, viewer):
        """目前畫面。viewer 是座位、"public" 或 "all"。"""
        data = {
            **self.summary(),
            "last_seq": len(self.events) - 1,
            "viewer": viewer,
            "view": self.deal.view(viewer) if self.deal is not None else None,
            "turn": self.public_turn(),
            "results": list(self.results),
            "your_turn": None,
        }
        if self.turn is not None and viewer in SEATS and self.turn["actor"] == viewer:
            data["your_turn"] = {k: v for k, v in self._your_turn_event().items() if k != "type"}
        return data

    def record(self):
        """結束後的完整紀錄,四家手牌公開。前端用來重播。"""
        if not self.ended:
            raise Conflict("record is available after the room ends", code="room_not_ended")
        return {
            **self.summary(),
            "players": {s: ({"name": p.name, "total_timeouts": p.total_timeouts} if p else None)
                        for s, p in self.seats.items()},
            "deals": list(self.played),
            "results": list(self.results),
        }

    def frames(self, index):
        """第 index 副(從 1 開始)每一步之後的畫面,四家公開。前端回放用。

        規則全部由 bridge-core 重播算出,前端不需要懂橋牌規則。
        第 0 個畫面是發完牌、還沒有人動作的樣子。
        """
        if not self.ended:
            raise Conflict("replay is available after the room ends", code="room_not_ended")
        if not 1 <= index <= len(self.played):
            raise NotFound(f"board index {index} not found", code="board_not_found")

        data = self.played[index - 1]
        deal = Deal(data["hands"], data["dealer"], data["vulnerability"], data.get("board_id"))
        frames = [{"step": 0, "action": None, "view": deal.view("all")}]
        for i, step in enumerate(data.get("history", []), start=1):
            turn = deal.to_act()
            deal.apply(step["actor"], step["action"])
            frames.append({"step": i,
                           "action": {"seat": turn.seat, "actor": step["actor"],
                                      "phase": turn.phase, "action": step["action"]},
                           "view": deal.view("all")})
        return {"room_code": self.code, "index": index, "total": len(self.played),
                "board": self.boards[index - 1]["number"],
                "incomplete": bool(data.get("incomplete")), "frames": frames}

    # -- 序列化 -------------------------------------------------------------

    def to_dict(self):
        """房間狀態,不含事件。事件另外存。"""
        return {
            "code": self.code,
            "boards": self.boards,
            "options": self.options,
            "created_by": self.created_by,
            "status": self.status,
            "seats": {s: (p.to_dict() if p else None) for s, p in self.seats.items()},
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "end_reason": self.end_reason,
            "ended_by_seat": self.ended_by_seat,
            "board_index": self.board_index,
            "deal": self.deal.to_dict() if self.deal else None,
            "played": self.played,
            "results": self.results,
            "turn": self.turn,
            "turn_counter": self.turn_counter,
        }

    @classmethod
    def from_dict(cls, data, events=(), clock=time.time, **kwargs):
        room = cls(data["code"], data["boards"], data.get("options"),
                   data.get("created_by", "bot"), clock=clock, **kwargs)
        room.status = data["status"]
        room.seats = {s: (Player.from_dict(p) if p else None) for s, p in data["seats"].items()}
        room.created_at = data["created_at"]
        room.started_at = data.get("started_at")
        room.ended_at = data.get("ended_at")
        room.end_reason = data.get("end_reason")
        room.ended_by_seat = data.get("ended_by_seat")
        room.board_index = data["board_index"]
        room.deal = Deal.from_dict(data["deal"]) if data.get("deal") else None
        room.played = data.get("played", [])
        room.results = data.get("results", [])
        room.turn = data.get("turn")
        room.turn_counter = data.get("turn_counter", 0)
        room.events = list(events)
        return room

    def restart_turn_clock(self):
        """伺服器重啟後呼叫:進行中的回合重新給滿時間。"""
        if self.turn is not None:
            now = self.clock()
            self.turn["issued_at"] = now
            self.turn["deadline"] = now + self.turn_timeout
            self._emit(self._your_turn_event())


def find_room(rooms, code):
    room = rooms.get((code or "").upper())
    if room is None:
        raise NotFound(f"room {code} not found", code="room_not_found")
    return room
