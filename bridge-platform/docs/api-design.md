# 橋牌平台 API v1

外部 bot 與網站前端如何與平台溝通。

平台是裁判與對局管理者,規則由 `bridge-core` 執行。bot 是玩家,主動連上
平台;平台不會主動連到 bot。所有端點都在 `/api/v1` 底下。

範例程式:`examples/simple_bot.py`,只相依 `requests`,把 `decide()` 換成
自己的邏輯就能上場。

---

## 1. 概念

**房間(room)** 一張牌桌,四個座位。每個房間有一組六碼房號,例如
`K7P2QX`,不分大小寫。一個房間依序打若干副牌,牌號決定發牌者與局況
(16 副一循環)。

**座位(seat)** `N` `E` `S` `W`。一個座位坐一個玩家。

**玩家 token** 坐進座位時由平台發給該玩家,只屬於這個房間的這個座位。
之後所有動作都要帶著它。房號是公開的,token 是祕密。

**回合(turn)** 平台等某個座位做決定的一次機會。每個回合有唯一的
`turn_id` 與截止時間。

### 房間狀態

```
waiting ──四個座位坐滿──> playing ──所有牌打完──> finished
   │                        │
   └──等待逾時──> expired    └──連續逾時 2 次──> aborted
```

| 狀態 | 說明 |
|---|---|
| `waiting` | 等人入座。座位坐滿自動開始 |
| `playing` | 對局中 |
| `finished` | 全部牌打完 |
| `aborted` | 有座位連續逾時 2 次,或主辦方中止 |
| `expired` | 等待超過 30 分鐘沒坐滿,自動關閉 |

---

## 2. 加入房間

```
POST /api/v1/rooms/join
```

**不帶房號**:開一個新房間並坐進去,拿到房號後分享給其他 bot。
**帶房號**:加入該房間。

```json
{
  "room_code": "K7P2QX",
  "seat": "E",
  "name": "my-rag-bot v3"
}
```

| 欄位 | 必填 | 說明 |
|---|---|---|
| `name` | 是 | 顯示名稱,1 到 40 字 |
| `room_code` | 否 | 沒給就開新房間 |
| `seat` | 否 | 指定座位。沒給就依 N、E、S、W 順序分配第一個空位 |
| `options` | 否 | 只在開新房間時有效,見下表 |

開房選項:

| 欄位 | 預設 | 說明 |
|---|---|---|
| `boards` | 4 | 要打幾副牌,1 到 32 |
| `seed` | 隨機產生 | 發牌亂數種子。同一個種子得到同一批牌。沒給的話平台會產生一個並記在房間資料裡,之後仍可重現 |
| `first_board` | 1 | 起始牌號,決定第一副的發牌者與局況 |

成功回應 `201`:

```json
{
  "room_code": "K7P2QX",
  "seat": "E",
  "player_token": "pt_4f8a1c...",
  "room": { "room_code": "K7P2QX", "status": "waiting",
            "seats": {"N": "bot-a", "E": "my-rag-bot v3", "S": null, "W": null},
            "boards": 4, "board": null }
}
```

`player_token` 只會出現這一次,平台只存它的雜湊值,遺失無法找回。

失敗:

| 狀態碼 | code | 情況 |
|---|---|---|
| 404 | `room_not_found` | 房號不存在 |
| 409 | `seat_taken` | 指定的座位已有人 |
| 409 | `room_full` | 沒有空位 |
| 409 | `room_not_waiting` | 房間已開始或已結束 |
| 422 | `invalid_request` | 座位、名稱或選項格式錯誤 |

### 離開

開始之前可以離開,座位空出來,token 失效:

```
DELETE /api/v1/rooms/{room_code}/seat
Authorization: Bearer <player_token>
```

開始之後不能離開(`409 room_not_waiting`)。bot 若就此消失,會因連續
逾時導致整場終止。

---

## 3. 收到回合通知

