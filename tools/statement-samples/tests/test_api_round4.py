# -*- coding: utf-8 -*-
"""Раунд 4 задачі 2: запити й паузи еталона -- лише спожиті обміни (I1); `/settings` -- обов'язковий перший обмін кожного читання
Привата (I2, R14); вузький виняток перевірки (а) за парою полів DLR ⊂ NUM_DOC (I3); кілька рядків балансу за добу. Дані синтетичні."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import common as C, recording as R, step2

from test_api_step2 import Env, mutate_body


class NarrowPairException(unittest.TestCase):
    """I3 (раунд run3 змінено): значення ролі ID, що стоїть підрядком у KEEP-полі (DLR у NUM_DOC), знеособлювач підміняє тією ж заміною; сире значення в будь-якому KEEP-полі -- витік."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = Env('privat', 'СинтСтраницыСлед', self.tmp)
        raw = R.Recording.from_dir(self.env.raw)
        self.page = [e['seq'] for e in raw.exchanges if e['request']['path'] == C.PRIVAT_PATH][0]
        t = R.body_json(raw.exchanges[self.page - 1])['transactions'][0]
        self.dlr, self.num = t['DLR'], t['NUM_DOC']
        # у вигаданому «сирому» записі DLR стає частиною NUM_DOC (як у справжньому: 25 з 404 рядків)
        mutate_body(self.env.raw, self.page, lambda s: s.replace('"NUM_DOC":"%s"' % self.num, '"NUM_DOC":"Q%s"' % self.dlr, 1))
        self.env.anonymize()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def res(self, target=None):
        return step2.check_a('privat', self.env.raw, target or self.env.anon)

    def anon_tx(self):
        return R.body_json(R.Recording.from_dir(self.env.anon).exchanges[self.page - 1])['transactions'][0]

    def test_dlr_inside_num_doc_is_replaced_by_the_same_map_value(self):
        """Раунд run3: виняток DLR_in_NUM_DOC знято. Знеособлювач підміняє значення ролі ID, що стоїть підрядком у KEEP-полі, ТІЄЮ САМОЮ заміною з мапи, що й у своєму полі: у знеособленому
        NUM_DOC лежить вигаданий DLR (зв'язок зберігається), а сирого немає; перевірка (а) чиста й винятку за парою DLR / NUM_DOC не веде."""
        t = self.anon_tx()
        self.assertIn(t['DLR'], t['NUM_DOC'])
        self.assertNotIn(self.dlr, t['NUM_DOC'])
        r = self.res()
        self.assertEqual(r['hits'], 0)
        self.assertNotIn('DLR_in_NUM_DOC', r['pair_counts'])

    def test_the_raw_value_left_in_num_doc_is_red(self):
        """Контроль: сире значення ролі ID у NUM_DOC знеособленого запису (заміну вимкнено чи відкочено) -- витік, перевірка (а) його знаходить."""
        t = self.anon_tx()
        mutate_body(self.env.anon, self.page, lambda s: s.replace('"NUM_DOC":"%s"' % t['NUM_DOC'], '"NUM_DOC":"Z%s"' % self.dlr, 1))
        self.assertGreater(self.res()['hits'], 0)

    def test_the_value_hidden_in_another_keep_field_is_red(self):
        mutate_body(self.env.anon, self.page, lambda s: s.replace('"type":"transactions"', '"type":"%s"' % self.dlr, 1))
        self.assertGreater(self.res()['hits'], 0)


