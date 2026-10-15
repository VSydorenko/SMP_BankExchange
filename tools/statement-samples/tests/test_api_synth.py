# -*- coding: utf-8 -*-
"""Синтетичні записи й еталони: форма, детермінованість, покриття Review Focus, спрацювання кожного відступу, сумісність
ключа з попередником, контроль поломкою кожного відступу. Дані — вигадані генератором; валідатори кодів незалежні від
генератора (`python-stdnum`)."""
import json
import os
import re
import sys
import unittest
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import common as C, etalon, expected as E, oracle_old as O, recording as R, synth as S

try:
    from stdnum import iban as sn_iban
    from stdnum.ua import edrpou as sn_edrpou, rntrc as sn_rntrc
except ImportError:            # pragma: no cover
    sn_iban = None

ALL = S.all_scenarios()
CODE_KEYS = {'AUT_MY_CRF', 'AUT_CNTR_CRF', 'counterEdrpou', 'idCode'}


def strings(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from strings(v)
            if isinstance(v, str):
                yield k, v
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


def bodies(rec):
    for ex in rec.exchanges:
        if ex['response']:
            try:
                yield R.body_json(ex)
            except R.NotJson:
                pass


class Shape(unittest.TestCase):
    def test_names_unique_and_marked_synthetic(self):
        names = [s.name for s in ALL]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all('Синт' in s.name and 'Синт' in s.etalon_name for s in ALL))
        self.assertTrue(all(R.Recording.__name__ and s.recording().manifest['note'].startswith('synthetic:') for s in ALL))

    def test_generation_is_deterministic(self):
        a = [etalon.dumps(etalon.build(s)[0]) + s.recording().pack() for s in ALL]
        b = [etalon.dumps(etalon.build(s)[0]) + s.recording().pack() for s in S.all_scenarios()]
        self.assertEqual(a, b)

    def test_recorded_requests_are_those_a_connector_would_make(self):
        for s in ALL:
            self.assertEqual(E.verify_requests(s.recording(), s.params), [], s.name)

    @unittest.skipIf(sn_iban is None, 'python-stdnum недоступний')
    def test_invented_codes_have_valid_checksums(self):
        count = {'iban': 0, 'code': 0}
        for s in ALL:
            rec = s.recording()
            texts = [(k, v) for b in bodies(rec) for k, v in strings(b)]
            texts += [('path', e['request']['path']) for e in rec.exchanges]
            texts.append(('account', s.params.account))
            for k, v in texts:
                for m in re.findall(r'UA\d{27}', v):
                    self.assertTrue(sn_iban.is_valid(m), (s.name, 'IBAN'))
                    count['iban'] += 1
                if k in CODE_KEYS and v:
                    ok = sn_edrpou.is_valid(v) if len(v) == 8 else sn_rntrc.is_valid(v)
                    self.assertTrue(ok, (s.name, k))
                    count['code'] += 1
        self.assertGreater(count['iban'], 20)
        self.assertGreater(count['code'], 20)

    def test_no_token_like_or_header_leak(self):
        for s in ALL:
            for ex in s.recording().exchanges:
                self.assertNotIn('headers', ex['request'])
                self.assertNotIn('token', json.dumps(ex['request']).lower())

    def test_contract_rules_hold_for_every_expected_operation(self):
        zero = {'СинтПоля'}
        for s in ALL:
            e = E.run(s.recording(), s.params)
            for o in e.ops:
                self.assertEqual(list(o), E.OP_COLUMNS, s.name)
                self.assertIn(o['Направление'], ('Поступило', 'Списано'))
                self.assertRegex(o['Валюта'], r'^(\d{3})?$')
                self.assertLessEqual(len(o['ИдентификаторОперации']), 50)
                self.assertTrue(o['НомерСчета'])
                self.assertEqual(o['ДатаДокумента'], o['ДатаОперации'][:10])
                if o['Сумма'] == '0.00':
                    self.assertIn(s.sid, zero)          # нуль до платформи доходить лише там, де запис це перевіряє
                self.assertNotIn('Неопределено', o['НазначениеПлатежа'])

    def test_failure_records_have_class_and_success_do_not(self):
        for s in ALL:
            e = E.run(s.recording(), s.params)
            if e.failure_class:
                self.assertFalse(e.complete, s.name)
                self.assertEqual(e.trust, s.params.period_start, s.name)      # межа визначена: курсор не посунеться
                self.assertTrue(all(d['Уровень'] == 'Предупреждение' for d in e.diags if d['Суть'] in ('read-failed', 'account-not-found')), s.name)
                self.assertTrue(any(d['Суть'] in ('read-failed', 'account-not-found') for d in e.diags), s.name)
                self.assertIn(e.failure_class, (E.CLS_RETRY, E.CLS_HUMAN))
            else:
                self.assertTrue(e.complete, s.name)

    def test_diagnostic_facts_are_a_closed_list(self):
        """Текст для людини будується лише з названих фактів (банк, статус, опис банку, ідентифікатор): заголовків запиту й
        облікових даних у діагностиці немає за побудовою."""
        allowed = {'Банк', 'Вид', 'Статус', 'ОписаниеБанка', 'Состояние', 'Ид', 'Момент', 'Значение', 'Код', 'КодСервиса'}
        for s in ALL:
            for d in E.run(s.recording(), s.params).diags:
                self.assertLessEqual(set(d['Факты']), allowed, s.name)


