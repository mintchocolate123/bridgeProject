# Bridge RAG

以檢索增強生成(RAG)為核心的橋牌叫牌 AI,以及一套可以讓不同決策模組
互相對打的評估環境。

## 架構

```
bridge-bot/        對局協調者。發牌、管輪次、判合法性、計分、寫紀錄
bridge-rag/        RAG 決策服務。無狀態的 HTTP 服務
BEN (Docker)       外部橋牌引擎,當對照組與部分座位的決策模組
```

四個座位各自綁一個決策模組,可以任意混搭。協調者不知道也不在意某個
座位背後是規則、是 BEN、還是哪一版的 RAG——它只負責問「輪到你了,
你要做什麼」。

所有跨程序的通訊都是 HTTP,沒有長連線,沒有狀態同步。

## 環境準備

### BEN(Docker)

第一次建立容器:

```
docker run -d --name ben -p 8080:8080 -p 4443:4443 -p 8085:8085 ghcr.io/lorserker/ben
```

之後開關:

```
docker start ben
docker stop ben
docker ps            # 確認是否在跑
docker logs ben      # 看輸出
```

確認 API 活著:

```
Invoke-RestMethod "http://localhost:8085/bid?hand=AK97543.K.T3.AK7&seat=N&dealer=N&vul=&ctx="
```

容器重啟後模型要重新載入,第一次請求會慢 10~40 秒,這是正常的。

### bridge-bot

```
cd bridge-bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### bridge-rag

獨立的虛擬環境,因為之後會裝向量資料庫與模型等較重的相依套件。

```
cd bridge-rag
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn rag_service:app --port 8001
```

## 跑對局

在 `bridge-bot` 底下,虛擬環境啟用後執行。

```
python main.py --deals 10
```

四家都用內建的規則式 baseline,不需要任何外部服務,用來確認流程正常。

### 指定各家的決策模組

`--ns` 與 `--ew` 以搭檔為單位設定,格式是 `KIND` 或 `KIND@URL`:

| KIND | 說明 | 預設網址 |
|---|---|---|
| `passing` | 一律 pass,測流程用 | — |
| `rulebased` | 12 點開叫的簡易 baseline | — |
| `ben` | BEN 引擎 | http://localhost:8085 |
| `rag` | 自建的 RAG 服務 | http://localhost:8001 |

```
python main.py --deals 50 --ew ben                 baseline 對 BEN
python main.py --deals 50 --ns rag --ew ben        RAG 對 BEN
python main.py --deals 50 --ns rag@http://localhost:8001 \
                          --ew rag@http://localhost:8002
                                                   兩個版本的 RAG 互打
```

需要個別指定座位時用 `--seat`,會覆蓋 `--ns` / `--ew`:

```
python main.py --seat N=rag@http://localhost:8001 E=ben
```

### 常用參數

| 參數 | 說明 |
|---|---|
| `--deals N` | 局數 |
| `--seed N` | 亂數種子。同一個種子得到同一批牌 |
| `--no-play` | 只跑叫牌,不打牌。快很多 |
| `--log PATH` | 紀錄檔路徑,目錄會自動建立 |
| `--no-mask` | 關閉手牌遮蔽,僅供對照實驗 |
| `-v` | 詳細輸出 |

## 實驗紀律

**同一批牌才能比較。** 不同設定要用同一個 `--seed`,否則比較的是運氣
不是能力。

```
python main.py --deals 100 --seed 1 --ew ben --log runs/base-vs-ben.jsonl
python main.py --deals 100 --seed 1 --ns rag --ew ben --log runs/rag-vs-ben.jsonl
```

**每批實驗分開存檔。** `--log` 指定不同路徑,不要全部堆在同一個檔案。

**只跑叫牌時速度快很多。** 打牌階段 BEN 每張牌都要跑模擬,一局可能數
十秒;只跑叫牌的話一局約數秒。評估叫牌品質時用 `--no-play`。

**遮蔽關閉的資料要隔離。** `--no-mask` 會讓決策模組看到四家手牌,那是
理論上限的對照組,結果絕不可與正常對局混在一起分析。

## 決策紀錄

每個決策寫一行 JSON 到紀錄檔,包含:

- `request` 當下的完整局面,可用於離線重播測試新版 RAG
- `response` 決策結果、解釋、檢索到的內容
- `agent` 哪一個決策模組做的,不同版本的 RAG 會有不同標記
- `fallback_used` 是否因服務失效而改用備援,分析時要排除這些
- `latency_ms` 耗時

查看最後一筆:

```
Get-Content runs/xxx.jsonl -Tail 1 | ConvertFrom-Json | ConvertTo-Json -Depth 6
```

只看某個模組的決策:

```
Get-Content runs/xxx.jsonl | Where-Object { $_ -match '"agent": "rag' }
```

## 接上自己的 RAG

改 `bridge-rag/rag_service.py` 的 `choose_bid` 與 `choose_card` 兩個函式。

輸入是局面物件,`request.hand` 是自己的 13 張牌,`request.auction` 是
叫牌歷史,`request.legal_bids` 是合法叫品清單。回傳三個值:決策、解釋、
檢索結果。

兩件事必須在這一層做:

**合法性把關。** 回傳值不在 `legal_bids` / `legal_cards` 裡會被判定失敗
並觸發備援,該筆資料就廢了。模型的輸出要自己檢查。

**檢索結果原樣帶出。** `retrieved` 會完整寫進紀錄檔,是日後做消融實驗
(比較開啟與關閉檢索的差異)的唯一依據,不要省略。

## 記法約定

| 項目 | 格式 |
|---|---|
| 花色 | `C` `D` `H` `S` `N`(無王) |
| 牌張 | 花色加點數,十寫作 `T`。`SA` `HT` `D9` `C2` |
| 叫品 | `1C` `3N` `7S` / `P` / `X` / `XX` |
| 座位 | `N` `E` `S` `W` |
| 局況 | `none` `NS` `EW` `both` |

內部一律使用上述記法。與 BEN 的 PBN 格式互轉集中在 `notation.py`,
換平台時只需改動該檔。

## 已知限制

BEN 的推論是單執行緒的,不要對同一個容器併發請求。需要更高吞吐量時
要跑多個容器。

BEN 會檢查發牌者、叫牌歷史長度、座位三者是否吻合,不吻合會回
`Dealer x, auction [...], and seat y do not match!`。

規則式 baseline (`rulebased`) 刻意寫得很簡單,只看大牌點與花色長度,
不代表任何正式叫牌制度。它的用途是確認流程與作為效能下限,不應作為
正式的比較基準。