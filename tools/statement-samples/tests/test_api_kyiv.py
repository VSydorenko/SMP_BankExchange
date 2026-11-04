# -*- coding: utf-8 -*-
"""Київський місцевий час оракула (`apilib/kyiv.py`) проти векторів, ВИМІРЯНИХ платформою 1С у задачі 0 плану 05а
(`МестноеВремя(UTC, "Europe/Kiev")`, 8.3.27.2342; журнал прогонів, «Виміри платформи»). Вектори — літерали, не
обчислення; контроль: зламане правило літнього часу дає червоний."""
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import kyiv

D = datetime
# (UTC, місцевий) — виміряно платформою
TO_LOCAL = [
    (D(2026, 1, 14, 21, 59, 59), D(2026, 1, 14, 23, 59, 59)), (D(2026, 1, 14, 22, 0, 0), D(2026, 1, 15, 0, 0, 0)),
    (D(2026, 1, 14, 22, 30, 0), D(2026, 1, 15, 0, 30, 0)), (D(2026, 1, 14, 23, 30, 0), D(2026, 1, 15, 1, 30, 0)),
    (D(2026, 7, 14, 20, 59, 59), D(2026, 7, 14, 23, 59, 59)), (D(2026, 7, 14, 21, 0, 0), D(2026, 7, 15, 0, 0, 0)),
    (D(2026, 7, 14, 21, 30, 0), D(2026, 7, 15, 0, 30, 0)), (D(2026, 7, 14, 22, 30, 0), D(2026, 7, 15, 1, 30, 0)),
    (D(2026, 3, 29, 0, 59, 59), D(2026, 3, 29, 2, 59, 59)), (D(2026, 3, 29, 1, 0, 0), D(2026, 3, 29, 4, 0, 0)),
    (D(2026, 3, 28, 22, 0, 0), D(2026, 3, 29, 0, 0, 0)), (D(2026, 3, 29, 21, 0, 0), D(2026, 3, 30, 0, 0, 0)),
    (D(2026, 10, 25, 0, 59, 59), D(2026, 10, 25, 3, 59, 59)), (D(2026, 10, 25, 1, 0, 0), D(2026, 10, 25, 3, 0, 0)),
    (D(2026, 10, 25, 0, 30, 0), D(2026, 10, 25, 3, 30, 0)), (D(2026, 10, 25, 1, 30, 0), D(2026, 10, 25, 3, 30, 0)),
    (D(2026, 10, 24, 21, 0, 0), D(2026, 10, 25, 0, 0, 0)), (D(2026, 10, 25, 22, 0, 0), D(2026, 10, 26, 0, 0, 0)),
]
# місцевий -> UTC (`УниверсальноеВремя`, виміряно): повторювана година — друге (зимове) входження, відсутня — зимове зміщення
TO_UTC = [(D(2026, 10, 25, 3, 30), D(2026, 10, 25, 1, 30)), (D(2026, 3, 29, 3, 30), D(2026, 3, 29, 1, 30)),
          (D(2026, 3, 29, 2, 30), D(2026, 3, 29, 0, 30))]
DAY_HOURS = [(D(2026, 3, 29), 23), (D(2026, 10, 25), 25), (D(2026, 1, 15), 24), (D(2026, 7, 15), 24)]


def vector_failures(mod=kyiv):
    bad = []
    for u, loc in TO_LOCAL:
        if mod.to_local(u) != loc:
            bad.append(('to_local', u))
    for loc, u in TO_UTC:
        if mod.to_utc(loc) != u:
            bad.append(('to_utc', loc))
    for d, h in DAY_HOURS:
        if mod.day_length_hours(d) != h:
            bad.append(('day', d))
    return bad


class KyivVectors(unittest.TestCase):
    def test_platform_vectors(self):
        self.assertEqual(vector_failures(), [])

    def test_control_can_fail(self):
        # правило «остання неділя» зламано на «перша неділя»: вектори мусять це побачити
        orig = kyiv._last_sunday
        try:
            kyiv._last_sunday = lambda y, m: next(d for d in (D(y, m, i) for i in range(1, 8)) if d.weekday() == 6)
            self.assertNotEqual(vector_failures(), [])
        finally:
            kyiv._last_sunday = orig
        self.assertEqual(vector_failures(), [])

    def test_unix_roundtrip_outside_ambiguity(self):
        for u in (D(2026, 1, 1), D(2026, 6, 1, 12), D(2026, 12, 31, 23, 59)):
            self.assertEqual(kyiv.to_utc(kyiv.to_local(u)), u)

    def test_zoneinfo_agrees_when_available(self):
        try:
            import zoneinfo
            zi = zoneinfo.ZoneInfo('Europe/Kiev')
        except Exception:
            self.skipTest('база часових поясів недоступна (Windows без tzdata)')
        from datetime import timezone, timedelta
        t = D(2026, 1, 1)
        while t < D(2027, 1, 1):
            want = t.replace(tzinfo=timezone.utc).astimezone(zi).replace(tzinfo=None)
            self.assertEqual(kyiv.to_local(t), want, t)
            t += timedelta(minutes=37)


if __name__ == '__main__':
    unittest.main()