class NameInKeepString(unittest.TestCase):
    """Раунд фінального рев'ю: слово з NAME (прізвище, назва контрагента) у рядковому полі KEEP знеособлювач замінює тією ж заміною слова з мапи, а перевірка (а) більше не виключає
    слово лише тому, що воно трапилось у KEEP того самого запису (`keep_words` прибрано)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = Env('privat', 'СинтСтраницыСлед', self.tmp)
        raw = R.Recording.from_dir(self.env.raw)
        self.page = [e['seq'] for e in raw.exchanges if e['request']['path'] == C.PRIVAT_PATH][0]
        t = R.body_json(raw.exchanges[self.page - 1])['transactions'][0]
        import re as _re
        from apilib import anonymize as A
        words = [w for w in _re.findall(r'[A-Za-zА-Яа-яІіЇїЄєҐґ]{4,}', t['AUT_CNTR_NAM']) if w[0].isupper() and w.casefold() not in A.GEN_WORDS and w not in ('Банк',)]
        self.word = words[0]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_name_word_in_a_keep_string_is_replaced_and_the_check_is_green(self):
        mutate_body(self.env.raw, self.page, lambda s: s.replace('"type":"transactions"', '"type":"%s"' % self.word, 1))
        self.env.anonymize()
        anon = R.body_json(R.Recording.from_dir(self.env.anon).exchanges[self.page - 1])
        self.assertNotIn(self.word, anon['type'])
        self.assertEqual(len(anon['type']), len(self.word))                          # заміна тієї ж довжини: форма збережена
        self.assertEqual(step2.check_a('privat', self.env.raw, self.env.anon)['hits'], 0)

    def test_the_name_word_left_in_a_keep_string_is_red(self):
        """Контроль, що вміє падати: слово з NAME того самого запису в KEEP-рядку знеособленого запису -- збіг (раніше його ховав `keep_words`)."""
        self.env.anonymize()
        mutate_body(self.env.anon, self.page, lambda s: s.replace('"type":"transactions"', '"type":"%s"' % self.word, 1))
        self.assertGreater(step2.check_a('privat', self.env.raw, self.env.anon)['hits'], 0)


class KeepNumbersOnlyFromListedFields(unittest.TestCase):
    """Консультант фінального рев'ю: число з поля KEEP виключається з перевірки (а) ЛИШЕ для явного переліку полів (`step2.KEEP_NUM_FIELDS`: суми, дати, номери документів).
    Число з поля іншого роду (тут `type`, як і `message`) винятку не має."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = Env('privat', 'СинтСтраницыСлед', self.tmp)
        self.raw = R.Recording.from_dir(self.env.raw)
        self.page = [e['seq'] for e in self.raw.exchanges if e['request']['path'] == C.PRIVAT_PATH][0]
        from apilib import leakguard
        self.cfg = leakguard.api_config()
        self.num = sorted(step2.collect('privat', self.raw, self.cfg).nums)[0]       # число від 5 цифр з чутливого поля

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def nums_after(self, fn):
        mutate_body(self.env.raw, self.page, fn)
        return step2.collect('privat', R.Recording.from_dir(self.env.raw), self.cfg).nums

    def test_a_number_in_a_keep_field_outside_the_list_is_not_exempt(self):
        """Контроль, що вміє падати: те саме число в `type` (KEEP поза переліком) лишається в чутливих і (а) його шукає."""
        self.assertNotIn('type', step2.KEEP_NUM_FIELDS['privat'])
        self.assertIn(self.num, self.nums_after(lambda s: s.replace('"type":"transactions"', '"type":"%s"' % self.num, 1)))

    def test_a_number_in_a_listed_field_is_exempt(self):
        import re as _re
        self.assertIn('SUM', step2.KEEP_NUM_FIELDS['privat'])
        nums = self.nums_after(lambda s: _re.sub(r'"SUM":"[^"]*"', '"SUM":"%s"' % self.num, s, count=1))
        self.assertNotIn(self.num, nums)

    def test_the_guard_list_exempts_amounts_dates_documents_only(self):
        from sslib import guard
        for k in ('SUMMA', 'dаtа_d', 'DOCUMENTNO', 'номер документа'):                    # (друге -- з кириличним двійником)
            self.assertIn(guard.norm_key(k), guard.KEEP_NUM_KEYS)
        for k in ('mfo_cr', 'BANKID', 'OPERATIONID', 'message', 'мфо'):
            self.assertNotIn(guard.norm_key(k), guard.KEEP_NUM_KEYS)


if __name__ == '__main__':
    unittest.main()
