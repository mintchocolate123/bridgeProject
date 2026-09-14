"""跑對局。

座位設定用 SEAT=KIND[@URL] 的形式,KIND 可以是:
    passing     全 pass
    rulebased   簡易規則式 baseline
    ben         BEN 引擎,預設 http://localhost:8085
    rag         自建的 RAG 服務,預設 http://localhost:8001

搭檔是比較兩套系統的自然單位,所以提供 --ns / --ew 快捷:

    python main.py --deals 10
        四家 baseline

    python main.py --deals 10 --ew ben
        南北 baseline 對東西 BEN

    python main.py --deals 50 --ns rag@http://localhost:8001 \
                              --ew rag@http://localhost:8002
        兩個不同版本的 RAG 互打

    python main.py --deals 50 --ns rag --ew ben --no-play
        RAG 對 BEN,只跑叫牌

需要個別指定座位時用 --seat,它會覆蓋 --ns / --ew:

    python main.py --seat N=rag@http://localhost:8001 E=ben
"""

import argparse
import logging
from collections import Counter

import config
from agents.ben import BenAgent
from agents.passing import PassingAgent
from agents.rag import RagAgent
from agents.rulebased import RuleBasedAgent
from logger import DecisionLogger
from notation import SEATS
from table import Table

log = logging.getLogger("main")

DEFAULT_URL = {"ben": config.BEN_URL, "rag": config.RAG_URL}


def make_agent(spec, fallback_kind="rulebased"):
    """"ben" / "rag@http://localhost:8002" -> agent 實例"""
    kind, _, url = spec.partition("@")
    kind = kind.strip().lower()
    url = url.strip() or DEFAULT_URL.get(kind)

    if kind == "passing":
        return PassingAgent()
    if kind == "rulebased":
        return RuleBasedAgent()
    if kind == "ben":
        return BenAgent(base_url=url)
    if kind == "rag":
        return RagAgent(base_url=url, fallback=RuleBasedAgent())

    raise ValueError(f"unknown agent kind: {kind!r}")


def build_agents(args):
    agents = {}
    for seat in SEATS:
        spec = args.ns if seat in ("N", "S") else args.ew
        agents[seat] = make_agent(spec)

    for item in args.seat:
        seat, _, spec = item.partition("=")
        seat = seat.strip().upper()
        if seat not in SEATS:
            raise ValueError(f"bad seat: {seat!r}")
        agents[seat] = make_agent(spec)

    return agents


def report(results, agents):
    done = [r for r in results if not r.error and not r.passed_out]
    errors = [r for r in results if r.error]

    print(f"\nNS = {agents['N'].name} / {agents['S'].name}")
    print(f"EW = {agents['E'].name} / {agents['W'].name}")
    print(f"總局數 {len(results)}  成約 {len(done)}"
          f"  流局 {len(results) - len(done) - len(errors)}  錯誤 {len(errors)}")

    for r in errors[:5]:
        print("  ERROR", r.board_id, r.error)

    if not done:
        return

    scored = [r for r in done if r.ns_score is not None]
    if scored:
        total = sum(r.ns_score for r in scored)
        print(f"NS 總分 {total:+d}   平均每局 {total / len(scored):+.1f}")

    by_declarer = Counter("NS" if r.contract["declarer"] in "NS" else "EW"
                          for r in done)
    print(f"做莊次數 NS {by_declarer['NS']} / EW {by_declarer['EW']}")

    contracts = Counter(f"{r.contract['level']}{r.contract['strain']}"
                        for r in done)
    print("常見合約:", ", ".join(f"{c}x{n}" for c, n in contracts.most_common(6)))


def main():
    p = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__)
    p.add_argument("--deals", type=int, default=5)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--ns", default="rulebased", help="南北的 agent 設定")
    p.add_argument("--ew", default="rulebased", help="東西的 agent 設定")
    p.add_argument("--seat", nargs="*", default=[],
                   help="個別指定座位,例如 N=ben E=rag@http://localhost:8002")
    p.add_argument("--no-play", action="store_true", help="只跑叫牌")
    p.add_argument("--no-mask", action="store_true",
                   help="關閉手牌遮蔽,僅供對照實驗")
    p.add_argument("--log", default=config.DECISION_LOG)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if args.no_mask:
        log.warning("手牌遮蔽已關閉,此批結果不可與正常對局混用")

    agents = build_agents(args)

    # 先確認外部服務活著,並讓 BEN 的模型預先載入
    warmed = set()
    for seat, agent in agents.items():
        if isinstance(agent, BenAgent) and agent.base_url not in warmed:
            log.info("暖機 %s(模型載入需要數秒)", agent.base_url)
            agent.warm_up()
            warmed.add(agent.base_url)
        elif isinstance(agent, RagAgent) and agent.base_url not in warmed:
            info = agent.health()
            log.info("%s health: %s", agent.name, info or "無回應,將使用 fallback")
            warmed.add(agent.base_url)

    table = Table(agents,
                  on_decision=DecisionLogger(args.log),
                  play_out=not args.no_play)

    results = table.run_deals(args.deals, seed=args.seed,
                              masking=not args.no_mask)
    report(results, agents)


if __name__ == "__main__":
    main()
