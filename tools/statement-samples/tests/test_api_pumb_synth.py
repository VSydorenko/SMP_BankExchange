# -*- coding: utf-8 -*-
"""Синтетика ПУМБ (задача 2a, Step 3): що саме вона покриває і чого НЕ покриває. Усі значення вигадані; форма відповідей -- за swagger і гіпотетична (позначка в кожному записі).
Контролі, що вміють впасти: невиміряне (пагінація, формат дати) оракул ЯВНО відхиляє -- «зеленого» мовчки немає; кожен відступ ПУМБ, що має слід, спрацьовує на синтетиці й
його вимкнення змінює еталон рівно там, де він спрацьовує."""
import json
import os
import re
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import common as C, etalon, expected as E, kyiv, readings as RD, recording as R, sets, synth as S, synth_pumb as SP

PUMB = S.pumb_scenarios()
BY = {s.sid: s for s in PUMB}


def run(sid, disabled=()):
    return E.run(BY[sid].recording(), BY[sid].params, frozenset(disabled))


def numbers(items):
    return [x['ПорядковыйНомер'] for x in items]


class Coverage(unittest.TestCase):
    def test_every_plan_case_has_a_record_or_an_awaiting_reason(self):
        for case, sid in SP.CASES:
            if sid is None:
                self.assertIn(case, SP.AWAITING_RUN1, case)
                self.assertGreater(len(SP.AWAITING_RUN1[case]), 40, case)         # причина, а не відписка
            else:
                self.assertIn(sid, BY, case)
        # пагінація: чекає виміру, записів немає
        self.assertEqual({c for c, s in SP.CASES if s is None}, {'обрив на сторінці N', 'курсор, що не просувається', 'повна сторінка без ознаки кінця', 'стеля сторінок'})

    def test_every_bank_with_a_model_has_synthetics_and_the_reverse(self):
        banks = {s.bank for s in S.every_scenario()}
        self.assertEqual(banks, set(C.BANKS))
        self.assertIn('pumb', banks)
        self.assertEqual({s.bank for s in S.all_scenarios()}, {'privat', 'mono-fop', 'mono-corp'})     # 5а -- свій перелік, ПУМБ у нього не потрапив
        self.assertEqual(len(S.all_scenarios()), 114)
        for sid in {x for _, x in SP.CASES if x}:
            self.assertIn(sid, BY)

    def test_records_are_marked_hypothesis_v2_and_deterministic(self):
        names = [s.name for s in PUMB]
        self.assertEqual(len(names), len(set(names)))
        for s in PUMB:
            self.assertIn(SP.HYPOTHESIS, s.title, s.sid)
            rec = s.recording()
            self.assertIn(SP.HYPOTHESIS, rec.manifest['note'], s.sid)
            self.assertTrue(s.sid.startswith('СинтПУМБ') or s.sid == 'СинтПУМБ', s.sid)
            if rec.exchanges:
                self.assertEqual(rec.manifest['formatVersion'], 2, s.sid)
        a = [etalon.dumps(etalon.build(s)[0]) + s.recording().pack() for s in PUMB]
        b = [etalon.dumps(etalon.build(s)[0]) + s.recording().pack() for s in S.pumb_scenarios()]
        self.assertEqual(a, b)

    def test_requests_follow_the_stated_bounds_hypothesis_and_hold_no_secrets(self):
        for s in PUMB:
            rec = s.recording()
            p = s.params
            moment = p.reading_moment + timedelta(hours=3 if kyiv.offset_hours(p.reading_moment) == 3 else 2)
            searches = [e for e in rec.exchanges if e['request']['path'].endswith('/document/searcher')]
            self.assertLessEqual(len(searches), 1, s.sid)                             # жодних сторінок: нічого невиміряного
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
            for e in searches:
                body = json.loads(R.request_body_text(e))
                self.assertEqual(set(body), {'fromDate', 'toDate', 'documentAccounts'}, s.sid)    # без фільтра станів, типу й pagingRequest
                lo = (p.period_start - timedelta(seconds=1)).strftime('%d.%m.%Y %H:%M:%S')       # запас у секунду -- гіпотеза до виміру
                hi = min(p.period_end + timedelta(seconds=1), moment).strftime('%d.%m.%Y %H:%M:%S')
                self.assertEqual((body['fromDate'], body['toDate']), (lo, hi), s.sid)
                self.assertEqual(body['documentAccounts'], [str(SP.ACCOUNT_ID)])

    def test_nothing_unmodelled_hides_in_green(self):
        # (1) жоден запис синтетики не має сторінок: невиміряне не може бути «зеленим» мовчки; (2) запис, що їх має, оракул відхиляє, а `pumb_split` називає «не змодельовано»
        from test_api_pumb_oracle import reading, doc
        rec, p = reading([doc(1)], search_body={'fromDate': '01.11.2026 00:00:00', 'toDate': '01.11.2026 23:59:59', 'documentAccounts': ['5500123456'], 'pagingRequest': {'pageSize': 1}})
        with self.assertRaises(E.PaginationUnmeasured):
            E.run(rec, p)
        ok, skipped = RD.pumb_split(rec)
        self.assertEqual((ok, len(skipped)), ([], 1))
        for s in PUMB:
            split_ok, split_skipped = RD.pumb_split(s.recording())
            self.assertEqual(split_skipped, [], s.sid)            # усе, що в синтетиці, оракул моделює
        # формат дати -- гіпотеза: відсутня дата -- явна відмова, форма запису є, еталона немає
        refused = SP.refused_scenarios()
        self.assertEqual([s.sid for s in refused], ['СинтПУМББезДатыОперации'])
        for s in refused:
            with self.assertRaises(C.PumbDateFormat):
                E.run(s.recording(), s.params)
        self.assertNotIn(refused[0].sid, BY)


