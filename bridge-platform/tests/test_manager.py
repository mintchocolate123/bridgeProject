import asyncio

import pytest

from bridge_core.notation import SEATS
from bridge_platform.errors import Invalid, NotFound, Unauthorized
from bridge_platform.manager import Manager, parse_options
from bridge_platform.store import Store

from tests.test_room import FakeClock

ROOM_KW = dict(turn_timeout=300, max_timeouts=2, waiting_expire=1800)


def make_manager(path, clock=None):
    clock = clock or FakeClock()
    return Manager(Store(path), clock=clock, **ROOM_KW), clock


def fill(manager, **options):
    room, seat, token = manager.join(None, "bot-N", "N", options or {"boards": 2, "seed": 3})
    tokens = {seat: token}
    for s in ("E", "S", "W"):
        _, seat, token = manager.join(room.code, f"bot-{s}", s)
        tokens[seat] = token
    return room, tokens


def act_once(manager, room):
    t = room.turn
    if t["phase"] == "bid":
        action = "P" if any(e["bid"] != "P" for e in room.deal.auction) else "1C"
    else:
        action = room.deal.default_action(t["actor"])
    return manager.act(room, t["actor"], t["turn_id"], action)


def test_join_creates_room_and_records_seed(tmp_path):
    m, _ = make_manager(str(tmp_path / "db.sqlite3"))
    room, seat, token = m.join(None, "a", None, {"boards": 3})
    assert seat == "N" and room.status == "waiting"
    assert isinstance(room.options["seed"], int)          # 沒指定也會產生並記下
    assert m.authenticate(token) == (room, "N")


def test_invalid_join_leaves_no_empty_room(tmp_path):
    m, _ = make_manager(str(tmp_path / "db.sqlite3"))
    with pytest.raises(Invalid):
        m.join(None, "", None)
    with pytest.raises(Invalid):
        m.join(None, "a", "Q")
    assert m.rooms == {}


def test_bad_options():
    for bad in ({"boards": 0}, {"boards": 33}, {"boards": "4"}, {"seed": 1.5},
                {"first_board": 0}, {"colour": "red"}, {"boards": True}):
        with pytest.raises(Invalid):
            parse_options(bad)
    assert parse_options({}) == {"boards": 4, "seed": None, "first_board": 1}


def test_unknown_room_and_token(tmp_path):
    m, _ = make_manager(str(tmp_path / "db.sqlite3"))
    with pytest.raises(NotFound):
        m.join("ZZZZZZ", "a")
    with pytest.raises(Unauthorized):
        m.authenticate("pt_nope")
    with pytest.raises(Unauthorized):
        m.authenticate(None)


def test_leave_invalidates_token(tmp_path):
    m, _ = make_manager(str(tmp_path / "db.sqlite3"))
    room, seat, token = m.join(None, "a", "S")
    m.leave(room, seat)
    with pytest.raises(Unauthorized):
        m.authenticate(token)


def test_same_seed_same_deals(tmp_path):
    m, _ = make_manager(str(tmp_path / "db.sqlite3"))
    a, _, _ = m.join(None, "a", None, {"boards": 2, "seed": 42})
    b, _, _ = m.join(None, "b", None, {"boards": 2, "seed": 42})
    assert a.code != b.code and a.boards == b.boards


def test_pbn_room(tmp_path):
    m, _ = make_manager(str(tmp_path / "db.sqlite3"))
    deal = "N:862.62.AQT52.A96 AQJT9.Q875.97.K7 7543.AT943.8.JT8 K.KJ.KJ643.Q5432"
    room = m.create_from_pbn([{"number": 5, "deal": deal}])
    assert room.created_by == "admin" and room.boards[0]["number"] == 5
    assert all(p is None for p in room.seats.values())      # 主辦方不佔座位
    with pytest.raises(Invalid):
        m.create_from_pbn([{"number": 1, "deal": "N:AK.. garbage"}])
    with pytest.raises(Invalid):
        m.create_from_pbn([])


def test_tick_handles_timeouts_and_expiry(tmp_path):
    m, clock = make_manager(str(tmp_path / "db.sqlite3"))
    room, _ = fill(m)
    lonely, _, _ = m.join(None, "alone", None)
    clock.advance(300)
    assert m.tick() == 1                                     # 只有對局中那間逾時
    assert room.seats["N"].consecutive_timeouts == 1
    clock.advance(1500)
    m.tick()
    assert lonely.status == "expired"


def test_restore_after_restart(tmp_path):
    path = str(tmp_path / "db.sqlite3")
    m1, clock = make_manager(path)
    room, tokens = fill(m1)
    for _ in range(15):
        act_once(m1, room)
    before = room.state("all")
    code, turn_id = room.code, room.turn["turn_id"]
    m1.store.close()

    # 「重開伺服器」
    clock.advance(200)
    m2 = Manager(Store(path), clock=clock, **ROOM_KW)
    assert m2.restore() == 1
    restored = m2.rooms[code]
    after = restored.state("all")

    assert after["view"] == before["view"]
    assert after["results"] == before["results"]
    assert restored.turn["turn_id"] == turn_id
    assert restored.turn["deadline"] == clock() + 300        # 重新給滿時間
    assert restored.events[-1]["type"] == "your_turn"        # 重送回合通知

    # token 在重啟後仍然有效,可以接著打
    for seat, token in tokens.items():
        assert m2.authenticate(token) == (restored, seat)
    while restored.status == "playing":
        act_once(m2, restored)
    assert restored.status == "finished"

    # 事件有完整存下,序號連續
    m3 = Manager(Store(path), clock=clock, **ROOM_KW)
    m3.restore()
    seqs = [e["seq"] for e in m3.rooms[code].events]
    assert seqs == list(range(len(seqs)))


def test_wait_for_change_wakes_on_commit(tmp_path):
    m, _ = make_manager(str(tmp_path / "db.sqlite3"))
    room, _ = fill(m)

    async def scenario():
        since = len(room.events)
        waiter = asyncio.create_task(m.wait_for_change(room, since, timeout=5))
        await asyncio.sleep(0.01)
        assert not waiter.done()
        act_once(m, room)
        await asyncio.wait_for(waiter, 1)                    # 被喚醒,不是等到逾時
        assert len(room.events) > since

        start = asyncio.get_running_loop().time()
        await m.wait_for_change(room, len(room.events), timeout=0.05)
        assert asyncio.get_running_loop().time() - start >= 0.04   # 沒事件就等到逾時

    asyncio.run(scenario())
