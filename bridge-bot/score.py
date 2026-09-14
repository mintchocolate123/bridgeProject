"""複式橋牌計分。

BEN 的 /autoplay 會回傳分數,但混合牌桌是由本專案自行主持,所以計分
也要自己算。這是純函式,沒有外部相依,容易驗證。
"""

_TRICK_VALUE = {"C": 20, "D": 20, "H": 30, "S": 30, "N": 30}


def contract_trick_score(level, strain):
    """合約本身的基本墩分(未計加倍)。"""
    score = level * _TRICK_VALUE[strain]
    if strain == "N":
        score += 10          # 無王第一墩 40 分
    return score


def score_contract(level, strain, doubled, vulnerable, tricks):
    """回傳莊家方的得分,負數代表倒墩罰分。

    level       1-7
    strain      C/D/H/S/N
    doubled     "none" / "doubled" / "redoubled"
    vulnerable  莊家方是否有局
    tricks      莊家方實際拿到的墩數
    """
    needed = level + 6
    multiplier = {"none": 1, "doubled": 2, "redoubled": 4}[doubled]

    if tricks < needed:
        return -_penalty(needed - tricks, doubled, vulnerable)

    base = contract_trick_score(level, strain) * multiplier
    score = base

    # 成局或部分分
    if base >= 100:
        score += 500 if vulnerable else 300
    else:
        score += 50

    # 滿貫
    if level == 6:
        score += 750 if vulnerable else 500
    elif level == 7:
        score += 1500 if vulnerable else 1000

    # 被加倍的補償
    if doubled == "doubled":
        score += 50
    elif doubled == "redoubled":
        score += 100

    # 超墩
    overtricks = tricks - needed
    if overtricks:
        if doubled == "none":
            score += overtricks * _TRICK_VALUE[strain]
        else:
            per = (200 if vulnerable else 100) * (2 if doubled == "redoubled" else 1)
            score += overtricks * per

    return score


def _penalty(down, doubled, vulnerable):
    if doubled == "none":
        return down * (100 if vulnerable else 50)

    if vulnerable:
        total = 200 + (down - 1) * 300
    else:
        # 第一墩 100,第二三墩各 200,之後每墩 300
        total = 100
        for i in range(2, down + 1):
            total += 200 if i <= 3 else 300

    return total * (2 if doubled == "redoubled" else 1)


def score_from_contract(contract, tricks, vulnerability="none"):
    """用 GameState 的 contract dict 計分。

    vulnerability 為 "none"/"NS"/"EW"/"both"
    """
    if contract is None:
        return 0

    declarer_side = "NS" if contract["declarer"] in ("N", "S") else "EW"
    vulnerable = vulnerability == "both" or vulnerability == declarer_side

    return score_contract(contract["level"], contract["strain"],
                          contract["doubled"], vulnerable, tricks)


def imps(score_diff):
    """分差換算成 IMP。用於兩組結果的比較。"""
    table = [20, 50, 90, 130, 170, 220, 270, 320, 370, 430, 500, 600, 750,
             900, 1100, 1300, 1500, 1750, 2000, 2250, 2500, 3000, 3500, 4000]
    sign = 1 if score_diff >= 0 else -1
    diff = abs(score_diff)

    result = 0
    for i, threshold in enumerate(table):
        if diff >= threshold:
            result = i + 1
        else:
            break
    return sign * result
