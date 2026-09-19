# bridge-platform

橋牌對局平台。房間、座位、回合、逾時、對外 API、紀錄。規則交給
`bridge-core`,這裡只管「誰、什麼時候、能不能」。

bot 主動連上平台當玩家,平台不會主動連到 bot,所以 bot 在任何網路環境
下都能參賽。API 說明見 `docs/api-design.md`。

## 安裝

需要 Python 3.10 以上,並且 `bridge-core` 放在同一層目錄:

```
_project/
  bridge-core/
  bridge-platform/
```

```
cd bridge-platform
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

`requirements.txt` 會用 `-e ../bridge-core` 把裁判程式庫一起裝進來。

## 啟動

```
python -m bridge_platform
```

要讓別台電腦(例如別隊的 bot)連進來,加上 `--host 0.0.0.0`。
不要直接用 `uvicorn` 啟動:事件串流是長連線,uvicorn 預設關閉時會一直
等它們結束,舊程序關不掉,bot 也會一直掛在舊程序上。`python -m bridge_platform`
關閉時最多等 3 秒就強制斷線,bot 會自動重連到新啟動的平台。

瀏覽器開 http://localhost:8000 就是網站(大廳、觀戰、回放、主辦方)。
網站是 `bridge-ui` build 出來的靜態檔,平台會自動去同一層的
`bridge-ui/dist` 找;還沒 build 的話網站打不開,但 API 照常運作。
build 方式見 `bridge-ui/README.md`。

http://localhost:8000/docs 可以看到所有 API 端點並直接試打。

資料存在 `data/platform.sqlite3`,重啟伺服器後房間與進行中的對局都會
還原。

## 試打一場

開四個終端機,在 `bridge-platform/examples` 底下:

```
python simple_bot.py --boards 2
```

它會印出房號,另外三個終端機用這個房號加入:

```
python simple_bot.py --room K7P2QX
python simple_bot.py --room K7P2QX --stream
python simple_bot.py --room K7P2QX
```

四個座位坐滿就自動開始。打完每個 bot 都會印出每副牌的合約與分數。
打牌途中打開 http://localhost:8000 ,大廳就會出現這個房間,點進去就能
即時觀戰。

## 設定

都用環境變數,沒設定就用預設值。

| 變數 | 預設 | 說明 |
|---|---|---|
| `BRIDGE_DB_PATH` | `data/platform.sqlite3` | 資料庫位置 |
| `BRIDGE_ADMIN_KEY` | 無 | 主辦方金鑰。沒設定就停用所有主辦方端點 |
| `BRIDGE_TURN_TIMEOUT_S` | 300 | 每個回合的時限 |
| `BRIDGE_MAX_CONSECUTIVE_TIMEOUTS` | 2 | 連續逾時幾次整場終止 |
| `BRIDGE_WAITING_EXPIRE_S` | 1800 | 等待中的房間多久沒坐滿就關閉 |
| `BRIDGE_RATE_LIMIT_PER_SECOND` | 20 | 每個 token 每秒請求上限 |
| `BRIDGE_MAX_STREAMS_PER_IP` | 8 | 每個 IP 同時開啟的串流上限 |
| `BRIDGE_CORS_ORIGINS` | `http://localhost:5173,...` | 允許的前端來源,逗號分隔 |
| `BRIDGE_UI_DIST` | `../bridge-ui/dist` | 網站靜態檔的位置 |

PowerShell 設定方式:

```
$env:BRIDGE_ADMIN_KEY = "換成一串夠長的隨機字"
python -m bridge_platform
```

## 測試

```
python -m pytest
```

測試不需要啟動伺服器,時鐘是假的,300 秒的逾時瞬間就能測完。

## 結構

```
bridge_platform/
  room.py      房間的完整生命週期:入座、回合、逾時、換副、結束
  filters.py   依觀看者過濾事件,手牌遮蔽只在這裡做
  manager.py   房號、token 對應、逾時掃描、存檔、喚醒串流
  store.py     SQLite
  api.py       HTTP 端點、驗證、頻率限制、錯誤格式,以及提供網站靜態檔
  config.py    設定
  errors.py    錯誤代碼
  __main__.py  啟動入口(python -m bridge_platform)
examples/
  simple_bot.py  給外部開發者的範例 bot,只相依 requests
docs/
  api-design.md  對外 API 文件
```

`room.py` 不碰 HTTP、資料庫、執行緒,也不自己計時,方便單獨測試。
`api.py` 不含遊戲邏輯。

## 部署前要注意

平台只有一個程序、一個事件迴圈,狀態在記憶體裡,不能開多個 worker
(多個 worker 會各自看到不同的房間)。`python -m bridge_platform` 固定
只開一個。比賽規模的流量一個程序綽綽有餘。

放在 nginx 之類的反向代理後面時,串流端點要關掉緩衝,否則事件會卡住
不送。平台已經送出 `X-Accel-Buffering: no` 標頭,nginx 預設會遵守。

`BRIDGE_ADMIN_KEY` 一定要設定成夠長的隨機字串,並且只給主辦方。
