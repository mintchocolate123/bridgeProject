"""最簡單的橋牌 bot 範例,給外部開發者參考。

只相依 requests,不需要本專案的任何程式碼。決策是隨機的合法動作,
把 decide() 換成你自己的邏輯就是一個能上場的 bot。

    pip install requests

    python simple_bot.py                          開新房間,印出房號
    python simple_bot.py --room K7P2QX            加入房間
    python simple_bot.py --room K7P2QX --seat E   指定座位
    python simple_bot.py --stream                 用事件串流代替輪詢

兩種模式:
    輪詢   每秒問一次「輪到我了嗎」。最容易寫,任何語言幾行就能做到
    串流   平台主動推事件過來,反應快、不浪費請求。要處理斷線重連
"""

import argparse
import json
import random
import sys
import time

import requests


# ---------------------------------------------------------------------------
# 決策:把這個函式換成你自己的邏輯
# ---------------------------------------------------------------------------

def decide(turn):
    """收到 your_turn,回傳一個動作字串。

    turn["phase"] 是 "bid" 或 "play"。
    turn["request"] 裡有你的手牌、叫牌歷史、合法動作清單等。
    輪到明手時你是莊家,request["hand"] 是明手的牌。
    """
    req = turn["request"]
    if turn["phase"] == "bid":
        legal = req["legal_bids"]
        # 多數時候 pass,偶爾叫一個一階的,這樣牌局才打得起來
        if "P" in legal and random.random() < 0.6:
            return "P"
        low = [b for b in legal if b[0] == "1"] or legal
        return random.choice(low)
    return random.choice(req["legal_cards"])


# ---------------------------------------------------------------------------
# 與平台溝通
# ---------------------------------------------------------------------------

class Bot:
    def __init__(self, server, name):
        self.server = server.rstrip("/")
        self.name = name
        self.token = None
        self.room = None
        self.seat = None
        self.http = requests.Session()

    def url(self, path):
        return f"{self.server}/api/v1{path}"

    def request(self, method, path, **kwargs):
        """送請求。被限流(429)就照 Retry-After 等一下再送。"""
        kwargs.setdefault("timeout", 10)
        for _ in range(10):
            r = self.http.request(method, self.url(path), **kwargs)
            if r.status_code != 429:
                return r
            time.sleep(float(r.headers.get("Retry-After", 1)))
        return r

    def join(self, room=None, seat=None, options=None):
        body = {"name": self.name}
        if room:
            body["room_code"] = room
        if seat:
            body["seat"] = seat
        if options:
            body["options"] = options
        r = self.request("POST", "/rooms/join", json=body)
        data = check(r)
        self.token, self.room, self.seat = data["player_token"], data["room_code"], data["seat"]
        self.http.headers["Authorization"] = f"Bearer {self.token}"
        print(f"[{self.name}] 房號 {self.room},座位 {self.seat}", flush=True)
        return data

    def act(self, turn):
        """做決定並送出。不合法就換一個再送,直到被接受或回合已經過去。"""
        for _ in range(5):
            action = decide(turn)
            r = self.request("POST", f"/rooms/{self.room}/action",
                             json={"turn_id": turn["turn_id"], "action": action})
            if r.ok:
                return r.json()
            code = error_code(r)
            if code == "illegal_action":
                continue                     # 不算逾時,換一個再試
            if code in ("stale_turn", "not_your_turn", "room_not_playing"):
                return None                  # 這個回合已經過去了,忽略
            check(r)
        return None

    # -- 輪詢模式 -----------------------------------------------------------

    def run_polling(self, interval=1.0):
        handled = None
        while True:
            state = check(self.request("GET", f"/rooms/{self.room}/state"))
            if state["status"] in ("finished", "aborted", "expired"):
                return self.finish(state)
            turn = state.get("your_turn")
            if turn and turn["turn_id"] != handled:
                handled = turn["turn_id"]
                self.act(turn)
                continue                     # 剛動作完,馬上再看一次
            time.sleep(interval)

    # -- 串流模式 -----------------------------------------------------------

    def run_stream(self):
        last_id = None
        while True:
            headers = {"Last-Event-ID": str(last_id)} if last_id is not None else {}
            try:
                with self.http.get(self.url(f"/rooms/{self.room}/stream"), headers=headers,
                                   stream=True, timeout=(10, 60)) as r:
                    check(r)
                    for event, event_id in read_sse(r):
                        if event_id is not None:
                            last_id = event_id
                        if event["type"] == "your_turn":
                            self.act(event)
                        elif event["type"] == "stream_end":
                            state = check(self.request("GET", f"/rooms/{self.room}/state"))
                            return self.finish(state)
            except (requests.ConnectionError, requests.Timeout) as exc:
                print(f"[{self.name}] 連線中斷,重新連線:{exc}", flush=True)
                time.sleep(1)

    def finish(self, state):
        print(f"[{self.name}] 房間結束:{state['status']}"
              + (f"({state['ended_reason']})" if state.get("ended_reason") else ""), flush=True)
        for r in state["results"]:
            c = r["contract"]
            if r["passed_out"]:
                text = "流局"
            else:
                doubled = {"none": "", "doubled": "X", "redoubled": "XX"}[c["doubled"]]
                text = (f"{c['level']}{c['strain']}{doubled} by {r['declarer']},"
                        f"{r['tricks']} 墩,南北 {r['ns_score']:+d}")
            print(f"  第 {r['board']} 副:{text}", flush=True)
        return state


def read_sse(response):
    """逐則讀出 SSE 訊息,回傳 (事件, id)。註解行(keep-alive)會被略過。"""
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


def error_code(response):
    try:
        return response.json()["error"]["code"]
    except Exception:
        return None


def check(response):
    if not response.ok:
        raise RuntimeError(f"{response.status_code} {error_code(response)}: {response.text[:200]}")
    return response.json() if "json" in response.headers.get("content-type", "") else response


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--server", default="http://localhost:8000")
    p.add_argument("--room", help="房號,不給就開新房間")
    p.add_argument("--seat", choices=list("NESW"))
    p.add_argument("--name", default="simple-bot")
    p.add_argument("--boards", type=int, help="開新房間時要打幾副")
    p.add_argument("--seed", type=int, help="開新房間時的發牌種子")
    p.add_argument("--stream", action="store_true", help="用事件串流代替輪詢")
    args = p.parse_args()

    options = {k: v for k, v in (("boards", args.boards), ("seed", args.seed)) if v is not None}
    bot = Bot(args.server, args.name)
    bot.join(args.room, args.seat, options or None)
    try:
        bot.run_stream() if args.stream else bot.run_polling()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
