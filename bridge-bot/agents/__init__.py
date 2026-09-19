"""由設定字串建立 agent。

設定字串格式為 KIND 或 KIND@URL:
    passing                       全 pass
    rulebased                     簡易規則式 baseline
    ben                           BEN 引擎,預設 config.BEN_URL
    rag                           自建 RAG 服務,預設 config.RAG_URL
    rag@http://localhost:8002     指定網址,用來接不同版本的 RAG

每個 agent 只做一件事:收到局面(request),回傳動作。它不知道自己是在
平台上比賽(play.py)還是在本機跑實驗(main.py)。
"""

import config
from agents.ben import BenAgent
from agents.passing import PassingAgent
from agents.rag import RagAgent
from agents.rulebased import RuleBasedAgent

DEFAULT_URL = {"ben": config.BEN_URL, "rag": config.RAG_URL}

KINDS = {
    "passing": "一律 pass,測流程用",
    "rulebased": "簡易規則式 baseline",
    "ben": "BEN 引擎(需先啟動 Docker 容器)",
    "rag": "自建 RAG 服務(需先啟動 bridge-rag)",
}


def parse_spec(spec):
    """"rag@http://x" -> ("rag", "http://x");未給網址時用預設值。"""
    kind, _, url = spec.partition("@")
    kind = kind.strip().lower()
    if kind not in KINDS:
        raise ValueError(f"unknown agent kind {kind!r}, choose from {', '.join(KINDS)}")
    return kind, (url.strip() or DEFAULT_URL.get(kind))


def make_agent(spec):
    kind, url = parse_spec(spec)
    if kind == "passing":
        return PassingAgent()
    if kind == "rulebased":
        return RuleBasedAgent()
    if kind == "ben":
        return BenAgent(base_url=url)
    if kind == "rag":
        return RagAgent(base_url=url, timeout=config.RAG_TIMEOUT_S, fallback=RuleBasedAgent())
    raise AssertionError(kind)


def warm_up(agents, log=None):
    """讓外部服務先準備好:BEN 預載模型,RAG 確認存活。

    agents 可以是 list 或 dict。同一個網址只處理一次。
    """
    seen = set()
    for agent in (agents.values() if isinstance(agents, dict) else agents):
        url = getattr(agent, "base_url", None)
        if url is None or url in seen:
            continue
        seen.add(url)

        if isinstance(agent, BenAgent):
            if log:
                log.info("暖機 %s(模型載入需要數秒)", url)
            agent.warm_up()
        elif isinstance(agent, RagAgent):
            info = agent.health()
            if log:
                log.info("%s health: %s", agent.name, info or "無回應,將使用備援")