兩種方式,都要帶 token。

### 方式一:事件串流

```
GET /api/v1/rooms/{room_code}/stream
Authorization: Bearer <player_token>
```

Server-Sent Events。每則訊息的 `data` 是一個 JSON 事件,`id` 是序號。
斷線重連時帶 `Last-Event-ID` 標頭(或 `?since=序號`),平台從那之後補送。
閒置時每 15 秒送一行註解維持連線。房間結束後送出 `{"type": "stream_end"}`
並關閉。

### 方式二:輪詢

```
GET /api/v1/rooms/{room_code}/state
Authorization: Bearer <player_token>
```

回傳目前畫面。輪到你時 `your_turn` 有值,否則為 `null`。

```json
{
  "seat": "E",
  "room_code": "K7P2QX",
  "status": "playing",
  "board": 2,
  "last_seq": 117,
  "view": { "hands": {"N": null, "E": ["SA", "..."], "S": null, "W": null}, "auction": [], "...": "..." },
  "turn": { "turn_id": "t_000183", "seat": "E", "actor": "E", "phase": "bid", "deadline": "..." },
  "results": [],
  "your_turn": { "turn_id": "t_000183", "...": "..." }
}
```

`view` 的格式與 `bridge-core` 的 `Deal.view()` 相同,看不到的手牌為
`null`,張數在 `hand_counts`。`turn` 是公開資訊,所有人都看得到在等誰。

### your_turn

```json
{
  "type": "your_turn",
  "turn_id": "t_000183",
  "board": 2,
  "phase": "bid",
  "seat": "E",
  "actor": "E",
  "deadline": "2026-09-19T16:05:00+08:00",
  "request": {
    "hand": ["SA", "SQ", "S8", "..."],
    "auction": [{"seat": "N", "bid": "1D"}],
    "legal_bids": ["P", "1H", "1S", "..."],
    "dealer": "N",
    "vulnerability": "none"
  }
}
```

`request` 的內容與 `bridge-core` 的 `Deal.request_for()` 相同。打牌階段
有 `legal_cards`、`contract`、`dummy`、`current_trick`、`completed_tricks`
等欄位。

**明手**:輪到明手出牌時,`your_turn` 送給莊家,`seat` 是明手的座位,
`actor` 是莊家,`request.hand` 是明手的牌,`request.me_hand` 是莊家自己的
牌。明手的玩家不會收到任何 `your_turn`。

**牌張順序**:手牌與合法牌張清單固定為黑桃、紅心、方塊、梅花,各花色
由大到小。決策邏輯不要依賴清單順序。

---

## 4. 送出動作

```
POST /api/v1/rooms/{room_code}/action
Authorization: Bearer <player_token>
```

```json
{ "turn_id": "t_000183", "action": "1S" }
```

`turn_id` 必須是目前這個回合的。這是為了防止過期的動作:bot 在逾時後才
送出答案,平台已經代打並進入下一個回合,如果沒有 `turn_id`,這個遲到的
動作會被誤當成下一回合的答案。

動作接受寬鬆寫法:`pass`、`3NT`、`dbl`、`rdbl`、`S10`、小寫都會轉成
標準記法。

成功 `200`:

```json
{ "accepted": true, "action": "1S", "next_turn_id": null }
```

`action` 是轉成標準記法後的結果。`next_turn_id` 不為 `null` 表示緊接著
又輪到你(例如莊家贏了一墩要再出牌),可以直接拿這個 id 送下一個動作。

失敗:

| 狀態碼 | code | 情況 | 會不會算逾時 |
|---|---|---|---|
| 409 | `stale_turn` | `turn_id` 不是目前回合,通常是已逾時代打 | 不影響 |
| 409 | `not_your_turn` | 不是你的回合 | 不影響 |
| 422 | `illegal_action` | 動作不合法或看不懂 | 不算,截止前可以重送 |
| 422 | `invalid_request` | 欄位缺漏或格式錯誤 | 不算 |
| 409 | `room_not_playing` | 房間不在對局中 | — |
| 401 | `invalid_token` | token 錯誤或不屬於這個房間 | — |

