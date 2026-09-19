"""房間管理:房號、token 對應、逾時掃描、存檔、通知串流。

HTTP 層只和這裡打交道,不直接改 Room。每個會改變房間的操作結束時都
呼叫 _commit():存檔,然後喚醒正在等這個房間新事件的串流。

平台跑在單一事件迴圈裡,所有操作都在同一個執行緒依序執行,所以不需要
鎖;送出動作和逾時代打不可能同時發生。
"""

import asyncio
import secrets
import time

from bridge_core.notation import SEATS, pbn_to_deal

from bridge_platform import config
from bridge_platform.errors import Invalid, Unauthorized
from bridge_platform.room import (
    Room,
    find_room,
    hash_token,
    make_boards,
    new_room_code,
    normalize_join,
)


class Manager:
    def __init__(self, store, clock=time.time, **room_kwargs):
        self.store = store
        self.clock = clock
        self.room_kwargs = room_kwargs       # 測試時可以縮短逾時時間
        self.rooms = {}
        self._tokens = {}                    # token 雜湊 -> (房號, 座位)
        self._saved = {}                     # 房號 -> 已存檔的事件數
        self._signals = {}                   # 房號 -> asyncio.Event

    # -- 啟動還原 -----------------------------------------------------------

    def restore(self):
        """從資料庫讀回所有房間。進行中的回合重新給滿時間。"""
        for data, events in self.store.load_all():
            room = Room.from_dict(data, events=events, clock=self.clock, **self.room_kwargs)
            self.rooms[room.code] = room
            self._saved[room.code] = len(room.events)
            self._index_tokens(room)
            if room.status == "playing":
                room.restart_turn_clock()
                self._commit(room)
        return len(self.rooms)

    def _index_tokens(self, room):
        for seat, player in room.seats.items():
            if player is not None:
                self._tokens[player.token_hash] = (room.code, seat)

    # -- 建立與加入 ---------------------------------------------------------

    def _unique_code(self):
        while True:
            code = new_room_code()
            if code not in self.rooms and not self.store.exists(code):
                return code

    def create_room(self, boards, options, created_by):
        room = Room(self._unique_code(), boards, options, created_by,
                    clock=self.clock, **self.room_kwargs)
        self.rooms[room.code] = room
        self._saved[room.code] = 0
        self._commit(room)
        return room

    def create_from_options(self, options, created_by="bot"):
        opts = parse_options(options)
        if opts["seed"] is None:
            # 沒指定也要產生一個並記下來,這樣任何房間的牌都能重現
            opts["seed"] = secrets.randbelow(2**31)
        boards = make_boards(opts["boards"], opts["seed"], opts["first_board"])
        return self.create_room(boards, opts, created_by)

    def create_from_pbn(self, pbn_boards, created_by="admin"):
        if not pbn_boards or len(pbn_boards) > config.MAX_BOARDS:
            raise Invalid(f"need 1 to {config.MAX_BOARDS} boards")
        boards = []
        for b in pbn_boards:
            try:
                number = int(b["number"])
                if number < 1:
                    raise ValueError("board number starts at 1")
                boards.append({"number": number, "hands": pbn_to_deal(b["deal"])})
            except (KeyError, TypeError, ValueError) as exc:
                raise Invalid(f"bad board {b!r}: {exc}") from None
        return self.create_room(boards, {"boards": len(boards), "source": "pbn"}, created_by)

    def join(self, room_code, name, seat=None, options=None):
        """回傳 (room, 座位, token)。沒給房號就開新房間。"""
        normalize_join(name, seat)          # 開房前先驗證,不合法就不留下空房間
        room = (self.create_from_options(options or {}) if room_code is None
                else find_room(self.rooms, room_code))
        seat, token = room.join(name, seat)
        self._tokens[hash_token(token)] = (room.code, seat)
        self._commit(room)
        return room, seat, token

    def leave(self, room, seat):
        token_hash = room.seats[seat].token_hash
        room.leave(seat)
        self._tokens.pop(token_hash, None)
        self._commit(room)

    def authenticate(self, token):
        """token -> (room, 座位)。錯誤或已失效就拋 Unauthorized。"""
        if not token:
            raise Unauthorized("missing token")
        entry = self._tokens.get(hash_token(token))
        if entry is None:
            raise Unauthorized("invalid token")
        room = self.rooms.get(entry[0])
        if room is None or room.seats.get(entry[1]) is None:
            raise Unauthorized("invalid token")
        return room, entry[1]

    # -- 對局 ---------------------------------------------------------------

    def act(self, room, seat, turn_id, action):
        result = room.act(seat, turn_id, action)
        self._commit(room)
        return result

    def abort(self, room, reason):
        room.abort(reason)
        self._commit(room)

    def tick(self, now=None):
        """處理所有到期的回合與過期的等待房間。由背景工作定期呼叫。"""
        now = self.clock() if now is None else now
        changed = 0
        for room in list(self.rooms.values()):
            if room.check_timeout(now) or room.check_expired(now):
                self._commit(room)
                changed += 1
        return changed

    # -- 存檔與通知 ---------------------------------------------------------

    def _commit(self, room):
        self.store.save(room, events_from=self._saved.get(room.code, 0))
        self._saved[room.code] = len(room.events)
        signal = self._signals.pop(room.code, None)
        if signal is not None:
            signal.set()

    async def wait_for_change(self, room, since, timeout):
        """等到房間有序號 >= since 的事件,或逾時。"""
        if len(room.events) > since:
            return
        signal = self._signals.get(room.code)
        if signal is None:
            signal = self._signals[room.code] = asyncio.Event()
        try:
            await asyncio.wait_for(signal.wait(), timeout)
        except asyncio.TimeoutError:
            pass

    # -- 查詢 ---------------------------------------------------------------

    def list_rooms(self, status=None):
        rooms = sorted(self.rooms.values(), key=lambda r: r.created_at, reverse=True)
        return [r.summary() for r in rooms if status is None or r.status == status]


def parse_options(options):
    """驗證 bot 開房時帶的選項。"""
    if not isinstance(options, dict):
        raise Invalid("options must be an object")

    unknown = set(options) - {"boards", "seed", "first_board"}
    if unknown:
        raise Invalid(f"unknown options: {sorted(unknown)}")

    def as_int(key, default, lo=None, hi=None):
        value = options.get(key, default)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise Invalid(f"{key} must be an integer")
        if (lo is not None and value < lo) or (hi is not None and value > hi):
            raise Invalid(f"{key} must be between {lo} and {hi}")
        return value

    return {
        "boards": as_int("boards", config.DEFAULT_BOARDS, 1, config.MAX_BOARDS),
        "seed": as_int("seed", None),
        "first_board": as_int("first_board", 1, 1, 10_000),
    }


__all__ = ["Manager", "parse_options", "SEATS"]
