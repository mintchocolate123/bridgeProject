import pytest

from bridge_core.notation import SEATS
from bridge_platform.errors import Conflict, Invalid
from bridge_platform.filters import events_since, filter_event
from bridge_platform.room import Room, hash_token, make_boards


class FakeClock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def new_room(boards=2, seed=7, clock=None, **kw):
    clock = clock or FakeClock()
    return Room("ABCDEF", make_boards(boards, seed), options={"seed": seed},
                clock=clock, turn_timeout=300, max_timeouts=2, waiting_expire=1800, **kw), clock


def full_room(**kw):
    room, clock = new_room(**kw)
    tokens = {}
    for s in SEATS:
        seat, token = room.join(f"bot-{s}", s)
        tokens[seat] = token
    return room, clock, tokens


def play_one(room):
    """目前回合的行動者做一個動作。

    叫牌時第一個有機會的人開 1C,其餘 pass,確保每副牌都會成約並打完;
    打牌時出最小的合法牌。全部 pass 的話每副牌都流局,打牌階段測不到。
    """
    t = room.turn
    if t["phase"] == "bid":
        opened = any(e["bid"] != "P" for e in room.deal.auction)
        action = "P" if opened else "1C"
    else:
        action = room.deal.default_action(t["actor"])
    return room.act(t["actor"], t["turn_id"], action)


# -- 入座 -------------------------------------------------------------------

def test_auto_seat_order():
    room, _ = new_room()
    assert [room.join(f"b{i}")[0] for i in range(4)] == ["N", "E", "S", "W"]


def test_choose_seat_and_conflicts():
    room, _ = new_room()
    assert room.join("a", "e")[0] == "E"           # 小寫也接受
    with pytest.raises(Conflict) as e:
        room.join("b", "E")
    assert e.value.code == "seat_taken"
    with pytest.raises(Invalid):
        room.join("b", "X")
    with pytest.raises(Invalid):
        room.join("   ")
    with pytest.raises(Invalid):
        room.join("x" * 41)
    for _ in range(3):
        room.join("c")
    assert room.status == "playing"
    with pytest.raises(Conflict) as e:
        room.join("late")
    assert e.value.code == "room_not_waiting"


def test_leave_before_start():
    room, _ = new_room()
    seat, _ = room.join("a")
    room.leave(seat)
    assert room.seats[seat] is None
    assert room.join("b")[0] == seat                   # 空出來的位子可以再坐


def test_token_identifies_seat():
    room, _ = new_room()
    seat, token = room.join("a", "S")
    assert room.seat_of(hash_token(token)) == "S"
    assert room.seat_of(hash_token("pt_wrong")) is None
    assert token not in str(room.to_dict())            # token 本身不落地


def test_waiting_room_expires():
    room, clock = new_room()
    room.join("a")
    clock.advance(1799)
    assert not room.check_expired()
    clock.advance(1)
    assert room.check_expired() and room.status == "expired"
    assert room.events[-1]["type"] == "room_end"


# -- 對局 -------------------------------------------------------------------

def test_starts_when_full():
    room, _, _ = full_room()
    assert room.status == "playing"
    types = [e["type"] for e in room.events]
    assert types[-2:] == ["board_start", "your_turn"]
    assert room.turn["actor"] == "N" and room.turn["phase"] == "bid"    # 第 1 副 N 發牌
    assert room.turn["deadline"] == room.clock() + 300


def test_plays_all_boards():
    room, _, _ = full_room(boards=3)
    while room.status == "playing":
        play_one(room)
    assert room.status == "finished"
    assert [r["board"] for r in room.results] == [1, 2, 3]
    assert all(not r["passed_out"] and r["tricks"] is not None for r in room.results)
    assert len(room.played) == 3
    end = room.events[-1]
    assert end["type"] == "room_end" and end["status"] == "finished"
    assert len(end["results"]) == 3


