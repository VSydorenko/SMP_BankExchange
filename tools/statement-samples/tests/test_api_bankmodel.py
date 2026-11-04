# -*- coding: utf-8 -*-
"""Контроль моделі банку monobank юросіб (`apilib/bankmodel.py`): модель, що реалізує лише виміряне, відтворює справжній запис
`corp_a1_statement_small_limit` на запитах рекордера (to = час межової операції) -- сторінки 10/10/10/3, ті самі операції в тому
самому порядку; зіпсована модель (`to` включний) це відтворення валить. Один тест. Запис -- знеособлений вихід run1 у
гітігнорованій `temp/` (його немає в клонах без прогону), тож без нього тест пропускається."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import bankmodel, recording as R

READING = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'temp', 'api-anon', 'run1', 'readings',
                       'mono-corp', 'ЗапStatementSmallLimit')


def replay(model, statements):
    """Сторінки моделі на запити рекордера (from, to, limit) -> [сторінка]."""
    return [model.statement(R.statement_window(e)[1], R.statement_window(e)[2], int(dict(R.query_pairs(e))['limit']))
            for e in statements]


class BankModel(unittest.TestCase):
    @unittest.skipUnless(os.path.isdir(READING), 'немає знеособленого запису run1 (temp/api-anon/run1)')
    def test_model_reproduces_the_recorded_pagination_and_a_broken_model_does_not(self):
        rec = R.Recording.from_dir(READING)
        statements = [e for e in rec.exchanges if R.statement_window(e)]
        recorded = [R.body_json(e) for e in statements]
        self.assertEqual([len(p) for p in recorded], [10, 10, 10, 3])
        pool = [op for page in recorded for op in page]
        self.assertEqual(len({op['id'] for op in pool}), len(pool))               # у запису повторів немає
        self.assertEqual(replay(bankmodel.CorpBank(pool), statements), recorded)    # поле за полем, у тому самому порядку
        self.assertNotEqual(replay(bankmodel.CorpBank(pool, to_inclusive=True), statements), recorded)   # контроль уміє впасти


if __name__ == '__main__':
    unittest.main()
