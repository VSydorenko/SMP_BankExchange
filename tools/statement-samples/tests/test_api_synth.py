# -*- coding: utf-8 -*-
"""Сторож синтетичних записів: у записі немає заголовків запиту й токеноподібних значень. Решта перевірок синтезатора
(форма, детермінованість, покриття, відступи оракула) прибрана як не ключова; інструмент дає записи для еталонів Т1."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import synth as S

ALL = S.all_scenarios()


class Shape(unittest.TestCase):
    def test_no_token_like_or_header_leak(self):
        for s in ALL:
            for ex in s.recording().exchanges:
                self.assertNotIn('headers', ex['request'])
                self.assertNotIn('token', json.dumps(ex['request']).lower())


if __name__ == '__main__':
    unittest.main()
