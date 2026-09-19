"""平台設定。可用環境變數覆蓋。"""

import os


def _int(name, default):
    return int(os.environ.get(name, default))


TURN_TIMEOUT_S = _int("BRIDGE_TURN_TIMEOUT_S", 300)
MAX_CONSECUTIVE_TIMEOUTS = _int("BRIDGE_MAX_CONSECUTIVE_TIMEOUTS", 2)
WAITING_EXPIRE_S = _int("BRIDGE_WAITING_EXPIRE_S", 30 * 60)

DEFAULT_BOARDS = 4
MAX_BOARDS = 32
MAX_NAME_LENGTH = 40

DB_PATH = os.environ.get("BRIDGE_DB_PATH", "data/platform.sqlite3")

# 沒有設定就停用所有 admin 端點
ADMIN_KEY = os.environ.get("BRIDGE_ADMIN_KEY") or None

# 莊家連續替自己和明手出牌時,一個回合就是查詢加送出兩次請求,10 太緊
RATE_LIMIT_PER_SECOND = _int("BRIDGE_RATE_LIMIT_PER_SECOND", 20)
MAX_STREAMS_PER_IP = _int("BRIDGE_MAX_STREAMS_PER_IP", 8)
STREAM_KEEPALIVE_S = 15

CORS_ORIGINS = [o for o in os.environ.get(
    "BRIDGE_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o]

# 前端 build 出來的靜態檔。預設是同一層的 bridge-ui/dist,不存在就只提供 API
UI_DIST = os.environ.get(
    "BRIDGE_UI_DIST",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "bridge-ui", "dist"))
