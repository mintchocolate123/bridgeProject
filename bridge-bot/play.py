"""把一個 agent 接到平台上,坐一個座位比賽。一個程序就是一個座位。

    python play.py --agent ben                              開新房間,坐北
    python play.py --agent ben --boards 8 --seed 7          開新房間並指定副數與種子
    python play.py --agent rag@http://localhost:8001 --room K7P2QX
    python play.py --agent rulebased --room K7P2QX --seat W --name baseline

四家對打就開四個程序,每個都是獨立連上平台的玩家,和別隊的 bot 完全一樣。

agent 只負責決定動作。這支程式負責其餘的事:入座、接收回合、送出動作、
斷線重連,以及下面這些保護:

    agent 丟出例外、回傳不合法的動作、或想超過 --budget 秒
        改用備援動作(規則式),這一手照樣送出,整場不會因為逾時被終止。
        決策紀錄裡會標記 fallback_used,分析時要排除。
"""

import argparse
import json
import logging
import os
import sys
import threading
import time

import requests

import config
from agents import make_agent, warm_up
from agents.rulebased import RuleBasedAgent
from logger import DecisionLogger

log = logging.getLogger("play")

ENDED = ("finished", "aborted", "expired")


class PlatformError(RuntimeError):
    def __init__(self, status, code, message):
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code


# ---------------------------------------------------------------------------
# 與平台溝通
# ---------------------------------------------------------------------------

class Platform:
    def __init__(self, server):
        self.base = server.rstrip("/") + "/api/v1"
        self.http = requests.Session()
        self.token = None

    def set_token(self, token):
        self.token = token
        self.http.headers["Authorization"] = f"Bearer {token}"

    def call(self, method, path, retry_until=None, **kwargs):
        """送請求並回傳 JSON。被限流就照 Retry-After 等;連不上時一直重試到 retry_until。"""
        kwargs.setdefault("timeout", 15)
        while True:
            try:
                r = self.http.request(method, self.base + path, **kwargs)
            except (requests.ConnectionError, requests.Timeout) as exc:
                if retry_until is None or time.time() > retry_until:
                    raise
                log.warning("連不上平台(%s),2 秒後重試", exc.__class__.__name__)
                time.sleep(2)
                continue
            if r.status_code == 429:
                time.sleep(float(r.headers.get("Retry-After", 1)))
                continue
            if not r.ok:
                try:
                    err = r.json()["error"]
                except Exception:
                    err = {"code": "http_error", "message": r.text[:200]}
                raise PlatformError(r.status_code, err.get("code"), err.get("message"))
            return r.json()

    def events(self, room, after):
        """讀事件串流,逐一回傳事件。斷線自動重連,從斷掉的地方接著讀。"""
        last_id = after
        while True:
            headers = {"Last-Event-ID": str(last_id)} if last_id is not None else {}
            try:
                with self.http.get(f"{self.base}/rooms/{room}/stream", headers=headers,
                                   stream=True, timeout=(10, 60)) as r:
                    if r.status_code == 429:
                        time.sleep(float(r.headers.get("Retry-After", 1)))
                        continue
                    if not r.ok:
                        raise PlatformError(r.status_code, "stream_failed", r.text[:200])
                    for event, event_id in _read_sse(r):
                        if event_id is not None:
                            last_id = event_id
                        yield event
                        if event["type"] == "stream_end":
                            return
            except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError) as exc:
                log.warning("串流中斷(%s),重新連線", exc.__class__.__name__)
                time.sleep(1)


def _read_sse(response):
    data, event_id = [], None
    for line in response.iter_lines(decode_unicode=True):
        if line is None:
            continue
        if line == "":
            if data:
                yield json.loads("\n".join(data)), event_id
            data, event_id = [], None
        elif line.startswith("data:"):
            data.append(line[5:].strip())
        elif line.startswith("id:"):
            event_id = int(line[3:].strip())


# ---------------------------------------------------------------------------
# 決策
# ---------------------------------------------------------------------------

def _run_with_budget(fn, request, budget):
    """在另一個執行緒跑 fn(request),超過 budget 秒就放棄。

    每次開新的執行緒:如果上一次卡住沒回來,不會連累這一次。
    """
    box = {}

    def target():
        try:
            box["value"] = fn(request)
        except BaseException as exc:          # noqa: BLE001 — 任何錯誤都交給備援
            box["error"] = exc

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(budget)
    if t.is_alive():
        raise TimeoutError(f"no decision within {budget:g} s")
    if "error" in box:
        raise box["error"]
    return box["value"]


