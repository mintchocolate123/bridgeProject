# bridge-rag

RAG 決策服務。收到局面,回傳叫品或牌張,附上解釋與檢索內容。

服務不知道平台、房間、回合的存在。bridge-bot 的 `RagAgent` 會把平台給
的局面原封不動 POST 過來,拿到動作後自己檢查合法性、送回平台。

```
平台 ──局面──▶ bridge-bot(play.py / main.py) ──POST /decide/bid──▶ rag_service.py ──▶ versions/v1.py
```

## 安裝

`bridge-core` 放在同一層:

```
cd bridge-rag
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest
```

## 啟動

選一個版本、給一個 port:

```
python rag_service.py --version v0 --port 8001
```

多個版本同時跑就開多個程序,各用一個 port:

```
python rag_service.py --version v1 --port 8001
python rag_service.py --version v2 --port 8002
```

bot 用網址選要接哪一個:

```
python play.py --agent rag@http://localhost:8002 --room K7P2QX       (在 bridge-bot 底下)
python main.py --ns rag@http://localhost:8001 --ew rag@http://localhost:8002
```

bot 啟動時會問服務是哪個版本,決策紀錄與網站上的名稱都會寫成
`rag:v2` 這樣,所以 port 怎麼分配都不影響分析。

## 新增版本

1. 把 `versions/v0.py` 複製成 `versions/v1.py`(檔名必須是 v 加數字開頭)
2. 改 `DESCRIPTION`,寫一句這一版和上一版差在哪
3. 實作 `choose_bid` 和 `choose_card`,各回傳 `(動作, 解釋, 檢索結果)`
4. 需要載入知識庫、向量索引、模型的話寫在 `setup()`,啟動時只跑一次

**舊版本不要改也不要刪。** 比較實驗要拿新版和舊版在同一批牌上對打,
舊版必須能原封不動地跑起來。要改就複製成新檔案。知識庫資料也一樣,
被某一版用過的就不要直接覆蓋。

版本檔之間可以共用程式,例如把手牌特徵的計算放在 `versions/common.py`。
但要注意:改了共用的程式,舊版本的行為也會跟著變。

## 回傳值的兩個要求

**合法。** 回傳值不在 `legal_bids` / `legal_cards` 裡,服務會回 422,
bot 改用規則式的備援動作,並在紀錄裡標記 `fallback_used`。那一筆資料就
不能拿來評估 RAG 了,所以模型的輸出要在版本檔裡自己檢查、修正。

**檢索結果原樣帶出。** `retrieved` 會完整寫進 bot 的決策紀錄,是之後做
消融實驗(比較開啟與關閉檢索)的唯一依據。每筆建議至少有 `doc_id` 和
`snippet`。

## 時間

平台每個回合給 300 秒,bot 預設最多等 240 秒(`play.py --budget`),超過就
改用備援動作。本機實驗(`main.py`)最多等 600 秒(bridge-bot 的
`config.RAG_TIMEOUT_S`),超過同樣改用備援並記在紀錄裡。

## 結構

```
rag_service.py     HTTP 外殼,所有版本共用。只負責收發與合法性檢查
versions/
  __init__.py      依名稱載入版本
  v0.py            骨架:永遠 pass,出第一張合法牌。新版本從這裡複製
knowledge/         知識庫原始資料
tests/
```