---

## 5. 逾時

每個回合限時 **300 秒**,從 `your_turn` 發出時起算。

時間到還沒有合法動作,平台用保守動作代打:叫牌 pass,出牌出最小的合法
牌。代打的 `bid` / `card` 事件標記 `"auto": true`,所有人都看得到。

每個座位有一個連續逾時計數。逾時加一,自己送出合法動作歸零。**計數達到
2 時整場終止**,房間進入 `aborted`,`ended_reason` 為 `timeout`,
`ended_by_seat` 記錄是哪個座位。第二次逾時不再代打,直接終止。

已打完的牌局結果保留;打到一半的那副不計分,但會存進紀錄並標記
`incomplete`。

送出不合法動作不算逾時,但也不會延長截止時間。

伺服器重啟時,進行中的回合會重新給滿 300 秒,並重送一次 `your_turn`。

---

## 6. 事件

所有事件共同欄位:

| 欄位 | 說明 |
|---|---|
| `seq` | 房間內從 0 開始遞增的序號,即 SSE 的 `id` |
| `type` | 事件種類 |
| `ts` | 時間 |
| `board` | 牌號。房間層級的事件沒有 |

| type | 內容 | 誰收得到 |
|---|---|---|
| `room_update` | `status`、`seats` | 所有人 |
| `board_start` | `board`、`index`、`total`、`dealer`、`vulnerability`、`hands` | 所有人。`hands` 只有自己那家,其他為 `null` |
| `your_turn` | 見第 3 節 | 只有該回合的行動者 |
| `turn` | 與 `your_turn` 相同但沒有 `request` | 行動者以外的所有人 |
| `bid` | `seat`、`bid`、`auto` | 所有人 |
| `auction_end` | `contract`、`passed_out`、`declarer`、`dummy`、`leader`。流局時 `contract` 為 `null` | 所有人 |
| `card` | `seat`(牌從哪家出)、`played_by`(誰決定)、`card`、`auto` | 所有人 |
| `dummy_revealed` | `seat`、`hand`。首引後出現一次 | 所有人 |
| `trick` | `number`、`winner`、`cards`、`counts` | 所有人 |
| `timeout` | `seat`、`turn_id`、`consecutive` | 所有人 |
| `board_end` | `contract`、`declarer`、`tricks`(莊家方)、`score`(莊家方)、`ns_score` | 所有人 |
| `room_end` | `status`、`reason`、`seat`、`results` | 所有人 |

一個動作可能產生好幾個事件。例如第四家出牌會依序產生 `card`、`trick`,
最後一墩再加上 `board_end`,若是最後一副還有 `room_end`。

---

## 7. 觀戰

不需要 token:

```
GET /api/v1/rooms                       房間列表,可用 ?status=playing 篩選
GET /api/v1/rooms/{room_code}           房間資訊與目前畫面(public 視角)
GET /api/v1/rooms/{room_code}/spectate  事件串流(public 視角)
GET /api/v1/rooms/{room_code}/record    完整紀錄,房間結束後才能看
GET /api/v1/rooms/{room_code}/replay/{n}  第 n 副(從 1 開始)每一步的畫面,房間結束後才能看
GET /api/v1/health                      伺服器狀態
```

**public 視角只看得到攤開的明手**,看不到另外三家,也收不到任何
`your_turn`。這是為了比賽公平:觀眾若看得到四家,就能把手牌轉告正在
比賽的 bot。

`record` 在房間結束前回 `409 room_not_ended`。結束後回傳每副牌的初始
發牌、完整的叫牌與出牌歷史(`bridge-core` 的 `Deal.to_dict()` 格式)、
結果,四家手牌全部公開。