def _last_resort(phase, request):
    if phase == "bid":
        return "P" if "P" in request["legal_bids"] else request["legal_bids"][0]
    return request["legal_cards"][0]


def decide(agent, fallback, phase, request, budget):
    """問 agent 要動作,保證回傳合法動作。回傳 (動作, response, meta)。"""
    key, legal_key = ("bid", "legal_bids") if phase == "bid" else ("card", "legal_cards")
    method = "decide_bid" if phase == "bid" else "decide_play"
    started = time.perf_counter()

    try:
        response, meta = _run_with_budget(getattr(agent, method), request, budget)
        action = response[key]
        if action not in request[legal_key]:
            raise ValueError(f"{action!r} is not legal")
        return action, response, meta
    except Exception as exc:
        error = f"{exc.__class__.__name__}: {exc}"
        log.warning("%s 失敗(%s),改用備援", getattr(agent, "name", "agent"), error)

    try:
        response, _ = getattr(fallback, method)(request)
        action = response[key]
        if action not in request[legal_key]:
            raise ValueError(f"fallback {action!r} is not legal")
    except Exception as exc:                    # 備援也失敗就出最保守的動作
        action = _last_resort(phase, request)
        response = {"schema_version": "0.1", key: action, "explanation": f"last resort ({exc})"}

    meta = {"agent": getattr(agent, "name", "agent"), "fallback_used": True, "error": error,
            "latency_ms": int((time.perf_counter() - started) * 1000)}
    return action, response, meta


# ---------------------------------------------------------------------------
# 一個座位
# ---------------------------------------------------------------------------

class Seat:
    def __init__(self, platform, agent, fallback=None, budget=config.TURN_BUDGET_S,
                 on_decision=None):
        self.platform = platform
        self.agent = agent
        self.fallback = fallback or RuleBasedAgent()
        self.budget = budget
        self.on_decision = on_decision
        self.room = None
        self.seat = None
        self.handled = set()                    # 已經送出的 turn_id
        self.decided = {}                       # 想好了但還沒送出的動作

    def join(self, name, room=None, seat=None, options=None):
        body = {"name": name}
        if room:
            body["room_code"] = room
        if seat:
            body["seat"] = seat
        if options:
            body["options"] = options
        data = self.platform.call("POST", "/rooms/join", json=body)
        self.platform.set_token(data["player_token"])
        self.room, self.seat = data["room_code"], data["seat"]
        return data

    def leave(self):
        self.platform.call("DELETE", f"/rooms/{self.room}/seat")

    def play(self):
        """一直打到房間結束,回傳最後的狀態。"""
        state = self.platform.call("GET", f"/rooms/{self.room}/state", retry_until=time.time() + 60)
        if state["status"] in ENDED:
            return state
        if state.get("your_turn"):
            self.take_turn(state["your_turn"])

        # 從目前狀態之後開始讀串流,不重看舊事件,也就不會去回應早就過去的回合
        for event in self.platform.events(self.room, after=state["last_seq"]):
            kind = event["type"]
            if kind == "your_turn":
                self.take_turn(event)
            elif kind == "board_start":
                log.info("第 %s 號牌開始(%s/%s),發牌 %s,局況 %s", event["board"], event["index"],
                         event["total"], event["dealer"], event["vulnerability"])
            elif kind == "board_end":
                log.info("第 %s 號牌結束,南北 %+d", event["board"], event["ns_score"])
            elif kind == "timeout" and event.get("seat") == self.seat:
                log.error("本座位逾時(連續第 %s 次)", event.get("consecutive"))
            elif kind == "stream_end":
                break
        return self.platform.call("GET", f"/rooms/{self.room}/state", retry_until=time.time() + 60)

    def take_turn(self, turn):
        turn_id = turn["turn_id"]
        if turn_id in self.handled:
            return
        request, phase = turn["request"], turn["phase"]

        # 同一個回合只想一次。送出失敗、之後平台重發同一個回合時,直接送已經決定好的動作
        action = self.decided.get(turn_id)
        if action is None:
            action, response, meta = decide(self.agent, self.fallback, phase, request, self.budget)
            self.decided[turn_id] = action
            if self.on_decision:
                self.on_decision(phase, request, response,
                                 {**meta, "room": self.room, "turn_id": turn_id})
            who = self.seat if turn["seat"] == self.seat else f"{self.seat}→{turn['seat']}"
            log.info("[%s] 第 %s 號牌 %s %s(%s ms%s)", who, turn["board"],
                     "叫" if phase == "bid" else "出", action, meta.get("latency_ms"),
                     ",備援" if meta.get("fallback_used") else "")

        try:
            self.submit(turn, action)
        except (requests.ConnectionError, requests.Timeout):
            # 平台掛了。它重啟後會重發這個回合,到時候再送
            log.error("送不出回合 %s,等平台恢復後重送", turn_id)
            return
        self.handled.add(turn_id)
        self.decided.pop(turn_id, None)

    def submit(self, turn, action):
        # 平台暫時連不上時一直重試,直到接近這個回合的截止時間
        deadline = time.time() + 45
        body = {"turn_id": turn["turn_id"], "action": action}
        try:
            self.platform.call("POST", f"/rooms/{self.room}/action", json=body, retry_until=deadline)
        except PlatformError as exc:
            if exc.code in ("stale_turn", "not_your_turn", "room_not_playing"):
                log.info("回合 %s 已經過去(%s),略過", turn["turn_id"], exc.code)
                return
            if exc.code == "illegal_action":
                # 不應該發生:送出前已經檢查過。保險起見改出最保守的動作
                log.error("平台判定 %s 不合法:%s", action, exc)
                body["action"] = _last_resort(turn["phase"], turn["request"])
                self.platform.call("POST", f"/rooms/{self.room}/action", json=body, retry_until=deadline)
                return
            raise