def test_board_rotation():
    room, _, _ = full_room(boards=3)
    starts = []
    while room.status == "playing":
        if room.events[-1]["type"] == "your_turn" and room.events[-2]["type"] == "board_start":
            starts.append(room.events[-2])
        play_one(room)
    assert [(s["board"], s["dealer"], s["vulnerability"]) for s in starts] == [
        (1, "N", "none"), (2, "E", "NS"), (3, "S", "EW")]


def test_stale_and_wrong_seat():
    room, _, _ = full_room()
    t = room.turn
    with pytest.raises(Conflict) as e:
        room.act("N", "t_999999", "P")
    assert e.value.code == "stale_turn"
    with pytest.raises(Conflict) as e:
        room.act("E", t["turn_id"], "P")
    assert e.value.code == "not_your_turn"
    room.act("N", t["turn_id"], "P")
    with pytest.raises(Conflict) as e:
        room.act("N", t["turn_id"], "P")               # 同一個 turn_id 不能用兩次
    assert e.value.code == "stale_turn"


def test_illegal_action_changes_nothing():
    room, _, _ = full_room()
    t = room.turn
    n_events = len(room.events)
    for bad in ("8S", "XX", "hello", "S10"):
        with pytest.raises(Invalid) as e:
            room.act("N", t["turn_id"], bad)
        assert e.value.code == "illegal_action"
    assert len(room.events) == n_events and room.turn == t


def test_normalized_action_returned():
    room, _, _ = full_room()
    t = room.turn
    assert room.act("N", t["turn_id"], "pass")["action"] == "P"


def test_dummy_turn_goes_to_declarer():
    room, _, _ = full_room()
    # N 開 1S,其他 pass:莊家 N,明手 S,首引 E
    for call in ("1S", "P", "P", "P"):
        t = room.turn
        room.act(t["actor"], t["turn_id"], call)
    assert room.turn["actor"] == "E"
    t = room.turn
    room.act("E", t["turn_id"], room.deal.default_action("E"))
    assert room.turn["seat"] == "S" and room.turn["actor"] == "N"
    with pytest.raises(Conflict) as e:
        room.act("S", room.turn["turn_id"], room.deal.legal_actions("N")[0])
    assert e.value.code == "not_your_turn"
    yt = room.events[-1]
    assert yt["type"] == "your_turn" and yt["request"]["playing_for"] == "S"


def test_next_turn_id_when_same_actor_again():
    room, _, _ = full_room()
    for call in ("1S", "P", "P", "P"):
        t = room.turn
        room.act(t["actor"], t["turn_id"], call)
    t = room.turn
    room.act("E", t["turn_id"], room.deal.default_action("E"))
    # 輪到明手 S(由 N 決定),N 出完後輪到 W,不是 N
    t = room.turn
    r = room.act("N", t["turn_id"], room.deal.default_action("N"))
    assert r["next_turn_id"] is None


# -- 逾時 -------------------------------------------------------------------

def test_single_timeout_auto_plays():
    room, clock, _ = full_room()
    t = room.turn
    clock.advance(299)
    assert not room.check_timeout()
    clock.advance(1)
    assert room.check_timeout()
    assert room.seats["N"].consecutive_timeouts == 1
    bid = next(e for e in reversed(room.events) if e["type"] == "bid")
    assert bid["seat"] == "N" and bid["bid"] == "P" and bid["auto"] is True
    assert any(e["type"] == "timeout" and e["seat"] == "N" for e in room.events)
    assert room.turn["actor"] == "E" and room.status == "playing"
    with pytest.raises(Conflict) as e:
        room.act("N", t["turn_id"], "1C")               # 遲到的答案
    assert e.value.code in ("stale_turn", "not_your_turn")


def test_valid_action_resets_counter():
    room, clock, _ = full_room()
    clock.advance(300); room.check_timeout()           # N 逾時一次
    for _ in range(3):                                 # E S W 正常
        play_one(room)
    assert room.turn["actor"] == "N"
    play_one(room)                                     # N 這次有回答
    assert room.seats["N"].consecutive_timeouts == 0


