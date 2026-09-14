"""對局協調者。

取代先前的 socket.io 連線層。四個座位各自綁一個 agent,可以任意混搭
(RAG、BEN、規則式、全 pass)。沒有連線、沒有事件、沒有執行緒——
一個迴圈跑完一局。

BEN 只回答「給我這個狀態,我下一步做什麼」,輪次、贏墩、計分都在這裡。
"""

import logging
import random
import uuid

from game_state import GameState
from notation import RANKS, SEATS, SUITS, next_seat
from rules import auction_is_over
from score import score_from_contract

log = logging.getLogger(__name__)

FULL_DECK = [s + r for s in SUITS for r in RANKS]


def deal_random(rng=None):
    """隨機發牌,回傳 {"N": [...], "E": [...], "S": [...], "W": [...]}"""
    rng = rng or random
    deck = list(FULL_DECK)
    rng.shuffle(deck)
    return {seat: sorted(deck[i * 13:(i + 1) * 13]) for i, seat in enumerate(SEATS)}


class DealResult:
    def __init__(self, board_id, hands, dealer, vulnerability):
        self.board_id = board_id
        self.hands = hands
        self.dealer = dealer
        self.vulnerability = vulnerability
        self.auction = []
        self.contract = None
        self.tricks = None
        self.score = None            # 莊家方得分
        self.ns_score = None
        self.play = []               # 依序的出牌
        self.passed_out = False
        self.error = None

    def summary(self):
        if self.passed_out:
            return f"{self.board_id}: passed out"
        if self.error:
            return f"{self.board_id}: ERROR {self.error}"
        c = self.contract
        doubled = {"none": "", "doubled": "X", "redoubled": "XX"}[c["doubled"]]
        text = (f"{self.board_id}: {c['level']}{c['strain']}{doubled}"
                f" by {c['declarer']}")

        if self.tricks is None:          # --no-play,只跑了叫牌
            return text
        return f"{text}, {self.tricks} tricks, NS {self.ns_score:+d}"


class Table:
    def __init__(self, agents, on_decision=None, play_out=True):
        """agents: {"N": agent, "E": agent, "S": agent, "W": agent}

        play_out=False 時只跑叫牌,不打牌。適合只評估叫牌品質時使用,
        速度快很多,但 tricks 與 score 會是 None。
        """
        self.agents = agents
        self.on_decision = on_decision
        self.play_out = play_out

    # -- 單局 ---------------------------------------------------------------

    def run_deal(self, hands=None, dealer="N", vulnerability="none",
                 board_id=None, masking=True):
        hands = hands or deal_random()
        board_id = board_id or str(uuid.uuid4())[:8]

        result = DealResult(board_id, hands, dealer, vulnerability)

        states = {}
        for seat in SEATS:
            gs = GameState(me=seat, board_id=board_id, dealer=dealer,
                           vulnerability=vulnerability, masking=masking)
            gs.start_deal(hands, board_id=board_id, dealer=dealer)
            states[seat] = gs

        try:
            self._run_auction(states, result)
            if result.contract and self.play_out:
                self._run_play(states, result)
        except Exception as exc:
            log.exception("deal %s failed", board_id)
            result.error = str(exc)

        return result

    def _run_auction(self, states, result):
        turn = result.dealer

        while not auction_is_over(result.auction):
            state = states[turn]
            request = state.bid_request()
            response, meta = self.agents[turn].decide_bid(request)
            call = response["bid"]

            if call not in request["legal_bids"]:
                raise ValueError(f"{turn} made illegal bid {call}")

            self._log("bid", request, response, meta)

            for gs in states.values():
                gs.record_bid(turn, call)
            result.auction.append({"seat": turn, "bid": call})
            turn = next_seat(turn)

        reference = states["N"]
        result.contract = reference.contract
        result.passed_out = reference.passed_out

    def _run_play(self, states, result):
        reference = states["N"]

        while not reference.deal_over:
            turn = reference.turn
            # 明手由莊家代打
            actor = (reference.contract["declarer"]
                     if turn == reference.dummy_seat
                     else turn)

            state = states[actor]
            request = state.play_request()
            if request is None:
                raise ValueError(f"no request for {actor} (turn {turn})")

            response, meta = self.agents[actor].decide_play(request)
            card = response["card"]

            if card not in request["legal_cards"]:
                raise ValueError(f"{actor} played illegal card {card}")

            self._log("play", request, response, meta)

            for gs in states.values():
                gs.record_card(turn, card)
            result.play.append(card)

        counts = reference.trick_counts()
        side = "NS" if result.contract["declarer"] in ("N", "S") else "EW"
        result.tricks = counts[side]
        result.score = score_from_contract(result.contract, result.tricks,
                                           result.vulnerability)
        result.ns_score = result.score if side == "NS" else -result.score

    def _log(self, phase, request, response, meta):
        if self.on_decision:
            self.on_decision(phase, request, response, meta)

    # -- 多局 ---------------------------------------------------------------

    def run_deals(self, n, seed=None, **kwargs):
        rng = random.Random(seed)
        results = []
        for i in range(n):
            hands = deal_random(rng)
            dealer = SEATS[i % 4]
            vulnerability = ("none", "NS", "EW", "both")[(i // 4) % 4]
            r = self.run_deal(hands=hands, dealer=dealer,
                              vulnerability=vulnerability,
                              board_id=f"board-{i + 1}", **kwargs)
            results.append(r)
            log.info("%s", r.summary())
        return results