class Coverage(unittest.TestCase):
    def test_every_review_focus_row_is_covered_per_bank(self):
        for bank in C.BANKS:
            got = set()
            for s in ALL:
                if s.bank == bank:
                    got |= set(s.focus)
            self.assertEqual(got, {1, 2, 3, 4, 5}, bank)

    def test_every_deviation_fires_somewhere(self):
        fired = set()
        for s in ALL:
            fired |= E.run(s.recording(), s.params).applied
        self.assertEqual(fired, set(E.DEVIATIONS) - {'dev8'})       # dev8 видно лише на базі з іншим поясом сеансу (нижче)

    def test_states_are_all_present(self):
        seen = {'privat': set(), 'mono-fop': set(), 'mono-corp': set()}
        for s in ALL:
            for body in bodies(s.recording()):
                if isinstance(body, dict):
                    seen['privat'] |= {t['PR_PR'] for t in body.get('transactions', [])}
                if isinstance(body, list):
                    for t in body:
                        if 'hold' in t:
                            seen['mono-fop'].add('hold' if t['hold'] else 'final')
                        if 'status' in t:
                            seen['mono-corp'] |= {t['status'], 'reverse' if t['reverse'] else 'plain'}
        self.assertEqual(seen['privat'], set('rptn'))
        self.assertEqual(seen['mono-fop'], {'hold', 'final'})
        self.assertEqual(seen['mono-corp'], {'DONE', 'PENDING', 'DECLINED', 'reverse', 'plain'})

    def test_pagination_edge_cases_exist(self):
        by = {(s.bank, s.sid): s for s in ALL}
        for bank in ('mono-fop', 'mono-corp'):
            rec = by[(bank, 'СинтСтраницы')].recording()
            pages = [R.body_json(e) for e in C.statement_exchanges(rec)]
            self.assertEqual(len(pages[0]), 500)
            ids = [t['id'] for p in pages for t in p]
            self.assertGreater(len(ids), len(set(ids)))                       # одна операція на двох сторінках
            self.assertEqual(len(E.run(rec, by[(bank, 'СинтСтраницы')].params).ops), len(set(ids)))   # але рівно один раз
            times = [t['time'] for t in pages[0]]
            self.assertGreater(len([x for x in times if x == min(times)]), 1)  # однакова секунда на межі
        e = E.run(by[('privat', 'СинтСтраницы')].recording(), by[('privat', 'СинтСтраницы')].params)
        self.assertEqual((len(e.ops), e.complete), (100, True))               # рівно limit записів і порожня друга сторінка
        e = E.run(by[('privat', 'СинтБезСледующей')].recording(), by[('privat', 'СинтБезСледующей')].params)
        self.assertEqual((e.failure_class, e.complete, len(e.ops)), (E.CLS_RETRY, False, 1))


class KeyCompatibility(unittest.TestCase):
    """D17: поля ключа — як у попередника. Для кожного запису, який завантажила стара обробка: або та сама операція в
    «очікуваному» з тими самими значеннями (день ДатаДокумента, номер, рахунок контрагента, сума), або рядок діагностики."""

    def test_key_fields_match_old_processing(self):
        compared = 0
        for s in ALL:
            rec = s.recording()
            e = E.run(rec, s.params)
            old = O.run(rec, s.params)
            ops = {o['ПорядковыйНомер']: o for o in e.ops}
            diag_numbers = {d['ПорядковыйНомер'] for d in e.diags} | set(e.duplicate_numbers)
            for r in old.rows:
                f = r.fields
                if r.n not in ops:
                    self.assertIn(r.n, diag_numbers, (s.name, r.n))
                    continue
                o = ops[r.n]
                self.assertEqual(o['ДатаДокумента'], f['ДатаДокумента'].strftime('%Y-%m-%d'), (s.name, r.n))
                self.assertEqual(o['НомерДокумента'], f['НомерДокумента'], (s.name, r.n))
                self.assertEqual(o['КонтрагентНомерСчета'], f['КонтрагентНомерСчета'], (s.name, r.n))
                self.assertEqual(Decimal(o['Сумма']), f['Сумма'], (s.name, r.n))
                compared += 1
        self.assertGreater(compared, 1500)