class HandExpected(unittest.TestCase):
    """Очікуване руками (зі спеки й відступів плану), не з оракула."""

    def test_failure_classes_and_trust_boundary_on_refusal(self):
        human, retry = E.CLS_HUMAN, E.CLS_RETRY
        table = {'СинтПУМБInvalidGrant': human, 'СинтПУМБ401Запрос': human, 'СинтПУМБСчетНеНайден': human, 'СинтПУМБПериодНаоборот': human,
                 'СинтПУМБ429': retry, 'СинтПУМБ5xx': retry, 'СинтПУМБHTML': retry, 'СинтПУМБHTML200': retry, 'СинтПУМБОбрыв': retry,
                 'СинтПУМБАномалияПосле': retry, 'СинтПУМБАномалияДо': retry}
        for sid, cls in table.items():
            e = run(sid)
            self.assertEqual((e.failure_class, e.complete, e.ops, e.trust), (cls, False, [], BY[sid].params.period_start), sid)        # відмова -> межа = НачалоПериода
            self.assertEqual([(d['Уровень'], d['ПорядковыйНомер']) for d in e.diags][0][0], 'Предупреждение', sid)
        # читання зупиняється на відмові: invalid_grant -- 1 запит, рахунку немає -- 2, решта -- 3
        self.assertEqual([len(run(s).requests) for s in ('СинтПУМБInvalidGrant', 'СинтПУМБСчетНеНайден', 'СинтПУМБ401Запрос')], [1, 2, 3])
        # текст людині без значень: банк, вид, статус, опис банку (помилки з description -- лише для 4xx/5xx)
        facts = run('СинтПУМБ5xx').diags[0]['Факты']
        self.assertEqual((facts['Банк'], facts['Статус'], facts['Вид']), ('ПУМБ', 500, 'http'))

    def test_states_and_trust(self):
        e = run('СинтПУМБНеокончательные')
        self.assertEqual((numbers(e.ops), numbers(e.diags), {d['Суть'] for d in e.diags}), ([1], [2, 3, 4], {'nonfinal'}))
        self.assertEqual((e.complete, e.trust), (True, datetime(2026, 11, 1, 12, 0, 0)))       # не пізніша за першу неостаточну (12:00)
        e = run('СинтПУМБОтменённые')
        self.assertEqual((numbers(e.ops), numbers(e.diags), {d['Суть'] for d in e.diags}), ([1], [2, 3, 4, 5], {'cancelled'}))
        self.assertEqual(e.trust, BY['СинтПУМБОтменённые'].params.period_end)                  # скасована межу не тримає
        e = run('СинтПУМБСтатусНеизвестен')
        self.assertEqual((numbers(e.ops), [(d['Уровень'], d['Суть']) for d in e.diags]), ([1], [('Ошибка', 'unknown-state')]))
        # межа довіри на початку: не раніша за НачалоПериода; неостаточний у запасі перед початком -- поза періодом, межі не тримає, операції не дає
        e = run('СинтПУМБГраницаНаНачале')
        self.assertEqual((e.trust, e.out_of_period, numbers(e.diags), numbers(e.ops)), (datetime(2026, 11, 1), [2], [1], [3]))

    def test_missing_fields_amount_identifier_purpose(self):
        e = run('СинтПУМБПоляОтсутствуют')
        self.assertEqual(numbers(e.ops), [1, 2, 3, 4])
        self.assertEqual([(d['ПорядковыйНомер'], d['Уровень'], d['Суть']) for d in e.diags],
                         [(4, 'Предупреждение', 'currency-unknown'), (5, 'Ошибка', 'bad-amount'), (6, 'Ошибка', 'unknown-state'), (7, 'Ошибка', 'unknown-direction'),
                          (8, 'Ошибка', 'no-iban')])        # Р-д: без IBAN обох сторін -- Ошибка, рахунок із accountId запиту не виводиться
        self.assertEqual([o['ИдентификаторОперации'] for o in e.ops], ['1101', '2202', '1103', '1104'])      # без id -- docId (відступ 6)
        self.assertEqual(e.ops[0]['НазначениеПлатежа'], '')                                           # без description -- порожнє, не «Неопределено»
        self.assertEqual(e.ops[2]['КонтрагентНаименование'] + e.ops[2]['КонтрагентКод'] + e.ops[2]['КонтрагентМФО'], '')
        e = run('СинтПУМБСумма')
        self.assertEqual((numbers(e.ops), [(d['Суть'], d['ПорядковыйНомер']) for d in e.diags]), ([1], [('bad-amount', 2), ('bad-amount', 3), ('bad-amount', 4)]))
        self.assertTrue(all(d['Уровень'] == 'Ошибка' for d in e.diags))
        self.assertEqual({'Количество'} | set(), set(run('СинтПУМБДлинныйИд').diags[0]['Факты']))     # довжина, не значення ідентифікатора
        e = run('СинтПУМБДлинныйИд')
        self.assertEqual((numbers(e.ops), len(e.ops[0]['ИдентификаторОперации']), [(d['Суть'], d['Факты']['Количество']) for d in e.diags]),
                         ([1, 5], 50, [('bad-identifier', 51), ('bad-identifier', 0), ('bad-identifier', 0)]))
        self.assertEqual(e.ops[1]['ИдентификаторОперации'], '2205')                                   # pumb6: id='' -- не ідентифікатор, береться docId
        e = run('СинтПУМБInvalidGrant')                                                              # Р-е: опис банку читається, вигаданий логін вирізано
        self.assertEqual(e.diags[0]['Факты']['ОписаниеБанка'], 'Invalid user credentials for ' + E.PUMB_CUT_MARK)
        self.assertNotIn(SP.FAKE_LOGIN, json.dumps(e.diags, ensure_ascii=False).lower())
        e = run('СинтПУМБНазначение')
        self.assertEqual(len(e.ops[0]['НазначениеПлатежа']), 1200)                                    # не обрізане до 1024 (відступ 5)

    def test_bounds_time_and_periods(self):
        e = run('СинтПУМБГраницаСуток')
        self.assertEqual((numbers(e.ops), e.out_of_period, e.silent), ([2, 3], [1, 4], 0))           # запас між межами запиту й періодом -- мовчки, не аномалія
        self.assertEqual([o['ДатаДокумента'] for o in e.ops], ['2026-11-01', '2026-11-01'])
        e = run('СинтПУМБВремяВесна')
        self.assertEqual([o['ДатаОперации'] for o in e.ops], ['2026-03-28T00:30:00', '2026-03-29T02:59:59', '2026-03-29T04:00:00', '2026-03-29T23:59:59'])
        e = run('СинтПУМБВремяОсень')
        self.assertEqual(sorted(o['ДатаОперации'] for o in e.ops), ['2026-10-25T00:30:00', '2026-10-25T03:30:00', '2026-10-25T03:30:00', '2026-10-25T23:59:59'])
        self.assertEqual(len({o['ИдентификаторОперации'] for o in e.ops}), 4)                          # дві різні операції з однаковим місцевим часом
        e = run('СинтПУМБПусто')
        self.assertEqual((e.ops, e.diags, e.complete, e.trust), ([], [], True, BY['СинтПУМБПусто'].params.period_end))
        e = run('СинтПУМБПериодВБудущем')
        self.assertEqual((e.ops, e.requests, e.complete, e.trust), ([], [], True, BY['СинтПУМБПериодВБудущем'].params.period_start))
        self.assertEqual(BY['СинтПУМБПериодВБудущем'].recording().exchanges, [])
        e = run('СинтПУМБПериодНаоборот')
        self.assertEqual((e.requests, e.failure_class), ([], E.CLS_HUMAN))
        e = run('СинтПУМБМоментВнутриПериода')
        self.assertEqual((e.complete, e.trust), (True, datetime(2026, 11, 20, 2, 0, 0)))             # межа = момент читання за Києвом, не КонецПериода

    def test_foreign_account_and_currency(self):
        e = run('СинтПУМБЧужойСчет')
        self.assertEqual((numbers(e.ops), list(e.foreign.values())), ([1, 2], [[2]]))                 # чужий рахунок йде до точки читання, яка пише діагностику (D30)
        self.assertNotEqual(e.ops[1]['НомерСчета'], BY['СинтПУМБЧужойСчет'].params.account)
        e = run('СинтПУМБЧужаяВалюта')
        self.assertEqual((numbers(e.ops), [(d['Уровень'], d['Суть'], d['ПорядковыйНомер']) for d in e.diags]), ([1], [('Предупреждение', 'foreign-currency', 2)]))
        e = run('СинтПУМБВалютныйСчет')
        self.assertEqual(([o['Валюта'] for o in e.ops], [d['Суть'] for d in e.diags]), (['980'], ['currency-unknown']))


