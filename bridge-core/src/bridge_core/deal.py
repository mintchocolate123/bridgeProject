"""一副牌的裁判狀態機。

Deal 是被動的:它不呼叫任何人,只接受「某座位做了某動作」,驗證、更新
狀態,並回報現在輪到誰、每個人看得到什麼。誰來驅動它、動作從哪裡來,
它不管。本機實驗用迴圈直接呼叫 agent,平台等外部 bot 送動作進來,兩者
共用同一個 Deal。

座位與行動者:
    seat   這一手的牌從哪一家出,或輪到哪一家叫
    actor  由誰做決定。只有一種情況兩者不同:輪到明手出牌時,由莊家決定

所有對外方法的 actor 參數都是指「做決定的人」。莊家要替明手出牌時,
傳入的是莊家的座位,不是明手的。

本類別不是執行緒安全的。多執行緒環境(例如平台)要自己加鎖。
"""

from dataclasses import dataclass

from bridge_core.boards import board_dealer, board_vulnerability, random_hands, validate_hands
from bridge_core.errors import DealOver, IllegalAction, NotYourTurn
from bridge_core.notation import (
    PASS,
    RANKS,
    SEATS,
    SUITS,
    VULNERABILITIES,
    card_suit,
    is_call,
    is_card,
    next_seat,
    partner,
    rank_value,
    side_of,
    sort_hand,
)
from bridge_core.rules import (
    auction_is_over,
    legal_bids,
    legal_cards,
    resolve_contract,
    trick_winner,
)
from bridge_core.score import score_deal

VIEWERS = ("all", "public") + SEATS
SCHEMA_VERSION = "0.1"


@dataclass(frozen=True)
class Turn:
    seat: str       # 這一手屬於哪一家
    actor: str      # 誰做決定
    phase: str      # "bid" 或 "play"

    def to_dict(self):
        return {"seat": self.seat, "actor": self.actor, "phase": self.phase}


