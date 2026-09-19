import pytest
from fastapi.testclient import TestClient

from bridge_platform.api import create_app
from bridge_platform.manager import Manager
from bridge_platform.store import Store

from tests.test_room import FakeClock

ADMIN = "secret-admin-key"


@pytest.fixture
def env(tmp_path):
    clock = FakeClock()
    manager = Manager(Store(str(tmp_path / "db.sqlite3")), clock=clock,
                      turn_timeout=300, max_timeouts=2, waiting_expire=1800)
    app = create_app(manager=manager, admin_key=ADMIN, tick_interval=3600, rate_limit=1000)
    with TestClient(app) as client:
        yield client, manager, clock


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def fill_room(client, **options):
    r = client.post("/api/v1/rooms/join", json={"name": "bot-N", "seat": "N",
                                                "options": options or {"boards": 1, "seed": 5}})
    assert r.status_code == 201, r.text
    code = r.json()["room_code"]
    tokens = {"N": r.json()["player_token"]}
    for s in "ESW":
        r = client.post("/api/v1/rooms/join", json={"name": f"bot-{s}", "room_code": code, "seat": s})
        assert r.status_code == 201, r.text
        tokens[s] = r.json()["player_token"]
    return code, tokens


def error_code(response):
    return response.json()["error"]["code"]


def test_join_flow(env):
    client, _, _ = env
    r = client.post("/api/v1/rooms/join", json={"name": "a"})
    assert r.status_code == 201
    body = r.json()
    assert body["seat"] == "N" and body["player_token"].startswith("pt_")
    assert body["room"]["status"] == "waiting"

    code = body["room_code"]
    r = client.post("/api/v1/rooms/join", json={"name": "b", "room_code": code.lower(), "seat": "N"})
    assert r.status_code == 409 and error_code(r) == "seat_taken"
    r = client.post("/api/v1/rooms/join", json={"name": "b", "room_code": "ZZZZZZ"})
    assert r.status_code == 404 and error_code(r) == "room_not_found"
    r = client.post("/api/v1/rooms/join", json={"name": "b", "seat": "Q"})
    assert r.status_code == 422 and error_code(r) == "invalid_request"
    r = client.post("/api/v1/rooms/join", json={"seat": "N"})       # 少了 name
    assert r.status_code == 422 and error_code(r) == "invalid_request"
    r = client.post("/api/v1/rooms/join", json={"name": "b", "options": {"boards": 99}})
    assert r.status_code == 422


def test_auth(env):
    client, _, _ = env
    code, tokens = fill_room(client)
    r = client.get(f"/api/v1/rooms/{code}/state")
    assert r.status_code == 401 and error_code(r) == "invalid_token"
    r = client.get(f"/api/v1/rooms/{code}/state", headers=auth("pt_forged"))
    assert r.status_code == 401

    other, _ = fill_room(client)
    r = client.get(f"/api/v1/rooms/{other}/state", headers=auth(tokens["N"]))
    assert r.status_code == 401                               # 拿 A 房的 token 看 B 房


def test_play_through_http(env):
    client, _, _ = env
    code, tokens = fill_room(client)
    moves = 0
    while True:
        state = client.get(f"/api/v1/rooms/{code}").json()
        if state["status"] != "playing":
            break
        actor = state["turn"]["actor"]
        mine = client.get(f"/api/v1/rooms/{code}/state", headers=auth(tokens[actor])).json()
        yt = mine["your_turn"]
        assert yt and yt["turn_id"] == state["turn"]["turn_id"]
        req = yt["request"]
        if yt["phase"] == "bid":
            action = "P" if any(e["bid"] != "P" for e in req["auction"]) else "1NT"
        else:
            action = req["legal_cards"][-1].lower()          # 故意用小寫
        r = client.post(f"/api/v1/rooms/{code}/action", headers=auth(tokens[actor]),
                        json={"turn_id": yt["turn_id"], "action": action})
        assert r.status_code == 200, r.text
        moves += 1
    assert state["status"] == "finished"
    assert moves == 4 + 52                                   # 1N 加三個 pass,再打 52 張

    rec = client.get(f"/api/v1/rooms/{code}/record").json()
    assert rec["results"][0]["contract"]["strain"] == "N"
    assert rec["deals"][0]["hands"]["E"]                     # 結束後四家公開


