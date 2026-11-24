# -*- coding: utf-8 -*-
"""Синтетика ПУМБ (задача 2a, Step 3): що саме вона покриває і чого НЕ покриває. Усі значення вигадані; форма відповідей -- за swagger і гіпотетична (позначка в кожному записі).
Контролі, що вміють впасти: невиміряне (пагінація, формат дати) оракул ЯВНО відхиляє -- «зеленого» мовчки немає; кожен відступ ПУМБ, що має слід, спрацьовує на синтетиці й
його вимкнення змінює еталон рівно там, де він спрацьовує."""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import common as C, kyiv, recording as R, synth as S, synth_pumb as SP

PUMB = S.pumb_scenarios()


class Coverage(unittest.TestCase):
    def test_requests_follow_the_stated_bounds_hypothesis_and_hold_no_secrets(self):
        for s in PUMB:
            rec = s.recording()
            p = s.params
            moment = p.reading_moment + timedelta(hours=3 if kyiv.offset_hours(p.reading_moment) == 3 else 2)
            searches = [e for e in rec.exchanges if e['request']['path'].endswith('/document/searcher')]
            self.assertTrue(all('pagingRequest' not in json.loads(R.request_body_text(e)) for e in searches), s.sid)       # пагінації немає (Р4); кілька запитів -- лише половини ділення
            for e in rec.exchanges:
                rq = e['request']
                self.assertNotIn('headers', rq)
                self.assertNotIn('authorization', json.dumps(e).lower())
                if rq['path'].endswith('/openid-connect/token'):
                    self.assertTrue(rq['bodyOmitted'], s.sid)                          # тіло автентифікації (пароль-грант) у запис не йде
                    self.assertNotIn('bodyBase64', rq)
                    self.assertNotIn('port', rq)
                else:
                    self.assertEqual(rq['port'], 4103, s.sid)
            for e in rec.exchanges:
                if e['request']['path'].endswith('/openid-connect/token') and e['response']['status'] == 200:
                    body = R.body_json(e)
                    for k, v in body.items():
                        if isinstance(v, str) and k not in ('token_type', 'scope'):
                            self.assertRegex(v, r'^a[a.\-]+$', s.sid)                    # лише маркер тієї ж форми, не значення
            for k, e in enumerate(searches):
                body = json.loads(R.request_body_text(e))
                self.assertEqual(set(body), {'fromDate', 'toDate', 'documentAccounts'}, s.sid)    # без фільтра станів, типу й pagingRequest
                lo = p.period_start.strftime('%d.%m.%Y') + ' 00:00:00'                              # цілі календарні доби, обидві межі включно (D36 п. 11, run2): запасу в секунду немає
                hi = min(p.period_end, moment).strftime('%d.%m.%Y') + ' 23:59:59'
                if k == 0:
                    self.assertEqual((body['fromDate'], body['toDate']), (lo, hi), s.sid)           # перший запит -- увесь період
                else:                                                                              # половини: від 00:00:00 першої до 23:59:59 останньої доби, у днях періоду
                    f, t = C.pumb_date(body['fromDate']), C.pumb_date(body['toDate'])
                    self.assertEqual((f.time(), t.time()), (datetime(2026, 1, 1).time(), datetime(2026, 1, 1, 23, 59, 59).time()), s.sid)
                    self.assertTrue(p.period_start.date() <= f.date() <= t.date() <= p.period_end.date(), s.sid)
                if 'МультиВалюта' not in s.sid:
                    self.assertEqual(body['documentAccounts'], [str(SP.ACCOUNT_ID)])


if __name__ == '__main__':
    unittest.main()
