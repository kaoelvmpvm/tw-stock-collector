"""
日期處理工具
"""

from datetime import datetime, timedelta


def is_trading_day(date_str: str) -> bool:
    """
    判斷是否為交易日

    簡單規則：排除週末
    TODO: 未來從 TWSE API 取得完整交易日曆

    Args:
        date_str: 日期字串 YYYY-MM-DD

    Returns:
        bool: 是否為交易日
    """
    date = datetime.strptime(date_str, '%Y-%m-%d')

    # 週末不是交易日
    if date.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return False

    # TODO: 加入國定假日判斷
    # 已知假日列表（需定期更新）
    holidays = {
        # 2025（保留既有項目）
        '2025-01-01',
        '2025-01-27',
        '2025-01-28',
        '2025-01-29',
        '2025-01-30',

        # 2026 TWSE 休市日（平日部分）
        '2026-01-01',
        '2026-02-12',
        '2026-02-13',
        '2026-02-16',
        '2026-02-17',
        '2026-02-18',
        '2026-02-19',
        '2026-02-20',
        '2026-02-27',
        '2026-04-03',
        '2026-04-06',
        '2026-05-01',
        '2026-06-19',
        '2026-07-10',  # 巴威颱風，台股/櫃買休市
        '2026-09-25',
        '2026-09-28',
        '2026-10-09',
        '2026-10-26',
        '2026-12-25',
    }

    if date_str in holidays:
        return False

    return True


def get_latest_trading_day(from_date: str = None) -> str:
    """
    取得最近的交易日

    Args:
        from_date: 起始日期 YYYY-MM-DD (預設: 今天)

    Returns:
        str: 最近的交易日 YYYY-MM-DD
    """
    if from_date is None:
        date = datetime.now()
    else:
        date = datetime.strptime(from_date, '%Y-%m-%d')

    # 往前找最近的交易日（最多找 7 天）
    for i in range(7):
        check_date = date - timedelta(days=i)
        date_str = check_date.strftime('%Y-%m-%d')
        if is_trading_day(date_str):
            return date_str

    # 如果 7 天內都沒有交易日，回傳今天
    return datetime.now().strftime('%Y-%m-%d')


def to_roc_date(date_str: str) -> str:
    """
    轉換為民國曆格式

    Args:
        date_str: 日期字串 YYYY-MM-DD

    Returns:
        str: 民國曆 YYY/MM/DD
    """
    date = datetime.strptime(date_str, '%Y-%m-%d')
    roc_year = date.year - 1911
    return f"{roc_year}/{date.month:02d}/{date.day:02d}"


def get_date_range(start_date: str, end_date: str) -> list:
    """
    產生日期範圍列表

    Args:
        start_date: 起始日期 YYYY-MM-DD
        end_date: 結束日期 YYYY-MM-DD

    Returns:
        list: 日期列表
    """
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')

    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)

    return dates


def get_trading_days_range(start_date: str, end_date: str) -> list:
    """
    產生交易日範圍列表

    Args:
        start_date: 起始日期 YYYY-MM-DD
        end_date: 結束日期 YYYY-MM-DD

    Returns:
        list: 交易日列表
    """
    all_dates = get_date_range(start_date, end_date)
    return [date for date in all_dates if is_trading_day(date)]