def test_action_errors(env):
    client, _, _ = env
    code, tokens = fill_room(client)
    turn_id = client.get(f"/api/v1/rooms/{code}/state", headers=auth(tokens["N"])).json()["your_turn"]["turn_id"]

    r = client.post(f"/api/v1/rooms/{code}/action", headers=auth(tokens["E"]),
                    json={"turn_id": turn_id, "action": "P"})
    assert r.status_code == 409 and error_code(r) == "not_your_turn"
    r = client.post(f"/api/v1/rooms/{code}/action", headers=auth(tokens["N"]),
                    json={"turn_id": "t_bogus", "action": "P"})
    assert r.status_code == 409 and error_code(r) == "stale_turn"
    r = client.post(f"/api/v1/rooms/{code}/action", headers=auth(tokens["N"]),
                    json={"turn_id": turn_id, "action": "9S"})
    assert r.status_code == 422 and error_code(r) == "illegal_action"
    r = client.post(f"/api/v1/rooms/{code}/action", headers=auth(tokens["N"]),
                    json={"turn_id": turn_id})
    assert r.status_code == 422 and error_code(r) == "invalid_request"
    r = client.post(f"/api/v1/rooms/{code}/action", headers=auth(tokens["N"]),
                    json={"turn_id": turn_id, "action": "1C"})
    assert r.status_code == 200 and r.json()["action"] == "1C"


def test_player_state_masks_other_hands(env):
    client, _, _ = env
    code, tokens = fill_room(client)
    view = client.get(f"/api/v1/rooms/{code}/state", headers=auth(tokens["E"])).json()["view"]
    assert view["hands"]["E"] and all(view["hands"][s] is None for s in "NSW")
    pub = client.get(f"/api/v1/rooms/{code}").json()
    assert all(h is None for h in pub["view"]["hands"].values())
    assert pub["your_turn"] is None
    r = client.get(f"/api/v1/rooms/{code}/record")
    assert r.status_code == 409 and error_code(r) == "room_not_ended"


def test_leave(env):
    client, _, _ = env
    r = client.post("/api/v1/rooms/join", json={"name": "a", "seat": "W"}).json()
    code, token = r["room_code"], r["player_token"]
    assert client.delete(f"/api/v1/rooms/{code}/seat", headers=auth(token)).status_code == 200
    assert client.get(f"/api/v1/rooms/{code}/state", headers=auth(token)).status_code == 401


def test_timeout_via_tick(env):
    client, manager, clock = env
    code, tokens = fill_room(client)
    clock.advance(300)
    manager.tick()
    state = client.get(f"/api/v1/rooms/{code}").json()
    assert state["turn"]["actor"] == "E"
    clock.advance(300); manager.tick()                       # E 第一次
    clock.advance(300); manager.tick()                       # S 第一次
    clock.advance(300); manager.tick()                       # W 第一次 -> 流局,下一副沒了
    state = client.get(f"/api/v1/rooms/{code}").json()
    assert state["status"] == "finished"                     # 四家各逾時一次,沒有人連續兩次


def test_admin(env):
    client, _, _ = env
    deal = "N:862.62.AQT52.A96 AQJT9.Q875.97.K7 7543.AT943.8.JT8 K.KJ.KJ643.Q5432"
    body = {"boards": [{"number": 7, "deal": deal}]}
    assert client.post("/api/v1/admin/rooms", json=body).status_code == 401
    assert client.post("/api/v1/admin/rooms", json=body, headers=auth("wrong")).status_code == 401
    r = client.post("/api/v1/admin/rooms", json=body, headers=auth(ADMIN))
    assert r.status_code == 201
    code = r.json()["room_code"]
    assert all(v is None for v in r.json()["seats"].values())

    for s in "NESW":
        client.post("/api/v1/rooms/join", json={"name": s, "room_code": code})
    full = client.get(f"/api/v1/admin/rooms/{code}", headers=auth(ADMIN)).json()
    assert all(h is not None for h in full["view"]["hands"].values())
    assert full["view"]["dealer"] == "S" and full["view"]["vulnerability"] == "both"   # 第 7 副

    r = client.post(f"/api/v1/admin/rooms/{code}/abort", headers=auth(ADMIN), json={})
    assert r.status_code == 200 and r.json()["status"] == "aborted"
    r = client.post(f"/api/v1/admin/rooms/{code}/abort", headers=auth(ADMIN), json={})
    assert r.status_code == 409


def test_admin_disabled(tmp_path):
    manager = Manager(Store(str(tmp_path / "db.sqlite3")))
    with TestClient(create_app(manager=manager, admin_key=None)) as client:
        r = client.post("/api/v1/admin/rooms", json={}, headers=auth("anything"))
        assert r.status_code == 403 and error_code(r) == "admin_disabled"