# ---------------------------------------------------------------------------
# 命令列
# ---------------------------------------------------------------------------

def print_results(state):
    status = state["status"]
    reason = f"({state['ended_reason']})" if state.get("ended_reason") else ""
    print(f"\n房間 {state['room_code']} {status}{reason}")
    total = 0
    for r in state["results"]:
        c = r["contract"]
        if r["passed_out"]:
            text = "流局"
        else:
            doubled = {"none": "", "doubled": "X", "redoubled": "XX"}[c["doubled"]]
            text = f"{c['level']}{c['strain']}{doubled} by {r['declarer']},{r['tricks']} 墩"
        total += r["ns_score"]
        print(f"  第 {r['board']} 號牌:{text},南北 {r['ns_score']:+d}")
    if state["results"]:
        print(f"  南北合計 {total:+d}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--agent", required=True, help="KIND 或 KIND@URL,例如 ben、rag@http://localhost:8001")
    p.add_argument("--server", default=config.PLATFORM_URL, help="平台網址")
    p.add_argument("--room", help="房號,不給就開新房間")
    p.add_argument("--seat", choices=list("NESW"), help="指定座位,不給就坐第一個空位")
    p.add_argument("--name", help="顯示在平台上的名稱,預設是 agent 名稱")
    p.add_argument("--boards", type=int, help="開新房間時打幾副")
    p.add_argument("--seed", type=int, help="開新房間時的發牌種子")
    p.add_argument("--first-board", type=int, help="開新房間時的起始牌號")
    p.add_argument("--budget", type=float, default=config.TURN_BUDGET_S,
                   help=f"每個決策最多等幾秒,超過改用備援(預設 {config.TURN_BUDGET_S})")
    p.add_argument("--log", help="決策紀錄檔,預設 runs/platform/<房號>-<座位>.jsonl")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    if args.room and any(v is not None for v in (args.boards, args.seed, args.first_board)):
        p.error("--boards / --seed / --first-board 只能在開新房間時使用")

    agent = make_agent(args.agent)
    warm_up([agent], log)                       # 先暖機再入座,避免第一手就超時

    options = {k: v for k, v in (("boards", args.boards), ("seed", args.seed),
                                 ("first_board", args.first_board)) if v is not None}
    seat = Seat(Platform(args.server), agent, budget=args.budget)
    try:
        info = seat.join(args.name or agent.name, args.room, args.seat, options or None)
    except PlatformError as exc:
        log.error("入座失敗:%s", exc)
        return 2
    except requests.ConnectionError:
        log.error("連不上平台 %s", args.server)
        return 2

    seat.on_decision = DecisionLogger(args.log or os.path.join(
        "runs", "platform", f"{seat.room}-{seat.seat}.jsonl"))
    log.info("房號 %s,座位 %s,%s 副。觀戰:%s/rooms/%s", seat.room, seat.seat,
             info["room"]["boards"], args.server.rstrip("/"), seat.room)

    try:
        state = seat.play()
    except KeyboardInterrupt:
        try:
            seat.leave()                        # 還沒開始就把座位讓出來
            log.info("已離開座位")
        except Exception:
            log.info("牌局已開始,無法離開;這個座位之後會逾時")
        return 130

    print_results(state)
    return 0 if state["status"] == "finished" else 1


if __name__ == "__main__":
    sys.exit(main())
