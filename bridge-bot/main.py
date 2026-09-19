"""本機批次實驗。不經過平台,直接在這台電腦上把四家湊起來打。

比賽與展示走平台(play.py)。這支是給自己跑數據用的:速度快、沒有逾時,
可以一次跑幾百副,也可以關掉遮蔽做對照組。規則全部交給 bridge-core,
這裡只負責「問 agent、把動作交給裁判」這個迴圈。

座位設定用 KIND 或 KIND@URL,可用的 KIND 見 agents/__init__.py。
搭檔是比較兩套系統的自然單位,所以提供 --ns / --ew 快捷:

    python main.py --deals 10
        四家 baseline

    python main.py --deals 10 --ew ben
        南北 baseline 對東西 BEN

    python main.py --deals 50 --ns rag@http://localhost:8001 --ew rag@http://localhost:8002
        兩個不同版本的 RAG 互打

    python main.py --deals 50 --ns rag --ew ben --no-play
        RAG 對 BEN,只跑叫牌

需要個別指定座位時用 --seat,它會覆蓋 --ns / --ew:

    python main.py --seat N=rag@http://localhost:8001 E=ben
"""

import argparse
import json
import logging
import os
import random
from collections import Counter

from bridge_core import Deal, IllegalAction
from bridge_core.notation import SEATS

import config
from agents import make_agent, warm_up
from logger import DecisionLogger

log = logging.getLogger("main")


def build_agents(ns, ew, seat_overrides=()):
    agents = {seat: make_agent(ns if seat in ("N", "S") else ew) for seat in SEATS}
    for item in seat_overrides:
        seat, _, spec = item.partition("=")
        seat = seat.strip().upper()
        if seat not in SEATS:
            raise ValueError(f"bad seat: {seat!r}")
        agents[seat] = make_agent(spec)
    return agents


def run_deal(deal, agents, on_decision=None, play_out=True, reveal_all=False):
    """把一副牌打完(或只叫完)。回傳這副牌的結果 dict。

    agent 出了不合法的動作或拋出例外時,這副牌記為錯誤並停止,不會
    偷偷換成別的動作,以免實驗數據被污染。
    """
    error = None
    try:
        while not deal.finished:
            turn = deal.to_act()
            if turn.phase == "play" and not play_out:
                break

            request = deal.request_for(turn.actor, reveal_all=reveal_all)
            agent = agents[turn.actor]
            if turn.phase == "bid":
                response, meta = agent.decide_bid(request)
                action = response["bid"]
            else:
                response, meta = agent.decide_play(request)
                action = response["card"]

            if on_decision:
                on_decision(turn.phase, request, response, meta)

            try:
                deal.apply(turn.actor, action)
            except IllegalAction as exc:
                raise ValueError(f"{getattr(agent, 'name', '?')} at {turn.actor}: {exc}") from None
    except Exception as exc:
        log.exception("%s failed", deal.board_id)
        error = str(exc)

    result = deal.result() or {
        "contract": deal.contract, "passed_out": deal.passed_out,
        "declarer": deal.declarer, "tricks": None, "score": None, "ns_score": None,
    }
    return {**deal.to_dict(), **result, "error": error}


def summary(r):
    if r["error"]:
        return f"{r['board_id']}: ERROR {r['error']}"
    if r["passed_out"]:
        return f"{r['board_id']}: passed out"
    c = r["contract"]
    if c is None:
        return f"{r['board_id']}: unfinished"
    doubled = {"none": "", "doubled": "X", "redoubled": "XX"}[c["doubled"]]
    text = f"{r['board_id']}: {c['level']}{c['strain']}{doubled} by {c['declarer']}"
    if r["tricks"] is None:               # --no-play,只跑了叫牌
        return text
    return f"{text}, {r['tricks']} tricks, NS {r['ns_score']:+d}"


def run_deals(agents, n, seed=None, **kwargs):
    """依標準 16 副循環決定發牌者與局況,同一個種子得到同一批牌。"""
    rng = random.Random(seed)
    results = []
    for i in range(n):
        deal = Deal.from_board(i + 1, rng=rng, board_id=f"board-{i + 1}")
        r = run_deal(deal, agents, **kwargs)
        results.append(r)
        log.info("%s", summary(r))
    return results


def write_results(results, path):
    """每副一行,含初始發牌與完整歷史,可以用 bridge_core.Deal.from_dict 重播。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def report(results, agents):
    done = [r for r in results if not r["error"] and r["contract"]]
    errors = [r for r in results if r["error"]]
    passed = [r for r in results if not r["error"] and r["passed_out"]]

    print(f"\nNS = {agents['N'].name} / {agents['S'].name}")
    print(f"EW = {agents['E'].name} / {agents['W'].name}")
    print(f"總副數 {len(results)}  成約 {len(done)}  流局 {len(passed)}  錯誤 {len(errors)}")
    for r in errors[:5]:
        print("  ERROR", r["board_id"], r["error"])
    if not done:
        return

    scored = [r for r in done if r["ns_score"] is not None]
    if scored:
        total = sum(r["ns_score"] for r in scored)
        print(f"NS 總分 {total:+d}   平均每副 {total / len(scored):+.1f}")

    by_side = Counter("NS" if r["declarer"] in ("N", "S") else "EW" for r in done)
    print(f"做莊次數 NS {by_side['NS']} / EW {by_side['EW']}")
    contracts = Counter(f"{r['contract']['level']}{r['contract']['strain']}" for r in done)
    print("常見合約:", ", ".join(f"{c}x{n}" for c, n in contracts.most_common(6)))


def main():
    p = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                description=__doc__)
    p.add_argument("--deals", type=int, default=5)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--ns", default="rulebased", help="南北的 agent 設定")
    p.add_argument("--ew", default="rulebased", help="東西的 agent 設定")
    p.add_argument("--seat", nargs="*", default=[],
                   help="個別指定座位,例如 N=ben E=rag@http://localhost:8002")
    p.add_argument("--no-play", action="store_true", help="只跑叫牌")
    p.add_argument("--no-mask", action="store_true", help="關閉手牌遮蔽,僅供對照實驗")
    p.add_argument("--log", default=config.DECISION_LOG, help="每個決策一行的紀錄檔")
    p.add_argument("--results", default=None,
                   help="每副一行的結果檔,預設為 --log 同名的 *.results.jsonl")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.no_mask:
        log.warning("手牌遮蔽已關閉,此批結果不可與正常對局混用")

    agents = build_agents(args.ns, args.ew, args.seat)
    warm_up(agents, log)

    results = run_deals(agents, args.deals, seed=args.seed,
                        on_decision=DecisionLogger(args.log),
                        play_out=not args.no_play, reveal_all=args.no_mask)

    results_path = args.results or os.path.splitext(args.log)[0] + ".results.jsonl"
    write_results(results, results_path)
    log.info("結果已寫入 %s", results_path)
    report(results, agents)


if __name__ == "__main__":
    main()
