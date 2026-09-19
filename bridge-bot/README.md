# bridge-bot

我們的 bot。每個 agent 只做一件事:收到局面,回傳動作。規則、輪次、
計分都不在這裡,交給 `bridge-core`(本機實驗)或平台(比賽)。

## 安裝

`bridge-core` 放在同一層:

```
_project/
  bridge-core/
  bridge-bot/
```

```
cd bridge-bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest
```

## agent

用設定字串指定,格式是 `KIND` 或 `KIND@URL`:

| KIND | 說明 | 預設網址 |
|---|---|---|
| `passing` | 一律 pass,測流程用 | — |
| `rulebased` | 12 點開叫的簡易 baseline | — |
| `ben` | BEN 引擎 | http://localhost:8085 |
| `rag` | 自建的 RAG 服務 | http://localhost:8001 |

`rag@http://localhost:8002` 這種寫法可以接不同版本的 RAG。

## 在平台上比賽:play.py

一個程序坐一個座位。四家對打就開四個程序,每個都是獨立連上平台的
玩家,和別隊的 bot 走一模一樣的 API。

```
python play.py --agent rag --boards 4 --seed 7         開新房間,印出房號
python play.py --agent ben --room K7P2QX               加入房間,坐第一個空位
python play.py --agent ben --room K7P2QX --seat W      指定座位
```

| 參數 | 說明 |
|---|---|
| `--agent` | 必填,見上表 |
| `--server` | 平台網址,預設 http://localhost:8000 |
| `--room` | 房號。不給就開新房間 |
| `--seat` | N / E / S / W。不給就坐第一個空位 |
| `--name` | 顯示在網站上的名稱,預設是 agent 名稱 |
| `--boards` `--seed` `--first-board` | 開新房間時的設定 |
| `--budget` | 每個決策最多等幾秒,預設 240 |
| `--log` | 決策紀錄檔,預設 `runs/platform/<房號>-<座位>.jsonl` |

平台每個回合給 300 秒,連續逾時 2 次整場終止。為了不讓一個出問題的
agent 毀掉整場,`play.py` 會保護每一次決策:

agent 丟出例外、回傳不合法的動作、或超過 `--budget` 秒還沒回應時,改用
規則式 baseline 的動作送出,並在決策紀錄標記 `fallback_used`。分析數據時
要把這些排除。

其他會自動處理的事:入座前先替 BEN 暖機;串流斷線自動重連;平台重啟後
接著打(平台會把還沒完成的回合重發一次);被限流時照平台指示等待。
在房間開始前按 Ctrl+C 會讓出座位;開始後按 Ctrl+C,這個座位會逾時。

打完會印出每副牌的結果,程式結束代碼 0 代表正常打完,1 代表房間被終止。

## 本機批次實驗:main.py

不經過平台,直接在這台電腦上用 `bridge-core` 當裁判把四家湊起來打。
沒有逾時、沒有頻率限制,適合一次跑幾百副。

```
python main.py --deals 10                                  四家 baseline
python main.py --deals 50 --ns rag --ew ben                RAG 對 BEN
python main.py --deals 50 --ns rag@http://localhost:8001 --ew rag@http://localhost:8002
python main.py --deals 50 --ns rag --ew ben --no-play      只跑叫牌
python main.py --seat N=rag E=ben                          個別指定座位
```

參數說明見專案根目錄的 README。`main.py` 本身不會替 agent 換動作:
agent 出了不合法的動作,這一副直接記為錯誤。唯一的例外是 `rag`:RAG 服務
沒回應、逾時或回了不合法的動作時,`RagAgent` 會改用規則式的動作並標記
`fallback_used`,這樣一次服務故障不會讓整批實驗停掉。分析時把這些排除。

發牌者與局況照標準 16 副循環(第 1 副北發牌無人有局……)。舊版的
`main.py` 不是這樣排的,而且發牌方式不同,所以同一個 `--seed` 得到的牌
和舊版不一樣,新舊結果不要混在一起比。

## 決策紀錄

兩種用法寫的格式相同,每個決策一行 JSON:

| 欄位 | 內容 |
|---|---|
| `request` | 當下的完整局面,可以離線重播測試新版 RAG |
| `response` | 決策結果、解釋、檢索到的內容 |
| `agent` | 哪一個 agent,不同版本的 RAG 會有不同標記 |
| `fallback_used` | 是否改用了備援動作 |
| `error` | 改用備援的原因 |
| `latency_ms` | 耗時 |
| `room` | 平台房號,本機實驗是 null |

## 結構

```
agents/
  __init__.py    由設定字串建立 agent、暖機
  base.py        介面:decide_bid(request) / decide_play(request)
  passing.py
  rulebased.py
  ben.py         BEN 的 REST API,含 BEN 專用的參數格式轉換
  rag.py         自建 RAG 服務
play.py          連上平台比賽
main.py          本機批次實驗
logger.py        決策紀錄
config.py        預設網址與時間
tests/
```

規則相關的程式(記法、合法叫品與出牌、計分)全部來自 `bridge-core`,
這裡沒有任何一份複本。
