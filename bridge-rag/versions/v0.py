"""v0:骨架。叫牌一律 pass,打牌出第一張合法牌。

用途是確認整條鏈(平台 → bot → RAG 服務)接得通,也是最低的比較基準。
新版本從這個檔案複製一份開始改。
"""

DESCRIPTION = "skeleton: always pass, first legal card"


def setup():
    """服務啟動時呼叫一次。知識庫、向量索引、模型在這裡載入。"""


def choose_bid(request):
    """回傳 (叫品, 解釋, 檢索結果)。

    request 的欄位:
        hand          自己的 13 張牌,例如 ["SA", "SK", "HQ", ...]
        auction       叫牌歷史 [{"seat": "N", "bid": "1C"}, ...]
        legal_bids    合法叫品。回傳值必須在這裡面
        me            自己的座位 N/E/S/W
        dealer        發牌者
        vulnerability none / NS / EW / both

    叫品用標準記法:1C 2H 3N 7S,pass 是 P,加倍 X,再加倍 XX。

    retrieved 是檢索到的片段,建議每筆至少有 doc_id 和 snippet。它會完整
    寫進 bot 的決策紀錄,是之後做消融實驗、證明檢索有效的唯一證據。
    """
    # 1. 把 request 整理成查詢:手牌、牌力、牌型、目前叫牌進度
    # 2. 檢索相關的叫牌知識
    # 3. 交給模型決定叫品
    # 4. 確認結果在 request.legal_bids 裡,不在就退而求其次
    return "P", "skeleton always passes", []


def choose_card(request):
    """回傳 (牌張, 解釋, 檢索結果)。

    request 的欄位:
        hand              這一手要出牌的那家的剩牌
        playing_for       這一手是替誰出。莊家替明手出牌時和 me 不同
        me_hand           自己的剩牌
        dummy             明手的剩牌,首引前是 None
        contract          {"level", "strain", "declarer", "doubled"}
        auction           叫牌歷史
        completed_tricks  已完成的墩
        current_trick     {"leader", "cards": [{"seat", "card"}, ...]}
        legal_cards       合法的牌。回傳值必須在這裡面

    牌張用兩個字元:SA HT D9 C2,十寫作 T。
    """
    return request.legal_cards[0], "skeleton plays first legal card", []
