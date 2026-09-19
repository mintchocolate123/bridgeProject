"""預設值。都可以用命令列參數覆蓋。"""

PLATFORM_URL = "http://localhost:8000"
BEN_URL = "http://localhost:8085"
RAG_URL = "http://localhost:8001"

# 平台每個回合給 300 秒。留 60 秒給網路與備援,agent 超過這個時間就改用備援動作
TURN_BUDGET_S = 240

# 呼叫 RAG 服務的連線逾時。模型可能要想很久,這裡給寬一點;
# 在平台上比賽時真正的上限是 TURN_BUDGET_S
RAG_TIMEOUT_S = 600

DECISION_LOG = "runs/decisions.jsonl"
