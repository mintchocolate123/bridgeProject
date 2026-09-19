# bridge-ui

橋牌平台的網站:大廳、即時觀戰、回放、主辦方頁面,中英切換。
Vue 3 + TypeScript + Vite。

前端只透過 HTTP API 和平台溝通,不含任何橋牌規則。牌桌上顯示的所有
東西(誰能看到哪些牌、合約、墩數、分數)都是平台算好給的。觀眾看的是
公開端點,平台本來就只送明手的牌,所以前端就算寫錯也拿不到其他三家。

## 需要

Node.js 20 以上。`bridge-platform` 和 `bridge-ui` 放在同一層:

```
_project/
  bridge-core/
  bridge-platform/
  bridge-ui/
```

## 安裝

```
cd bridge-ui
npm install
```

## 開發

先照 `bridge-platform/README.md` 在 8000 port 啟動平台,再開另一個終端機:

```
npm run dev
```

瀏覽器開 http://localhost:5173 。改程式存檔後畫面會自動更新。
`/api` 開頭的請求會被轉給 localhost:8000,不會有 CORS 問題。

## 部署

```
npm run build
```

產生 `dist/`。平台啟動時會自動找 `../bridge-ui/dist`,之後打開
http://localhost:8000 就是網站,整個網站只有一個程序、一個網址。
改過前端要重新 build,平台不用重啟,重新整理頁面就好。

## 頁面

| 網址 | 內容 |
|---|---|
| `/` | 大廳,房間列表每 3 秒更新,可輸入房號 |
| `/rooms/:code` | 即時牌桌,觀眾視角,只看得到明手 |
| `/rooms/:code/replay` | 房間結束後的回放,四家全開,可逐步播放 |
| `/admin` | 主辦方:輸入金鑰、開房(隨機或指定 PBN)、終止房間 |
| `/admin/rooms/:code` | 主辦方的即時牌桌,四家全開 |

主辦方金鑰只存在該分頁的 sessionStorage,關掉分頁就會忘記。

回放鍵盤操作:← → 一步,空白鍵播放/暫停,Home / End 到頭尾。

## 結構

```
src/
  api/
    types.ts         平台回傳的資料格式
    client.ts        HTTP 請求與事件串流(斷線自動重連)
  composables/
    useLiveRoom.ts   即時追蹤房間:抓狀態 + 接串流
    useAdminKey.ts   主辦方金鑰
  components/
    BridgeTable.vue  牌桌,觀戰、主辦方、回放共用
    HandView.vue     一家的手牌
    PlayingCard.vue  一張牌,純 CSS,不需要圖檔
    AuctionTable.vue 叫牌表
    ResultsTable.vue 成績表
    ...
  pages/             四個頁面
  i18n/              中文與英文字典
  format.ts          記號轉顯示文字
  describe.ts        事件轉成一句話
```

新增文字時兩個字典(`i18n/zh.ts`、`i18n/en.ts`)都要加。

## 之後加真人對局

`BridgeTable` 已經預留 `playable` 參數:傳入 `{ seat, legal }` 後,那一家
的合法牌可以點,點了會發出 `play` 事件。真人頁面要做的是:

1. 用 `POST /api/v1/rooms/join` 入座,拿到玩家 token
2. 用 token 開 `/rooms/{code}/stream`,收到 `your_turn` 就把
   `request.legal_cards`(或 `legal_bids`)交給牌桌
3. 點牌或叫牌後呼叫 `POST /rooms/{code}/action`

平台不用改,真人和 bot 走的是同一套 API。叫牌盒元件還沒做。
