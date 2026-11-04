# -*- coding: utf-8 -*-
"""Контроль моделей банку monobank (`apilib/bankmodel.py`): юросіб і ФОП. Юросіб: модель, що реалізує лише виміряне, відтворює справжній запис
`corp_a1_statement_small_limit` на запитах рекордера (to = час межової операції) -- сторінки 10/10/10/3, ті самі операції в тому
самому порядку; зіпсована модель (`to` включний) це відтворення валить. Один тест. Запис -- знеособлений вихід run1 у
гітігнорованій `temp/` (його немає в клонах без прогону), тож без нього тест пропускається."""
import base64
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import bankmodel, readings, recording as R

READING = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'temp', 'api-anon', 'run1', 'readings',
                       'mono-corp', 'ЗапStatementSmallLimit')


READING500 = os.path.join(os.path.dirname(READING), 'ЗапStatementLimit500')


def replay(model, statements):
    """Сторінки моделі на запити рекордера (from, to, limit) -> [сторінка]."""
    return [model.statement(R.statement_window(e)[1], R.statement_window(e)[2], int(dict(R.query_pairs(e))['limit']))
            for e in statements]


class BankModel(unittest.TestCase):
    @unittest.skipUnless(os.path.isdir(READING) and os.path.isdir(READING500), 'немає знеособленого запису run1 (temp/api-anon/run1)')
    def test_model_reproduces_the_recorded_pagination_and_a_broken_model_does_not(self):
        rec = R.Recording.from_dir(READING)
        statements = [e for e in rec.exchanges if R.statement_window(e)]
        recorded = [R.body_json(e) for e in statements]
        self.assertEqual([len(p) for p in recorded], [10, 10, 10, 3])
        pool = [op for page in recorded for op in page]
        self.assertEqual(len({op['id'] for op in pool}), len(pool))               # у запису повторів немає
        self.assertEqual(replay(bankmodel.CorpBank(pool), statements), recorded)    # поле за полем, у тому самому порядку
        self.assertNotEqual(replay(bankmodel.CorpBank(pool, to_inclusive=True), statements), recorded)   # контроль уміє впасти
        # похідний запис «справжні операції, сторінки від моделі» (ЗапStatementLimit500_Модель30): модель лише групує операції --
        # тіла операцій побайтово ті самі, множина id та сама; balances справжнього запису береться як є
        real = R.Recording.from_dir(READING500)
        derived = readings.model_paged_corp(real)
        real_stmt = next(e for e in real.exchanges if R.statement_window(e))
        real_body = base64.b64decode(real_stmt['response']['bodyBase64'])
        real_ops = R.body_json(real_stmt)
        derived_stmts = [e for e in derived.exchanges if R.statement_window(e)]
        derived_ops = [op for e in derived_stmts for op in R.body_json(e)]
        self.assertGreater(len(derived_stmts), 1)                                       # сторінки на робочому ліміті, а не одна на 500
        self.assertEqual({op['id'] for op in derived_ops}, {op['id'] for op in real_ops})
        for op in derived_ops:
            self.assertIn(json.dumps(op, ensure_ascii=False, separators=(',', ':')).encode('utf-8'), real_body)
        real_bal = next(e for e in real.exchanges if e['request']['path'].endswith('/balances'))
        self.assertEqual([e['response']['bodyBase64'] for e in derived.exchanges if e['request']['path'].endswith('/balances')],
                         [real_bal['response']['bodyBase64']])


READING_FOP = os.path.join(os.path.dirname(READING), '..', 'mono-fop', 'ЗапStatementSegment01')


class FopBankModel(unittest.TestCase):
    @unittest.skipUnless(os.path.isdir(READING_FOP), 'немає знеособленого запису run1 (temp/api-anon/run1)')
    def test_fop_model_reproduces_the_recorded_segment_and_a_broken_model_does_not(self):
        """ФОП: модель з місткістю сторінки 500 відтворює справжній запис `fop_statement_segment_01` (одна сторінка, 31 операція, від нових
        до старих) на запиті рекордера; модель із зіпсованим порядком (від старих до нових) його не відтворює. Продовження за
        часом на справжніх даних ФОП не виміряне (найбільша відповідь -- 31 операція), тож контроль лише цей."""
        rec = R.Recording.from_dir(READING_FOP)
        statements = [e for e in rec.exchanges if R.statement_window(e)]
        # читання під межі D36 п. 11 (похідний запис): один запит із запасом (S - 1, E + 1), відповідь справжня
        self.assertEqual(len(statements), 1)
        recorded = R.body_json(statements[0])
        self.assertGreater(len(recorded), 1)
        _, frm, to = R.statement_window(statements[0])
        self.assertEqual(bankmodel.FopBank(recorded).statement(frm, to, 500), recorded)

        class Ascending(bankmodel.FopBank):
            def statement(self, frm, to, limit):
                return list(reversed(super().statement(frm, to, limit)))

        self.assertNotEqual(Ascending(recorded).statement(frm, to, 500), recorded)       # контроль уміє впасти


if __name__ == '__main__':
    unittest.main()
