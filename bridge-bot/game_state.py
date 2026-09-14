"""對局狀態。

這一層只吃已經正規化過的資料(標準記法),不知道任何 Brydz 細節。
它的另一個職責是遮蔽:遊戲 server 會廣播四家手牌,但這裡只允許
讀取規則上看得見的牌,避免決策模組意外作弊。
"""

from notation import PASS, DOUBLE, REDOUBLE, SEATS, is_contract_bid, next_seat, partner, same_side
from rules import auction_is_over, legal_bids, legal_cards


class HiddenInformationError(Exception):
    """試圖讀取規則上看不見的手牌。"""


class GameState:
    def __init__(self, me, board_id=None, dealer="S", vulnerability="none",
                 masking=True):
        self.me = me
        self.board_id = board_id
        self.dealer = dealer
        self.vulnerability = vulnerability

        # masking=False 只供實驗使用:決策模組會看到四家手牌。
        # 這種對局的請求會標記 masked=false,分析時務必據此區隔。
        self.masking = masking

        self._all_hands = {}      # 私有,只能經由 hand_of 讀取
        self.auction = []
        self.turn = dealer

        self.auction_over = False
        self.contract = None      # {"level","strain","declarer","doubled"}
                                  # 流局時叫牌已結束但 contract 仍為 None
        self.completed_tricks = []
        self.current_trick = {"leader": None, "cards": []}

    # -- 發牌 ---------------------------------------------------------------

    def start_deal(self, hands_by_seat, board_id=None, dealer="S"):
        """hands_by_seat: {"N": [...], "E": [...], "S": [...], "W": [...]}"""
        self._all_hands = {s: list(hands_by_seat[s]) for s in SEATS}
        self.board_id = board_id or self.board_id
        self.dealer = dealer
        self.turn = dealer
        self.auction = []
        self.auction_over = False
        self.contract = None
        self.completed_tricks = []
        self.current_trick = {"leader": None, "cards": []}

    # -- 可見性 -------------------------------------------------------------

    @property
    def dummy_seat(self):
        if self.contract is None:
            return None
        return partner(self.contract["declarer"])

    @property
    def dummy_revealed(self):
        """首引打出之後明手才攤牌。"""
        if self.contract is None:
            return False
        return bool(self.completed_tricks) or bool(self.current_trick["cards"])

    def visible_seats(self):
        if not self.masking:
            return set(SEATS)
        seats = {self.me}
        if self.dummy_revealed:
            seats.add(self.dummy_seat)
        return seats

    def full_deal(self):
        """完整發牌,不受 masking 影響。

        僅供記錄與離線重播使用,不得用於決策路徑。
        """
        return {s: list(self._all_hands.get(s, [])) for s in SEATS}

    def hand_of(self, seat):
        if seat not in self.visible_seats():
            raise HiddenInformationError(f"hand of {seat} is not visible to {self.me}")
        return list(self._all_hands[seat])

    # -- 叫牌 ---------------------------------------------------------------

    def record_bid(self, seat, call):
        self.auction.append({"seat": seat, "bid": call})
        self.turn = next_seat(seat)
        if auction_is_over(self.auction):
            self.auction_over = True
            self.contract = self._resolve_contract()
            if self.contract:
                self.turn = next_seat(self.contract["declarer"])
                self.current_trick["leader"] = self.turn

    def _resolve_contract(self):
        final = None
        for entry in reversed(self.auction):
            if is_contract_bid(entry["bid"]):
                final = entry
                break
        if final is None:
            return None            # 四家全 pass,此局不打

        level, strain = int(final["bid"][0]), final["bid"][1]

        doubled = "none"
        for entry in self.auction:
            if is_contract_bid(entry["bid"]):
                doubled = "none"
            elif entry["bid"] == DOUBLE:
                doubled = "doubled"
            elif entry["bid"] == REDOUBLE:
                doubled = "redoubled"

        # 莊家是該方最先叫出這個王牌花色的人
        declarer = None
        for entry in self.auction:
            if is_contract_bid(entry["bid"]) and entry["bid"][1] == strain \
                    and same_side(entry["seat"], final["seat"]):
                declarer = entry["seat"]
                break

        return {"level": level, "strain": strain,
                "declarer": declarer, "doubled": doubled}

    # -- 打牌 ---------------------------------------------------------------

    @property
    def passed_out(self):
        """流局:叫牌結束但無人成約。"""
        return self.auction_over and self.contract is None

    @property
    def deal_over(self):
        """13 墩打完、無牌可出,或流局。"""
        if self.passed_out:
            return True
        if self.contract is None:
            return False
        if len(self.completed_tricks) >= 13:
            return True
        return all(not cards for cards in self._all_hands.values())

    def trick_counts(self):
        """各方贏得的墩數。server 未實作計分,由 bot 自行統計。"""
        ns = sum(1 for t in self.completed_tricks if t["winner"] in ("N", "S"))
        return {"NS": ns, "EW": len(self.completed_tricks) - ns}

    def declarer_result(self):
        """莊家方的成績。正數代表超墩,負數代表倒墩。"""
        if self.contract is None:
            return None
        counts = self.trick_counts()
        side = "NS" if self.contract["declarer"] in ("N", "S") else "EW"
        needed = self.contract["level"] + 6
        return counts[side] - needed

    @property
    def playing_for(self):
        """這一手要為誰選牌。莊家代打明手時與 me 不同。"""
        if self.deal_over:
            return None
        if self.contract is None:
            return self.me

        # 明手不自己打牌,由莊家代打。這個判斷必須排在 turn == me 之前,
        # 否則明手座位的 bot 會與莊家同時出牌。
        if self.me == self.dummy_seat:
            return None

        if self.turn == self.me:
            return self.me
        if self.me == self.contract["declarer"] and self.turn == self.dummy_seat:
            return self.dummy_seat
        return None                # 不是我該動作

    def record_card(self, seat, card):
        """記錄一張打出的牌。重複的事件回傳 False 並忽略。

        同一家在同一墩只會打一張,據此判斷重複廣播。
        """
        if any(e["seat"] == seat for e in self.current_trick["cards"]):
            return False

        if not self.current_trick["cards"]:
            self.current_trick["leader"] = seat

        self.current_trick["cards"].append({"seat": seat, "card": card})
        if card in self._all_hands.get(seat, []):
            self._all_hands[seat].remove(card)

        if len(self.current_trick["cards"]) == 4:
            from rules import trick_winner
            winner = trick_winner(self.current_trick["cards"], self.contract["strain"])
            self.completed_tricks.append({
                "leader": self.current_trick["leader"],
                "cards": list(self.current_trick["cards"]),
                "winner": winner,
            })
            self.current_trick = {"leader": winner, "cards": []}
            self.turn = winner
        else:
            self.turn = next_seat(seat)

        return True

    # -- 產生決策請求 -------------------------------------------------------

    def bid_request(self, system="SAYC"):
        return {
            "schema_version": "0.1",
            "board_id": self.board_id,
            "me": self.me,
            "dealer": self.dealer,
            "vulnerability": self.vulnerability,
            "system": system,
            "masked": self.masking,
            "hand": self.hand_of(self.me),
            "auction": list(self.auction),
            "legal_bids": legal_bids(self.auction, self.me),
            **self._unmasked_extra(),
        }

    def play_request(self):
        """不是自己該動作時回傳 None,不拋例外。

        決策在背景執行緒進行,期間狀態可能前進,這是預期內的情況。
        """
        actor = self.playing_for
        if actor is None:
            return None

        if not self._all_hands.get(actor):
            return None

        dummy = None
        if self.dummy_revealed and self.dummy_seat != actor:
            dummy = self.hand_of(self.dummy_seat)

        hand = self.hand_of(actor)

        return {
            "schema_version": "0.1",
            "board_id": self.board_id,
            "me": self.me,
            "masked": self.masking,
            "playing_for": actor,
            "dealer": self.dealer,
            "vulnerability": self.vulnerability,
            "me_hand": self.hand_of(self.me),
            "contract": dict(self.contract),
            "auction": list(self.auction),
            "hand": hand,
            "dummy": dummy,
            "completed_tricks": list(self.completed_tricks),
            "current_trick": {
                "leader": self.current_trick["leader"],
                "cards": list(self.current_trick["cards"]),
            },
            "legal_cards": legal_cards(hand, self.current_trick["cards"]),
            **self._unmasked_extra(),
        }

    def _unmasked_extra(self):
        if self.masking:
            return {}
        return {"all_hands": self.full_deal()}
