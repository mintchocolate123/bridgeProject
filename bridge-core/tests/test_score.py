from bridge_core.boards import board_dealer, board_vulnerability
from bridge_core.score import imps, score_contract, score_deal


def test_made_contracts():
    assert score_contract(4, "S", "none", False, 10) == 420
    assert score_contract(4, "H", "none", False, 10) == 420
    assert score_contract(4, "S", "none", True, 10) == 620
    assert score_contract(3, "N", "none", False, 9) == 400
    assert score_contract(3, "N", "none", True, 9) == 600
    assert score_contract(1, "C", "none", False, 7) == 70
    assert score_contract(2, "H", "none", False, 9) == 140
    assert score_contract(5, "D", "none", False, 11) == 400


def test_slams():
    assert score_contract(6, "S", "none", False, 12) == 980
    assert score_contract(6, "S", "none", True, 12) == 1430
    assert score_contract(7, "N", "none", True, 13) == 2220
    assert score_contract(7, "N", "none", False, 13) == 1520


def test_doubled_made():
    assert score_contract(3, "N", "doubled", False, 9) == 550
    assert score_contract(1, "S", "doubled", False, 8) == 260
    assert score_contract(4, "S", "redoubled", False, 10) == 880
    # 2C 加倍有局超一:基本 40x2=80(未成局)+ 部分分 50 + 加倍做成 50 + 超墩 200
    assert score_contract(2, "C", "doubled", True, 9) == 380


def test_undertricks():
    assert score_contract(4, "S", "none", False, 9) == -50
    assert score_contract(4, "S", "none", True, 9) == -100
    assert score_contract(4, "S", "none", False, 7) == -150
    assert score_contract(4, "S", "doubled", False, 9) == -100
    assert score_contract(4, "S", "doubled", False, 8) == -300
    assert score_contract(4, "S", "doubled", False, 7) == -500
    assert score_contract(4, "S", "doubled", False, 6) == -800
    assert score_contract(4, "S", "doubled", True, 9) == -200
    assert score_contract(4, "S", "doubled", True, 7) == -800
    assert score_contract(4, "S", "redoubled", False, 9) == -200


def test_score_deal_sides():
    c = {"level": 4, "strain": "S", "declarer": "N", "doubled": "none"}
    assert score_deal(c, 10, "none") == (420, 420)
    assert score_deal(c, 10, "NS") == (620, 620)
    assert score_deal(c, 10, "EW") == (420, 420)
    c = {"level": 4, "strain": "S", "declarer": "E", "doubled": "none"}
    assert score_deal(c, 10, "EW") == (620, -620)
    assert score_deal(None, None, "both") == (0, 0)


def test_imps():
    assert imps(0) == 0 and imps(10) == 0 and imps(20) == 1
    assert imps(420) == 9 and imps(-420) == -9
    assert imps(4000) == 24 and imps(9999) == 24


def test_board_cycle():
    assert [board_dealer(n) for n in (1, 2, 3, 4, 5)] == ["N", "E", "S", "W", "N"]
    assert [board_vulnerability(n) for n in range(1, 17)] == [
        "none", "NS", "EW", "both", "NS", "EW", "both", "none",
        "EW", "both", "none", "NS", "both", "none", "NS", "EW"]
    assert board_vulnerability(17) == "none"
