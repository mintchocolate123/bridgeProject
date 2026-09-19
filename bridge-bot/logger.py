"""決策記錄。

每次決策寫一行 JSON。request 完整保留,之後可以離線重播同一批局面
測試新版 RAG,不需要重新開遊戲。
"""

import json
import os
import threading
import uuid
from datetime import datetime, timezone


class DecisionLogger:
    def __init__(self, path="decisions.jsonl"):
        self.path = path
        self._lock = threading.Lock()

        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)

    def __call__(self, phase, request, response, meta):
        record = {
            "ts": datetime.now(timezone.utc).astimezone().isoformat(),
            "request_id": str(uuid.uuid4()),
            "board_id": request.get("board_id"),
            "phase": phase,
            "masked": request.get("masked"),
            "request": request,
            "response": response,
            "agent": meta.get("agent"),
            "fallback_used": meta.get("fallback_used", False),
            "latency_ms": meta.get("latency_ms"),
            "error": meta.get("error"),
            "room": meta.get("room"),          # 在平台上打的才有
        }
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