`replay/{n}` 把第 n 副牌用 `bridge-core` 從頭重播一次,回傳每一步之後的
畫面(`all` 視角),前端回放直接切換這些畫面,不需要自己懂規則:

```json
{
  "room_code": "K7P2QX", "index": 1, "total": 4, "board": 1, "incomplete": false,
  "frames": [
    {"step": 0, "action": null, "view": { ... 發完牌的樣子 ... }},
    {"step": 1, "action": {"seat": "N", "actor": "N", "phase": "bid", "action": "1C"}, "view": { ... }},
    ...
  ]
}
```

`seat` 是這一步出牌的位置,`actor` 是實際做決定的人,莊家替明手出牌時
兩者不同。`n` 超出範圍回 `404 board_not_found`,房間還沒結束回
`409 room_not_ended`。

之後若要做複式賽(同一副牌在兩桌打),完整紀錄要等兩桌都打完才公開。
這部分待賽制確定後補上。

---

## 8. 主辦方

需要在伺服器設定環境變數 `BRIDGE_ADMIN_KEY`,請求時帶
`Authorization: Bearer <admin_key>`。沒有設定時所有主辦方端點回
`403 admin_disabled`,金鑰錯誤回 `401 invalid_admin_key`。

**開房**,指定牌局或依種子產生。主辦方不佔座位,bot 用房號加入:

```
POST /api/v1/admin/rooms
```

```json
{
  "boards": [
    {"number": 1, "deal": "N:AKQ2.J3.T98.KQ52 ..."},
    {"number": 2, "deal": "N:..."}
  ]
}
```

`deal` 是 PBN 格式。或改用 `{"options": {"boards": 8, "seed": 42}}`。

**完整畫面與串流**(all 視角,看得到四家):

```
GET /api/v1/admin/rooms/{room_code}
GET /api/v1/admin/rooms/{room_code}/stream
```

**中止房間**:

```
POST /api/v1/admin/rooms/{room_code}/abort
{"reason": "..."}
```

---

## 9. 錯誤格式

所有錯誤回應:

```json
{
  "error": {
    "code": "illegal_action",
    "message": "'1C' is not legal for E now"
  }
}
```

`code` 給程式判斷,`message` 給人看,內容可能調整,bot 不要依賴它。

---

## 10. 限制

| 項目 | 限制 |
|---|---|
| 每個 token 的請求頻率 | 每秒 20 次(串流連線不計) |
| 開房與加入 | 每個 IP 每秒 20 次 |
| 每個 IP 同時開啟的串流 | 8 條 |
| 等待中的房間 | 30 分鐘沒坐滿自動關閉 |
| 每個回合 | 300 秒 |
| 每個房間 | 1 到 32 副牌 |

超過頻率限制回 `429 rate_limited`,附 `Retry-After` 標頭(秒),照著等
再重送即可。

以上數值都可以用環境變數調整,見 `README.md`。

---

## 11. 實作備註(不對外)

**狀態保存** 房間狀態(`Room.to_dict()`,token 只存雜湊)與事件存
SQLite。每個改變房間的操作結束時存檔。伺服器重啟時從資料庫還原,進行
中的回合重新計時並重送 `your_turn`。

**並行** 平台跑在單一事件迴圈,所有改變房間的操作都在同一個執行緒依序
執行,送出動作與逾時代打不可能同時發生,不需要鎖。

**逾時** 背景工作每 0.5 秒掃描一次所有房間,處理到期的回合與過期的
等待房間。

**視角過濾** 事件在房間裡保存完整內容,送出時才經過 `filters.py`
依接收者過濾。所有端點都走同一個函式,不各自挑欄位。

**前端** 網站前端用觀戰端點,和外部觀眾相同。之後加真人對戰時,真人
透過同一組 join / stream / action 端點當玩家,不需要另一套 API。

---

## 待確認

複式賽的賽制,等教授確認。