class KyivBoundaries(unittest.TestCase):
    """Літерали: 00:30 за Києвом, доби на 23 і 25 годин (виміряно платформою), день ДатаДокумента за completedTime."""

    def ops(self, bank, sid):
        s = [x for x in ALL if x.bank == bank and x.sid == sid][0]
        return E.run(s.recording(), s.params).ops

    def test_spring(self):
        want = {'2026-03-28T00:30:00', '2026-03-28T23:59:59', '2026-03-29T00:00:00', '2026-03-29T02:59:59',
                '2026-03-29T04:00:00', '2026-03-29T23:59:59', '2026-03-30T00:30:00'}
        self.assertEqual({o['ДатаОперации'] for o in self.ops('mono-fop', 'СинтВремяВесна')}, want)

    def test_autumn_has_two_distinct_operations_at_the_same_local_moment(self):
        ops = self.ops('mono-fop', 'СинтВремяОсень')
        self.assertEqual(sorted(o['ДатаОперации'] for o in ops),
                         ['2026-10-25T00:30:00', '2026-10-25T03:30:00', '2026-10-25T03:30:00', '2026-10-25T23:59:59',
                          '2026-10-26T00:30:00'])
        self.assertEqual(len({o['ИдентификаторОперации'] for o in ops}), 5)

    def test_corp_completed_time_decides_the_document_day(self):
        for sid, day, moment in (('СинтВремяВесна', '2026-03-30', '2026-03-30T00:10:00'),
                                 ('СинтВремяОсень', '2026-10-26', '2026-10-26T00:10:00')):
            ops = [o for o in self.ops('mono-corp', sid) if o['ДатаОперации'] == moment]
            self.assertEqual([o['ДатаДокумента'] for o in ops], [day])


class DeviationMutations(unittest.TestCase):
    """Контроль поломкою: вимкнений відступ (поведінка попередника) дає зміну рівно на записах, де він спрацьовує."""

    @staticmethod
    def expected_part(s, disabled=()):
        d = etalon.build(s, frozenset(disabled))[0]['expected']
        return json.dumps(d, sort_keys=True, ensure_ascii=False)

    def test_each_deviation_changes_exactly_the_records_where_it_fires(self):
        for dev in sorted(set(E.DEVIATIONS) - {'dev8'}):
            fires, changes = set(), set()
            for s in ALL:
                e = E.run(s.recording(), s.params)
                if dev in e.applied:
                    fires.add(s.name)
                if self.expected_part(s) != self.expected_part(s, {dev}):
                    changes.add(s.name)
            self.assertTrue(fires, dev)
            self.assertEqual(changes, fires, dev)

    def test_dev8_matters_only_on_a_base_whose_session_is_not_kyiv(self):
        for s in ALL:
            if s.bank == 'privat':
                continue
            p_utc = replace(s.params, old_session_tz='UTC')
            on = E.run(s.recording(), p_utc)
            off = E.run(s.recording(), p_utc, {'dev8'})
            if on.ops:
                self.assertNotEqual(on.ops, off.ops, s.name)
            same_kyiv = E.run(s.recording(), s.params, {'dev8'})
            self.assertEqual(same_kyiv.ops, E.run(s.recording(), s.params).ops, s.name)    # на київській базі збігається

    def test_privat_rejected_mutation_is_red_exactly_on_the_rejected_record(self):
        """Прогноз плану: «n вантажити як проведену» -> червоний рівно тест забракованої операції."""
        s = [x for x in ALL if x.bank == 'privat' and x.sid == 'СинтСтатусы'][0]
        base = E.run(s.recording(), s.params)
        mut = E.run(s.recording(), s.params, {'dev3'})
        extra = [o for o in mut.ops if o['ПорядковыйНомер'] not in {x['ПорядковыйНомер'] for x in base.ops}]
        self.assertEqual([o['ПорядковыйНомер'] for o in extra], [4])
        self.assertEqual(extra[0]['Сумма'], '19.99')

    def test_reversal_mutation_is_red_exactly_on_the_reversal_record(self):
        """«повернення пропускати, як попередник юросіб»."""
        s = [x for x in ALL if x.bank == 'mono-corp' and x.sid == 'СинтСтатусы'][0]
        base = E.run(s.recording(), s.params)
        mut = E.run(s.recording(), s.params, {'dev4'})
        lost = [o['НомерДокумента'] for o in base.ops if o['ПорядковыйНомер'] not in {x['ПорядковыйНомер'] for x in mut.ops}]
        self.assertEqual(len(lost), 1)


from decimal import Decimal  # noqa: E402

if __name__ == '__main__':
    unittest.main()
