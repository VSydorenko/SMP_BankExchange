# -*- coding: utf-8 -*-
"""Київський місцевий час для оракула. Рахується тут, у Python, без 1С.

Правила — ті самі, що в ЄС (Україна живе за ними): літній час (UTC+3) від останньої неділі березня 01:00 UTC до
останньої неділі жовтня 01:00 UTC, інакше UTC+2. Це вдруге перевірено незалежно: вектори, виміряні платформою
(`МестноеВремя(..., "Europe/Kiev")` у задачі 0 плану 05а), лежать у тестах; збіг із `zoneinfo`, якщо база часових
поясів у системі є (на Windows без пакета tzdata її немає).

Обернене перетворення (місцевий -> UTC) повторює виміряну поведінку `УниверсальноеВремя`:
  * повторювана година (осінь, 03:00-03:59:59) -> друге, зимове входження (03:30 -> 01:30 UTC);
  * відсутня година (весна, 03:00-03:59:59) -> зимове зміщення UTC+2 (03:30 -> 01:30 UTC; 02:30 -> 00:30 UTC).
Ім'я пояса в 8.3.27 — `Europe/Kiev` (`Europe/Kyiv` платформа відхиляє)."""
from datetime import datetime, timedelta

PLATFORM_ZONE = 'Europe/Kiev'
EPOCH = datetime(1970, 1, 1)


def _last_sunday(year, month):
    d = datetime(year, month, 31 if month in (3, 10) else 30)
    while d.weekday() != 6:
        d -= timedelta(days=1)
    return d


def dst_bounds_utc(year):
    """(початок літнього часу, кінець літнього часу) у UTC (naive)."""
    return (_last_sunday(year, 3) + timedelta(hours=1), _last_sunday(year, 10) + timedelta(hours=1))


def offset_hours(utc):
    start, end = dst_bounds_utc(utc.year)
    return 3 if start <= utc < end else 2


def to_local(utc):
    """UTC (naive) -> київський місцевий час (naive)."""
    return utc + timedelta(hours=offset_hours(utc))


def to_utc(local):
    """Місцевий (naive) -> UTC (naive); неоднозначну й відсутню годину див. у шапці модуля."""
    cands = []
    for off in (3, 2):
        u = local - timedelta(hours=off)
        if offset_hours(u) == off:
            cands.append(u)
    if len(cands) == 2:
        return max(cands)      # повторювана година: зимове входження
    if len(cands) == 1:
        return cands[0]
    return local - timedelta(hours=2)   # відсутня година: зимове зміщення


def unix_to_utc(sec):
    return EPOCH + timedelta(seconds=int(sec))


def unix_to_local(sec):
    return to_local(unix_to_utc(sec))


def local_to_unix(local):
    return int((to_utc(local) - EPOCH).total_seconds())


def day_length_hours(day):
    """Тривалість місцевої доби `day` (date або datetime) у годинах: 23, 24 або 25."""
    start = datetime(day.year, day.month, day.day)
    nxt = start + timedelta(days=1)
    return int((to_utc(nxt) - to_utc(start)).total_seconds() // 3600)