class Contract(unittest.TestCase):
    def test_contract_rules_hold_for_every_expected_operation(self):
        for s in PUMB:
            e = E.run(s.recording(), s.params)
            for o in e.ops:
                self.assertEqual(list(o), E.OP_COLUMNS, s.sid)
                self.assertIn(o['Направление'], ('Поступило', 'Списано'))
                self.assertRegex(o['Валюта'], r'^(\d{3})?$')
                self.assertTrue(1 <= len(o['ИдентификаторОперации']) <= 50, s.sid)
                self.assertTrue(o['НомерСчета'], s.sid)
                self.assertGreater(float(o['Сумма']), 0, s.sid)
                self.assertEqual(o['ДатаДокумента'], o['ДатаОперации'][:10])
            if e.failure_class:
                self.assertFalse(e.complete, s.sid)
                self.assertEqual(e.trust, s.params.period_start, s.sid)
                self.assertTrue(all(d['Уровень'] == 'Предупреждение' for d in e.diags), s.sid)
            else:
                self.assertTrue(e.complete, s.sid)
            # нічого не зникає мовчки: кожен документ відповіді -- операція, рядок діагностики або запас поза періодом (рядок currency-unknown -- застереження до операції)
            nums = numbers(e.ops) + [d['ПорядковыйНомер'] for d in e.diags if d['ПорядковыйНомер'] > 0 and d['Суть'] != 'currency-unknown']
            self.assertEqual(len(nums), len(set(nums)), s.sid)
            if not e.failure_class:
                self.assertEqual(len(nums) + len(e.out_of_period) + e.silent, e.items, s.sid)
            self.assertEqual(e.silent, 0, s.sid)

    def test_sets_for_pumb_are_buildable_with_equal_ids(self):
        recs, ets = sets.synthetic_sets('pumb')                               # макетів поки не генеруємо; набір збирається з тих самих записів
        self.assertEqual(sorted(recs), sorted(ets))
        self.assertEqual(len(recs), len(PUMB))
        for ident, pack in recs.items():
            rec = R.Recording.unpack(json.dumps(pack, ensure_ascii=False))
            self.assertEqual(len(rec.exchanges), ets[ident]['recording']['обменов'])
            self.assertTrue(ets[ident]['synthetic'])
            self.assertEqual(ets[ident]['oldProcessing']['Допущения'], ['PUMB-NOT-APPLICABLE'])     # ключ зі старою обробкою не звіряється (D17, виняток ПУМБ)
            self.assertTrue({'ИдентификаторПУМБ', 'ВозвратПУМБ', 'ФорматДатыПУМБ'} <= set(ets[ident]['dependsOn']))
        self.assertNotIn('pumb', sets.BANKS)                                  # у `sets.build` (12 макетів 5а) ПУМБ не потрапляє: макети -- після скану консультанта й задачі 3


