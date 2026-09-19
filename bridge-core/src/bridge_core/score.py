"""複式橋牌計分與 IMP 換算。"""

from bridge_core.notation import is_vulnerable

_TRICK_VALUE = {"C": 20, "D": 20, "H": 30, "S": 30, "N": 30}

_IMP_TABLE = (20, 50, 90, 130, 170, 220, 270, 320, 370, 430, 500, 600, 750,
              900, 1100, 1300, 1500, 1750, 2000, 2250, 2500, 3000, 3500, 4000)


def contract_trick_score(level, strain):
    """合約本身的基本墩分(未計加倍)。無王第一墩 40 分,之後每墩 30 分。"""
    score = level * _TRICK_VALUE[strain]
    if strain == "N":
        score += 10
    return score


def score_contract(level, strain, doubled, vulnerable, tricks):
    """莊家方的得分,負數代表倒墩罰分。

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

    # 成局獎分或部分分
    score += (500 if vulnerable else 300) if base >= 100 else 50

    # 滿貫獎分
    if level == 6:
        score += 750 if vulnerable else 500
    elif level == 7:
        score += 1500 if vulnerable else 1000

    # 加倍後做成的補償
    score += {"none": 0, "doubled": 50, "redoubled": 100}[doubled]

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


def score_deal(contract, tricks, vulnerability):
    """由合約與莊家方墩數計分,回傳 (莊家方得分, 南北得分)。流局兩者皆為 0。"""
    if contract is None:
        return 0, 0

    declarer = contract["declarer"]
    score = score_contract(contract["level"], contract["strain"],
                           contract["doubled"],
                           is_vulnerable(declarer, vulnerability), tricks)
    ns_score = score if declarer in ("N", "S") else -score
    return score, ns_score


def imps(score_diff):
    """分差換算成 IMP。複式賽比較兩桌同一副牌的結果時使用。"""
    sign = 1 if score_diff >= 0 else -1
    diff = abs(score_diff)

    result = 0
    for i, threshold in enumerate(_IMP_TABLE):
        if diff >= threshold:
            result = i + 1
        else:
            break
    return sign * result
