"""RAG 的各個版本。一個版本一個檔案,啟動服務時選要跑哪一個。

每個版本檔案要提供:

    DESCRIPTION = "一句話說明這一版和上一版差在哪"

    def choose_bid(request):   回傳 (叫品, 解釋, 檢索結果)
    def choose_card(request):  回傳 (牌張, 解釋, 檢索結果)

    def setup():               選用。服務啟動時呼叫一次,用來載入知識庫、
                               向量索引、模型。不要在 choose_bid 裡每次重載

舊版本不要刪也不要改:之後做比較實驗時,要能把舊版原封不動地跑起來。
要改就複製成新檔案。
"""

import importlib
import pkgutil
import re

_NAME = re.compile(r"^v\d+[a-z0-9_]*$")


def available():
    """所有版本名稱,例如 ["v0", "v1"]"""
    return sorted(m.name for m in pkgutil.iter_modules(__path__) if _NAME.match(m.name))


def load(name):
    if name not in available():
        raise ValueError(f"unknown RAG version {name!r}; available: {', '.join(available())}")
    module = importlib.import_module(f"versions.{name}")
    for attr in ("choose_bid", "choose_card"):
        if not callable(getattr(module, attr, None)):
            raise TypeError(f"versions/{name}.py must define {attr}(request)")
    return module
