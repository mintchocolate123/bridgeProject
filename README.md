# Bridge RAG

以檢索增強生成(RAG)為核心的橋牌叫牌 AI,以及一套可以讓不同決策模組
互相對打的評估環境。

## 架構

```
bridge-core/       裁判程式庫。規則、計分、牌局狀態機,其他專案共用
bridge-platform/   對局平台。房間、座位、回合、逾時、對外 API、紀錄
bridge-ui/         網站。大廳、即時觀戰、回放、主辦方頁面
bridge-bot/        我們的 bot。只負責決定動作:規則式、BEN、RAG
bridge-rag/        RAG 決策服務。無狀態的 HTTP 服務
BEN (Docker)       外部橋牌引擎,當對照組與部分座位的決策模組
```

平台只負責裁判與對局管理,不知道也不在意某個座位背後是規則、是 BEN、
是哪一版的 RAG,還是別隊的 bot。所有 bot 都用同一套 API 主動連上平台,
網站也只透過 API 讀資料。各部分的說明在各自資料夾的 README。

bot 有兩種用法。`play.py` 讓一個 bot 連上平台坐一個座位,四家對打就開
四個程序,比賽與展示都走這條。`main.py` 是自己跑實驗用的:不經過平台,
直接在本機用 bridge-core 當裁判把四家湊起來打,速度快、可以一次跑幾百
副、可以開 `--no-mask` 做對照組。兩者用的是同一批 agent。

## 環境準備

需要 Python 3.10 以上、Node.js 20 以上、Docker(跑 BEN 用)。五個資料夾
放在同一層:

```
_project/
  bridge-core/
  bridge-platform/
  bridge-ui/
  bridge-bot/
  bridge-rag/
```

每個 Python 專案各有自己的虛擬環境,互不影響。`bridge-core` 不用另外
安裝,其他專案的 requirements 會用 `-e ../bridge-core` 把它一起裝進去;
只有要跑它自己的測試時才需要進去裝。

| 要做的事 | 需要安裝 |
|---|---|
| 開平台、看網站 | bridge-platform、bridge-ui |
| 讓 bot 上平台比賽 | 上面兩個,加 bridge-bot |
| bot 用 RAG | 再加 bridge-rag |
| bot 用 BEN | 再加 BEN |
| 只跑本機實驗(main.py) | bridge-bot,需要時加 bridge-rag / BEN |

### bridge-core(只有要跑它的測試時)

```
cd bridge-core
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e . pytest
python -m pytest
```

### bridge-platform

```
cd bridge-platform
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest
python -m bridge_platform
```

### bridge-ui

裝一次、build 一次,之後平台會自動提供網站。改了前端才需要再 build。

```
cd bridge-ui
npm install
npm run build
```

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

`bridge-core` 要放在同一層,安裝時會一起裝進來。

```
cd bridge-bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest
```

### bridge-rag

獨立的虛擬環境,因為之後會裝向量資料庫與模型等較重的相依套件。

```
cd bridge-rag
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest
python rag_service.py --version v0 --port 8001
```

每個 RAG 版本是 `bridge-rag/versions/` 底下的一個檔案,要跑哪一版、
開在哪個 port 由啟動參數決定。詳見 `bridge-rag/README.md`。

## 在平台上比賽

先啟動平台(見 `bridge-platform/README.md`),然後在 `bridge-bot` 底下:

```
python play.py --agent rag@http://localhost:8001 --boards 4 --seed 7
```

它會開一個房間並印出房號。另外三家各開一個終端機加入:

```
python play.py --agent ben --room K7P2QX
python play.py --agent rag@http://localhost:8002 --room K7P2QX
python play.py --agent ben --room K7P2QX
```

詳細參數見 `bridge-bot/README.md`。

## 本機批次實驗

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
| `--deals N` | 副數 |
| `--seed N` | 亂數種子。同一個種子得到同一批牌,發牌者與局況照標準 16 副循環 |
| `--no-play` | 只跑叫牌,不打牌。快很多 |
| `--log PATH` | 決策紀錄檔(每個決策一行),預設 `runs/decisions.jsonl` |
| `--results PATH` | 結果檔(每副一行,可用 `bridge_core.Deal.from_dict` 重播),預設與 `--log` 同名加 `.results` |
| `--no-mask` | 關閉手牌遮蔽,僅供對照實驗 |
| `-v` | 詳細輸出 |

## 平台與網站

啟動方式見 `bridge-platform/README.md` 與 `bridge-ui/README.md`。
平台啟動後打開 http://localhost:8000 就是網站;bot 連線方式與 API 見
`bridge-platform/docs/api-design.md`,範例 bot 在
`bridge-platform/examples/simple_bot.py`。

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

**平台不是實驗工具。** 它有逾時、頻率限制,是給比賽與展示用的。
要跑數據用 `main.py`。

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

把 `bridge-rag/versions/v0.py` 複製成新的版本檔(例如 `v1.py`),改裡面的
`choose_bid` 與 `choose_card`。`rag_service.py` 是共用的 HTTP 外殼,不用動。

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

所有專案一律使用上述記法,定義在 `bridge-core` 的 `notation.py`。
BEN 自己的參數格式只有 BEN 用得到,轉換放在 `bridge-bot/agents/ben.py`。

## 已知限制

BEN 的推論是單執行緒的,不要對同一個容器併發請求。需要更高吞吐量時
要跑多個容器。同時開多場都用 BEN 時,它們會排隊。

BEN 會檢查發牌者、叫牌歷史長度、座位三者是否吻合,不吻合會回
`Dealer x, auction [...], and seat y do not match!`。

規則式 baseline (`rulebased`) 刻意寫得很簡單,只看大牌點與花色長度,
不代表任何正式叫牌制度。它的用途是確認流程與作為效能下限,不應作為
正式的比較基準。

真人對戰尚未啟用。平台與網站都已預留,做法見 `bridge-ui/README.md`
最後一節。
