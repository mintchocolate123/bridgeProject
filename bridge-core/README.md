# bridge-core

橋牌裁判程式庫。規則、狀態機、計分,純邏輯,零相依。

它不碰網路、不開執行緒、不寫檔案,也不呼叫任何人。你告訴它「某個座位
做了某個動作」,它驗證、更新狀態,並回報現在輪到誰、每個人看得到什麼。
平台後端與本機實驗工具共用這一份,所以兩邊的規則、計分、遮蔽不可能
不一致。

## 安裝

在要使用它的專案(平台或 bot)的虛擬環境裡:

```
pip install -e ../bridge-core
```

`-e` 代表可編輯安裝,改了 bridge-core 的程式碼不用重裝。

跑測試:

```
cd bridge-core
pip install -e ".[test]"
pytest
```

## 基本用法

```python
from bridge_core import Deal

deal = Deal.from_board(1)                 # 第 1 副牌:N 發牌,雙方無局,隨機發牌

while not deal.finished:
    turn = deal.to_act()                  # 輪到誰
    request = deal.request_for(turn.actor)
    action = my_agent.decide(request)     # 你的決策邏輯
    events = deal.apply(turn.actor, action)

print(deal.result())
```

## 座位與行動者

`to_act()` 回傳的 `Turn` 有兩個座位欄位:

`seat` 是這一手屬於哪一家:輪到哪一家叫牌,或這張牌從哪一家的手上打出。
`actor` 是誰做決定。

兩者只在一種情況下不同:輪到明手出牌時,`seat` 是明手,`actor` 是莊家。
所有方法的座位參數都是 `actor`。莊家要替明手出牌時,傳入莊家的座位。
明手自己送動作會得到 `NotYourTurn`。

## 介面

| 方法 | 說明 |
|---|---|
| `Deal(hands, dealer, vulnerability, board_id)` | 指定手牌建立。手牌不完整或重複會拋 `ValueError` |
| `Deal.from_board(n, hands=None, rng=None)` | 依牌號決定發牌者與局況,16 副一循環 |
| `to_act()` | 現在輪到誰,結束時回傳 `None` |
| `legal_actions(actor)` | 合法動作清單。不是 actor 的回合時回傳空清單 |
| `apply(actor, action)` | 送出動作,回傳事件清單 |
| `default_action(actor)` | 逾時代打用:叫牌 pass,出牌出最小的合法牌 |
| `view(viewer, reveal_finished=False)` | 某觀看者看到的畫面 |
| `request_for(actor, reveal_all=False)` | 給決策模組的請求 |
| `result()` | 結果,未結束回傳 `None` |
| `to_dict()` / `Deal.from_dict(d)` | 序列化與還原 |

## 視角與遮蔽

`view(viewer)` 的 `viewer` 決定看得到哪幾家的手牌,看不到的是 `None`,
但張數永遠在 `hand_counts` 裡:

`all` 看得到四家,給事後檢討或自己的實驗用。
`public` 只看得到已攤開的明手,給比賽的觀眾用。觀眾若看得到四家,就能
把手牌轉告正在比賽的 bot。
`N` / `E` / `S` / `W` 看得到自己,首引後加上明手。

`reveal_finished=True` 會在這副牌結束後讓所有人看到四家。複式賽兩桌打
同一副牌,另一桌還沒打完之前不要打開。

`request_for(reveal_all=True)` 會把四家手牌放進決策請求,只能用在自己開
的對照實驗。面對外部 bot 絕對不能開。

## 事件

`apply` 回傳這一步產生的事件,每個事件都帶 `board_id` 與 `type`:

| type | 內容 |
|---|---|
| `bid` | `seat`, `bid` |
| `auction_end` | `contract`, `passed_out`;成約時另有 `declarer`, `dummy`, `leader` |
| `card` | `seat`(牌從哪家出), `played_by`(誰決定), `card` |
| `dummy_revealed` | 首引後緊接著出現一次。`seat`, `hand` |
| `trick` | `number`, `winner`, `cards`, `counts` |
| `deal_end` | 與 `result()` 相同的欄位 |

一個動作可能產生多個事件,例如第四家出牌會同時產生 `card`、`trick`,
最後一墩還會加上 `deal_end`。

## 錯誤

所有錯誤都繼承 `RefereeError`。拋出例外時狀態不會改變。

| 例外 | 意思 | 建議對應的 HTTP 碼 |
|---|---|---|
| `NotYourTurn` | 不是這個座位的回合 | 409 |
| `IllegalAction` | 動作不合法,或格式看不懂 | 422 |
| `DealOver` | 這副牌已經結束 | 409 |

## 記法

| 項目 | 格式 |
|---|---|
| 花色 | `C` `D` `H` `S`,無王為 `N` |
| 牌張 | 花色加點數,十寫作 `T`,例如 `SA` `HT` `D9` `C2` |
| 叫品 | `1C` … `7N`,`P`(pass),`X`(加倍),`XX`(再加倍) |
| 座位 | `N` `E` `S` `W` |
| 局況 | `none` `NS` `EW` `both` |

`apply` 對輸入是寬鬆的:`pass`、`3NT`、`dbl`、`rdbl`、`S10`、小寫都會
自動轉成標準記法。輸出一律是標準記法。

手牌與合法牌張清單的順序固定為黑桃、紅心、方塊、梅花,各花色由大到小。
決策邏輯不應該依賴清單順序,例如「有好幾張一樣小的牌時選第一張」,
這種寫法換個排序結果就不同。

`notation` 模組另外提供 PBN 轉換(`hand_to_pbn`、`pbn_to_deal` 等),
比賽匯入牌局時會用到。

## 序列化

`to_dict()` 只存初始發牌與動作歷史,`from_dict()` 從頭重播還原。這樣存
下來的資料不可能自相矛盾,而且重播時每一步都會重新驗證。

## 驗證

測試涵蓋規則、計分、狀態機、遮蔽與序列化,另有 300 副隨機牌局的壓力
測試,檢查每一副牌打滿 52 張不重複、每墩四家各一張、跟牌規則沒被違反、
計分一致、序列化還原後畫面相同。

與先前的 `table.py` 實作用同樣的決策模組跑 500 副牌對照,叫牌、出牌
順序、合約、分數完全一致。