def test_two_consecutive_timeouts_abort():
    room, clock, _ = full_room()
    clock.advance(300); room.check_timeout()           # N 第一次
    for _ in range(3):
        play_one(room)
    assert room.turn["actor"] == "N"
    clock.advance(300); room.check_timeout()           # N 第二次
    assert room.status == "aborted"
    assert room.end_reason == "timeout" and room.ended_by_seat == "N"
    assert room.turn is None
    end = room.events[-1]
    assert end["type"] == "room_end" and end["seat"] == "N"
    assert room.played and room.played[-1].get("incomplete") is True


def test_other_seats_timeouts_do_not_accumulate():
    room, clock, _ = full_room()
    for _ in range(4):                                 # 四家各逾時一次
        clock.advance(300); room.check_timeout()
    assert room.status == "playing"
    assert all(room.seats[s].consecutive_timeouts == 1 for s in SEATS)


# -- 視角 -------------------------------------------------------------------

def test_no_hidden_cards_leak_to_players():
    room, _, _ = full_room(boards=2)
    while room.status == "playing":
        play_one(room)

    for viewer in SEATS:
        board_hands = {}
        for e in events_since(room, 0, viewer):
            if e["type"] == "board_start":
                assert all(h is None for s, h in e["hands"].items() if s != viewer)
                assert e["hands"][viewer] is not None
                board_hands[e["board"]] = e["hands"][viewer]
            if e["type"] == "your_turn":
                assert e["actor"] == viewer
                req = e["request"]
                assert "all_hands" not in req and req["masked"] is True
                assert set(req.get("me_hand", req["hand"])) <= set(board_hands[e["board"]])
            if e["type"] == "turn":
                assert "request" not in e


def test_public_sees_no_hands():
    room, _, _ = full_room()
    for _ in range(10):
        play_one(room)
    for e in events_since(room, 0, "public"):
        if e["type"] == "board_start":
            assert all(h is None for h in e["hands"].values())
        assert e["type"] != "your_turn" and "request" not in e
    view = room.state("public")["view"]
    visible = [s for s, h in view["hands"].items() if h is not None]
    assert visible in ([], [room.deal.dummy])


def test_state_your_turn_only_for_actor():
    room, _, _ = full_room()
    assert room.state("N")["your_turn"]["turn_id"] == room.turn["turn_id"]
    assert room.state("E")["your_turn"] is None
    assert room.state("public")["your_turn"] is None
    assert room.state("E")["turn"]["actor"] == "N"


def test_all_viewer_sees_everything():
    room, _, _ = full_room()
    e = next(e for e in room.events if e["type"] == "board_start")
    assert filter_event(e, "all")["hands"]["E"] is not None


# -- 紀錄與序列化 -----------------------------------------------------------

def test_record_only_after_end():
    room, _, _ = full_room(boards=1)
    with pytest.raises(Conflict):
        room.record()
    while room.status == "playing":
        play_one(room)
    rec = room.record()
    assert len(rec["deals"]) == 1 and rec["deals"][0]["hands"]["E"]


def test_round_trip_mid_game():
    room, clock, _ = full_room(boards=2)
    for _ in range(20):
        play_one(room)
    data = room.to_dict()
    copy = Room.from_dict(data, events=room.events, clock=clock,
                          turn_timeout=300, max_timeouts=2, waiting_expire=1800)
    assert copy.state("all") == room.state("all")
    t = copy.turn
    copy.act(t["actor"], t["turn_id"], copy.deal.default_action(t["actor"]))
    assert copy.turn != room.turn


def test_restart_turn_clock():
    room, clock, _ = full_room()
    clock.advance(250)
    room.restart_turn_clock()
    assert room.turn["deadline"] == clock() + 300
    assert room.events[-1]["type"] == "your_turn"