class Deal:
    def __init__(self, hands, dealer="N", vulnerability="none", board_id=None):
        validate_hands(hands)
        if dealer not in SEATS:
            raise ValueError(f"bad dealer {dealer!r}")
        if vulnerability not in VULNERABILITIES:
            raise ValueError(f"bad vulnerability {vulnerability!r}")

        self.board_id = board_id
        self.dealer = dealer
        self.vulnerability = vulnerability

        self._initial = {s: sort_hand(hands[s]) for s in SEATS}
        self._hands = {s: list(self._initial[s]) for s in SEATS}

        self._auction = []
        self._contract = None
        self._passed_out = False

        self._tricks = []            # 已完成的墩:{"number","leader","cards","winner"}
        self._current = []           # 本墩已出的牌:{"seat","card"}
        self._leader = None

        self._phase = "bidding"      # bidding / playing / finished
        self._history = []           # [{"actor","action"}],序列化與重播用

    # -- 建立 ---------------------------------------------------------------

    @classmethod
    def new(cls, hands, dealer="N", vulnerability="none", board_id=None):
        return cls(hands, dealer, vulnerability, board_id)

    @classmethod
    def from_board(cls, board_number, hands=None, rng=None, board_id=None):
        """依牌號決定發牌者與局況。沒給手牌就隨機發,給 rng 可以重現。"""
        return cls(hands or random_hands(rng),
                   dealer=board_dealer(board_number),
                   vulnerability=board_vulnerability(board_number),
                   board_id=board_id or f"board-{board_number}")

    # -- 狀態查詢 -----------------------------------------------------------

    @property
    def phase(self):
        return self._phase

    @property
    def finished(self):
        return self._phase == "finished"

    @property
    def auction(self):
        return [dict(e) for e in self._auction]

    @property
    def contract(self):
        return dict(self._contract) if self._contract else None

    @property
    def passed_out(self):
        return self._passed_out

    @property
    def declarer(self):
        return self._contract["declarer"] if self._contract else None

    @property
    def dummy(self):
        return partner(self.declarer) if self._contract else None

    @property
    def dummy_revealed(self):
        """首引打出之後明手才攤牌。"""
        return self._contract is not None and bool(self._tricks or self._current)

    @property
    def initial_hands(self):
        return {s: list(self._initial[s]) for s in SEATS}

    @property
    def history(self):
        return [dict(h) for h in self._history]

    def trick_counts(self):
        ns = sum(1 for t in self._tricks if side_of(t["winner"]) == "NS")
        return {"NS": ns, "EW": len(self._tricks) - ns}

    def _turn_seat(self):
        if self._phase == "bidding":
            return next_seat(self._auction[-1]["seat"]) if self._auction else self.dealer
        if self._phase == "playing":
            return next_seat(self._current[-1]["seat"]) if self._current else self._leader
        return None

    def to_act(self):
        """現在輪到誰。對局結束時回傳 None。"""
        seat = self._turn_seat()
        if seat is None:
            return None
        if self._phase == "bidding":
            return Turn(seat=seat, actor=seat, phase="bid")
        actor = self.declarer if seat == self.dummy else seat
        return Turn(seat=seat, actor=actor, phase="play")

    def legal_actions(self, actor):
        """actor 現在能做的動作。不是 actor 的回合時回傳空清單。"""
        turn = self.to_act()
        if turn is None or actor != turn.actor:
            return []
        if turn.phase == "bid":
            return legal_bids(self._auction, turn.seat)
        return legal_cards(self._hands[turn.seat], self._current)

    # -- 動作 ---------------------------------------------------------------

    def apply(self, actor, action):
        """送出一個動作,回傳這一步產生的事件清單。

        會拋出:DealOver(已結束)、NotYourTurn(不是 actor 的回合)、
        IllegalAction(動作不合法或看不懂)。拋出例外時狀態不會改變。
        """
        if self.finished:
            raise DealOver(f"{self.board_id or 'deal'} is already finished")

        turn = self.to_act()
        if actor != turn.actor:
            raise NotYourTurn(f"{actor} cannot act now, waiting for {turn.actor}")

        action = _normalize(turn.phase, action)
        legal = self.legal_actions(actor)
        if action not in legal:
            raise IllegalAction(f"{action!r} is not legal for {actor} now")

        if turn.phase == "bid":
            events = self._apply_bid(turn.seat, action)
        else:
            events = self._apply_card(turn, action)

        self._history.append({"actor": actor, "action": action})
        return [{"board_id": self.board_id, **e} for e in events]

    def _apply_bid(self, seat, call):
        self._auction.append({"seat": seat, "bid": call})
        events = [{"type": "bid", "seat": seat, "bid": call}]

        if not auction_is_over(self._auction):
            return events

        self._contract = resolve_contract(self._auction)
        if self._contract is None:
            self._passed_out = True
            self._phase = "finished"
            events.append({"type": "auction_end", "contract": None, "passed_out": True})
            events.append({"type": "deal_end", **self.result()})
            return events

        self._phase = "playing"
        self._leader = next_seat(self.declarer)
        events.append({"type": "auction_end", "contract": self.contract,
                       "passed_out": False, "declarer": self.declarer,
                       "dummy": self.dummy, "leader": self._leader})
        return events

    def _apply_card(self, turn, card):
        seat = turn.seat
        self._hands[seat].remove(card)
        self._current.append({"seat": seat, "card": card})
        events = [{"type": "card", "seat": seat, "played_by": turn.actor, "card": card}]

        if not self._tricks and len(self._current) == 1:
            events.append({"type": "dummy_revealed", "seat": self.dummy,
                           "hand": list(self._hands[self.dummy])})

        if len(self._current) == 4:
            winner = trick_winner(self._current, self._contract["strain"])
            trick = {"number": len(self._tricks) + 1, "leader": self._current[0]["seat"],
                     "cards": self._current, "winner": winner}
            self._tricks.append(trick)
            self._current = []
            self._leader = winner
            events.append({"type": "trick", "number": trick["number"],
                           "winner": winner, "cards": [dict(c) for c in trick["cards"]],
                           "counts": self.trick_counts()})

            if len(self._tricks) == 13:
                self._phase = "finished"
                events.append({"type": "deal_end", **self.result()})

        return events

    def default_action(self, actor):
        """逾時代打用的保守動作:叫牌 pass,出牌出最小的合法牌。

        不是 actor 的回合時回傳 None。
        """
        legal = self.legal_actions(actor)
        if not legal:
            return None
        if self.to_act().phase == "bid":
            return PASS
        return min(legal, key=lambda c: (rank_value(c), SUITS.index(card_suit(c))))

    # -- 結果 ---------------------------------------------------------------

    def result(self):
        """結束後的結果。未結束回傳 None。

        tricks 是莊家方的墩數;score 是莊家方得分;ns_score 換算成南北觀點。
        """
        if not self.finished:
            return None
        if self._passed_out:
            return {"contract": None, "passed_out": True, "declarer": None,
                    "tricks": None, "score": 0, "ns_score": 0}

        tricks = self.trick_counts()[side_of(self.declarer)]
        score, ns_score = score_deal(self._contract, tricks, self.vulnerability)
        return {"contract": self.contract, "passed_out": False,
                "declarer": self.declarer, "tricks": tricks,
                "score": score, "ns_score": ns_score}

    # -- 視角 ---------------------------------------------------------------

    def visible_seats(self, viewer, reveal_finished=False):
        """viewer 看得到哪幾家的手牌。

        all      四家全部。觀戰或事後檢討用
        public   只有攤開的明手。比賽時給觀眾,避免觀眾把手牌轉告 bot
        N/E/S/W  自己,加上攤開的明手

        reveal_finished 為真時,結束後所有人都看得到四家。複式賽兩桌打同一
        副牌,另一桌還沒打完前不要打開。
        """
        if viewer not in VIEWERS:
            raise ValueError(f"viewer must be one of {VIEWERS}")

        if viewer == "all" or (reveal_finished and self.finished):
            return set(SEATS)

        seats = set() if viewer == "public" else {viewer}
        if self.dummy_revealed:
            seats.add(self.dummy)
        return seats

    def view(self, viewer="all", reveal_finished=False):
        """某個觀看者看到的牌桌畫面。前端直接拿這個來畫。"""
        visible = self.visible_seats(viewer, reveal_finished)
        turn = self.to_act()

        return {
            "board_id": self.board_id,
            "viewer": viewer,
            "dealer": self.dealer,
            "vulnerability": self.vulnerability,
            "phase": self._phase,
            "hands": {s: (list(self._hands[s]) if s in visible else None) for s in SEATS},
            "hand_counts": {s: len(self._hands[s]) for s in SEATS},
            "auction": self.auction,
            "contract": self.contract,
            "passed_out": self._passed_out,
            "declarer": self.declarer,
            "dummy": self.dummy,
            "dummy_revealed": self.dummy_revealed,
            "turn": turn.to_dict() if turn else None,
            "current_trick": [dict(c) for c in self._current],
            "tricks": [{**t, "cards": [dict(c) for c in t["cards"]]} for t in self._tricks],
            "counts": self.trick_counts(),
            "result": self.result(),
        }

    def request_for(self, actor, reveal_all=False, system="SAYC"):
        """給決策模組的請求,格式與 agent-interface.md 相同。

        不是 actor 的回合時回傳 None。reveal_all 會附上四家手牌,只能用在
        自己開的對照實驗,平台面對外部 bot 時絕不可開啟。
        """
        turn = self.to_act()
        if turn is None or actor != turn.actor:
            return None

        common = {
            "schema_version": SCHEMA_VERSION,
            "board_id": self.board_id,
            "me": actor,
            "dealer": self.dealer,
            "vulnerability": self.vulnerability,
            "masked": not reveal_all,
            "auction": self.auction,
        }
        if reveal_all:
            common["all_hands"] = {s: list(self._hands[s]) for s in SEATS}

        if turn.phase == "bid":
            return {**common, "system": system,
                    "hand": list(self._hands[actor]),
                    "legal_bids": self.legal_actions(actor)}

        dummy_hand = None
        if self.dummy_revealed and self.dummy != turn.seat:
            dummy_hand = list(self._hands[self.dummy])

        return {
            **common,
            "playing_for": turn.seat,
            "me_hand": list(self._hands[actor]),
            "contract": self.contract,
            "hand": list(self._hands[turn.seat]),
            "dummy": dummy_hand,
            "completed_tricks": [{"leader": t["leader"], "winner": t["winner"],
                                  "cards": [dict(c) for c in t["cards"]]}
                                 for t in self._tricks],
            "current_trick": {"leader": self._leader,
                              "cards": [dict(c) for c in self._current]},
            "legal_cards": self.legal_actions(actor),
        }

    # -- 序列化 -------------------------------------------------------------

    def to_dict(self):
        """只存初始發牌與動作歷史,還原時重播。這樣存下來的東西不可能自相矛盾。"""
        return {
            "version": 1,
            "board_id": self.board_id,
            "dealer": self.dealer,
            "vulnerability": self.vulnerability,
            "hands": self.initial_hands,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data):
        deal = cls(data["hands"], data["dealer"], data["vulnerability"], data.get("board_id"))
        for step in data.get("history", []):
            deal.apply(step["actor"], step["action"])
        return deal

    def copy(self):
        return Deal.from_dict(self.to_dict())


def _normalize(phase, action):
    """把外部送來的動作轉成標準記法。看不懂就拋 IllegalAction。

    接受 PASS / 3NT / S10 / sa 這類常見寫法,轉成 P / 3N / ST / SA。
    """
    if not isinstance(action, str):
        raise IllegalAction(f"action must be a string, got {type(action).__name__}")

    text = action.strip().upper()

    if phase == "bid":
        text = {"PASS": "P", "DBL": "X", "RDBL": "XX"}.get(text, text)
        if text.endswith("NT"):
            text = text[:-1]
        if not is_call(text):
            raise IllegalAction(f"cannot understand call {action!r}")
        return text

    if len(text) == 3 and text[1:] == "10":
        text = text[0] + "T"
    if not is_card(text) or text[1] not in RANKS:
        raise IllegalAction(f"cannot understand card {action!r}")
    return text
