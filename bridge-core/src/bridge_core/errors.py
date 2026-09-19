"""裁判拒絕動作時拋出的例外。

平台把這些對應成 HTTP 錯誤碼回給 bot,所以類型要分清楚:
    NotYourTurn     不是這個座位的回合         -> 409
    IllegalAction   動作不合法,或格式看不懂   -> 422
    DealOver        這副牌已經結束            -> 409
"""


class RefereeError(ValueError):
    """所有裁判錯誤的共同父類別。"""


class NotYourTurn(RefereeError):
    pass


class IllegalAction(RefereeError):
    pass


class DealOver(RefereeError):
    pass