def test_rate_limit(tmp_path):
    manager = Manager(Store(str(tmp_path / "db.sqlite3")))
    with TestClient(create_app(manager=manager, rate_limit=5, tick_interval=3600)) as client:
        responses = [client.post("/api/v1/rooms/join", json={"name": "a"}) for _ in range(8)]
        codes = [r.status_code for r in responses]
        assert codes[:5] == [201] * 5 and 429 in codes[5:]
        limited = next(r for r in responses if r.status_code == 429)
        assert limited.headers["Retry-After"] == "1"
        assert error_code(limited) == "rate_limited"


def test_rooms_list(env):
    client, _, _ = env
    code, _ = fill_room(client)
    client.post("/api/v1/rooms/join", json={"name": "lonely"})
    playing = client.get("/api/v1/rooms", params={"status": "playing"}).json()
    assert [r["room_code"] for r in playing] == [code]
    assert len(client.get("/api/v1/rooms").json()) == 2


def play_to_end(client, code, tokens):
    while True:
        state = client.get(f"/api/v1/rooms/{code}").json()
        if state["status"] != "playing":
            return state
        actor = state["turn"]["actor"]
        yt = client.get(f"/api/v1/rooms/{code}/state", headers=auth(tokens[actor])).json()["your_turn"]
        req = yt["request"]
        if yt["phase"] == "bid":
            action = "P" if any(e["bid"] != "P" for e in req["auction"]) else "1NT"
        else:
            action = req["legal_cards"][0]
        client.post(f"/api/v1/rooms/{code}/action", headers=auth(tokens[actor]),
                    json={"turn_id": yt["turn_id"], "action": action})


def test_replay_frames(env):
    client, _, _ = env
    code, tokens = fill_room(client)
    r = client.get(f"/api/v1/rooms/{code}/replay/1")
    assert r.status_code == 409 and error_code(r) == "room_not_ended"   # 比賽中不給看

    play_to_end(client, code, tokens)
    r = client.get(f"/api/v1/rooms/{code}/replay/1")
    assert r.status_code == 200, r.text
    frames = r.json()["frames"]
    assert len(frames) == 1 + 4 + 52
    assert frames[0]["action"] is None and frames[0]["view"]["phase"] == "bidding"
    assert all(len(frames[0]["view"]["hands"][s]) == 13 for s in "NESW")
    assert frames[1]["action"] == {"seat": "N", "actor": "N", "phase": "bid", "action": "1N"}
    last = frames[-1]["view"]
    assert last["phase"] == "finished" and len(last["tricks"]) == 13
    recorded = client.get(f"/api/v1/rooms/{code}/record").json()["results"][0]
    assert last["result"] == {k: v for k, v in recorded.items() if k != "board"}
    # 莊家替明手出牌時,seat 是明手、actor 是莊家
    dummy = last["dummy"]
    assert any(f["action"]["seat"] == dummy and f["action"]["actor"] != dummy
               for f in frames[1:] if f["action"]["phase"] == "play")

    assert client.get(f"/api/v1/rooms/{code}/replay/2").status_code == 404
    assert client.get(f"/api/v1/rooms/{code}/replay/0").status_code == 404


def test_serves_ui(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>ui</html>")
    (dist / "assets" / "app-1a2b.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("nope")
    manager = Manager(Store(str(tmp_path / "db.sqlite3")))
    with TestClient(create_app(manager=manager, tick_interval=3600, ui_dist=str(dist))) as client:
        assert client.get("/").text == "<html>ui</html>"
        assert client.get("/rooms/ABCDEF/replay").text == "<html>ui</html>"     # 前端路由
        r = client.get("/assets/app-1a2b.js")
        assert r.text == "console.log(1)" and "immutable" in r.headers["cache-control"]
        assert "nope" not in client.get("/../secret.txt").text
        assert "nope" not in client.get("/%2e%2e/secret.txt").text
        assert client.get("/api/v1/health").json()["status"] == "ok"
        r = client.get("/api/v1/nothing-here")
        assert r.status_code == 404 and error_code(r) == "not_found"


def test_without_ui(tmp_path):
    manager = Manager(Store(str(tmp_path / "db.sqlite3")))
    with TestClient(create_app(manager=manager, tick_interval=3600,
                               ui_dist=str(tmp_path / "missing"))) as client:
        assert client.get("/").status_code == 404
        assert client.get("/api/v1/health").status_code == 200