class Deviations(unittest.TestCase):
    """Кожен відступ ПУМБ, що має слід, спрацьовує на синтетиці; вимкнення змінює еталон рівно там, де він спрацьовує; решта названі з причиною."""
    NO_TRACE = {'pumb4': 'повернення -- до виміру: функція нічого не вгадує, слід є лише в залежності еталона `ВозвратПУМБ`',
                'pumb7': 'київський час: формат дати -- гіпотеза; відступ не має власного вимикача й сліду, формат перевіряє `PumbDateFormat` (запис СинтПУМББезДатыОперации)',
                'pumb8': 'пагінація -- до виміру: оракул відмовляє (`PaginationUnmeasured`), слід -- відмова, а не `applied`'}

    def test_every_pumb_deviation_fires_somewhere_or_is_named_without_trace(self):
        fired = set()
        for s in PUMB:
            fired |= E.run(s.recording(), s.params).applied
        self.assertEqual(fired, set(E.PUMB_DEVIATIONS) - set(self.NO_TRACE))
        self.assertEqual(set(self.NO_TRACE) - set(E.PUMB_DEVIATIONS), set())
        self.assertFalse(fired & set(E.DEVIATIONS))                                # відступи 5а ПУМБ не зачіпають

    @staticmethod
    def expected_part(s, disabled=()):
        return json.dumps(etalon.build(s, frozenset(disabled))[0]['expected'], sort_keys=True, ensure_ascii=False)

    def test_disabling_a_deviation_changes_exactly_the_records_where_it_fires(self):
        for dev in sorted(set(E.PUMB_DEVIATIONS) - set(self.NO_TRACE)):
            fires, changes = set(), set()
            for s in PUMB:
                if dev in E.run(s.recording(), s.params).applied:
                    fires.add(s.sid)
                if self.expected_part(s) != self.expected_part(s, {dev}):
                    changes.add(s.sid)
            self.assertTrue(fires, dev)
            self.assertEqual(changes, fires, dev)


if __name__ == '__main__':
    unittest.main()
