#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Official Public Holidays of the Republic of Belarus.
Provides deterministic holiday calculation, Easter & Radunitsa calculation,
and weekly holiday detection for academic timetable optimization.
Reference: Decree of the President of Belarus No. 157 and Art. 147 of the Labour Code.
"""

import datetime
from typing import Dict, List, Optional, Tuple, Union


def orthodox_easter(year: int) -> datetime.date:
    """
    Computes Orthodox Easter (Пасха) using Meeus's Julian algorithm
    converted to Gregorian calendar (+13 days for 1900-2099).
    """
    a = year % 4
    b = year % 7
    c = year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    day = ((d + e + 114) % 31) + 1
    julian_date = datetime.date(year, month, day)
    return julian_date + datetime.timedelta(days=13)


def get_radunitsa(year: int) -> datetime.date:
    """Computes Radunitsa (Радуница) — Tuesday, 9 days after Orthodox Easter."""
    return orthodox_easter(year) + datetime.timedelta(days=9)


def get_belarus_holidays(year: int) -> Dict[datetime.date, str]:
    """
    Returns all non-working public holidays in the Republic of Belarus for a given year.
    1. 1 и 2 января — Новый год
    2. 7 января — Рождество Христово (православное)
    3. 8 марта — День женщин
    4. Радуница (по календарю православной конфессии — 9-й день после Пасхи)
    5. 1 мая — Праздник труда
    6. 9 мая — День Победы
    7. 3 июля — День Независимости Республики Беларусь (День Республики)
    8. 7 ноября — День Октябрьской революции
    9. 25 декабря — Рождество Христово (католическое)
    """
    holidays: Dict[datetime.date, str] = {
        datetime.date(year, 1, 1): "Новый год (день 1)",
        datetime.date(year, 1, 2): "Новый год (день 2)",
        datetime.date(year, 1, 7): "Рождество Христово (православное)",
        datetime.date(year, 3, 8): "День женщин",
        datetime.date(year, 5, 1): "Праздник труда",
        datetime.date(year, 5, 9): "День Победы",
        datetime.date(year, 7, 3): "День Независимости Республики Беларусь (День Республики)",
        datetime.date(year, 11, 7): "День Октябрьской революции",
        datetime.date(year, 12, 25): "Рождество Христово (католическое)",
    }
    holidays[get_radunitsa(year)] = "Радуница"
    return holidays


def parse_date(val: Union[str, datetime.date]) -> datetime.date:
    """Parses date from string (YYYY-MM-DD or DD.MM.YYYY) or returns datetime.date."""
    if isinstance(val, datetime.date):
        return val
    val = val.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(val, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Unsupported date format: {val!r}")


def is_belarus_holiday(d: Union[str, datetime.date]) -> Tuple[bool, Optional[str]]:
    """Checks whether a specific calendar date is a public holiday in Belarus."""
    date_obj = parse_date(d)
    year_holidays = get_belarus_holidays(date_obj.year)
    if date_obj in year_holidays:
        return True, year_holidays[date_obj]
    return False, None


def get_week_holidays(
    week_start_date: Union[str, datetime.date]
) -> Dict[int, str]:
    """
    Given a week starting date (Monday), checks which academic days (0..5: Mon..Sat)
    are public holidays in Belarus.
    Returns mapping: day_index (0..5) -> holiday_name.
    """
    start = parse_date(week_start_date)
    # If not Monday, align to Monday of that week
    start = start - datetime.timedelta(days=start.weekday())

    holidays_in_week: Dict[int, str] = {}
    for day_idx in range(6):  # 0..5 (Mon..Sat)
        curr_date = start + datetime.timedelta(days=day_idx)
        is_hol, hol_name = is_belarus_holiday(curr_date)
        if is_hol and hol_name:
            holidays_in_week[day_idx] = f"{hol_name} ({curr_date.strftime('%d.%m.%Y')})"

    return holidays_in_week
