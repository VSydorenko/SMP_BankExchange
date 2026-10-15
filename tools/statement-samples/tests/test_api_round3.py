# -*- coding: utf-8 -*-
"""Раунд 3 задачі 2: оракул і синтетика вирівняно з фактами run1 (R12: запис -- факт, документація -- гіпотеза). Дані
синтетичні; жодного значення справжніх записів тут немає."""
import os
import sys
import unittest
from dataclasses import fields, replace
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import common as C, expected as E, recording as R, synth as S
from apilib.common import Params

SCN = {(s.bank, s.sid): s for s in S.all_scenarios()}


def body(scn, k=0, path=None):
    exs = [e for e in scn.exchanges if path is None or e['request']['path'] == path]
    return R.body_json(exs[k])


def privat_pages(s):
    for e in s.exchanges:
        if e['request']['path'] == C.PRIVAT_PATH and e['response'] and e['response']['status'] == 200:
            try:
                js = R.body_json(e)
            except R.NotJson:
                continue
            if isinstance(js, dict):
                yield js


class ParamsFollowRun1(unittest.TestCase):
    def test_no_14_digit_account_format_parameter(self):
        self.assertNotIn('old_account_format', {f.name for f in fields(Params)})

    def test_defaults(self):
        p = Params(account='x', period_start=None, period_end=None)
        self.assertEqual((p.privat_id, p.fop_pause_after_client_info), ('ID', 0))

    def test_fop_has_no_pause_after_client_info_by_default(self):
        for s in SCN.values():
            if s.bank == 'mono-fop':
                self.assertNotIn('after-client-info', [x['Причина'] for x in E.run(s.recording(), s.params).pauses], s.name)
        s = SCN[('mono-fop', 'СинтСтатусы')]
        e = E.run(s.recording(), replace(s.params, fop_pause_after_client_info=60))
        self.assertIn('after-client-info', [x['Причина'] for x in e.pauses])


class PrivatForms(unittest.TestCase):
    def test_accounts_are_iban(self):
        n = 0
        for s in SCN.values():
            if s.bank != 'privat':
                continue
            for js in privat_pages(s):
                for t in js.get('transactions', []):
                    for k in ('AUT_MY_ACC', 'AUT_CNTR_ACC'):
                        self.assertRegex(t[k], r'^UA\d{27}$', (s.name, k))
                        n += 1
        self.assertGreater(n, 200)

    def test_id_equals_technical_id_except_the_not_observed_variant(self):
        for s in SCN.values():
            if s.bank == 'privat' and s.sid != 'СинтПовторТехнический':
                for js in privat_pages(s):
                    for t in js.get('transactions', []):
                        self.assertEqual(t['ID'], t['TECHNICAL_TRANSACTION_ID'], s.name)

    def test_cursor_is_last_id_and_present_on_the_last_page(self):
        pages = list(privat_pages(SCN[('privat', 'СинтСтраницыСлед')]))
        self.assertEqual([p['exist_next_page'] for p in pages], [True, True, False])
        for pg in pages:
            self.assertEqual(pg['next_page_id'], pg['transactions'][-1]['ID'])

    def test_balance_rows_are_newest_first_with_dpd(self):
        rows = body(SCN[('privat', 'СинтГраницаДыра')], path=C.PRIVAT_BALANCE_PATH)['balances']
        days = [r['dpd'] for r in rows]
        self.assertEqual(len(rows), 4)
        self.assertEqual(days, sorted(days, key=lambda d: (d[6:10], d[3:5], d[:2]), reverse=True))
        self.assertIsInstance(rows[0]['is_final_bal'], bool)

    def test_http_errors_have_the_observed_shape(self):
        for sid in ('СинтТокен401', 'СинтПериод400', 'СинтЧужойСчет403'):
            self.assertEqual(set(body(SCN[('privat', sid)])), {'status', 'code', 'message', 'requestId', 'appErrorCode'})

    def test_error_at_200_stays_synthetic_and_marked(self):
        for sid in ('СинтОшибкаСтатус', 'СинтОшибкаАвторизация'):
            self.assertIn('документальний, не спостерігалось', SCN[('privat', sid)].title)

    def test_technical_variant_is_marked(self):
        self.assertIn('не спостерігалось', SCN[('privat', 'СинтПовторТехнический')].title)


class MonoForms(unittest.TestCase):
    def test_corp_errors_have_the_observed_shape(self):
        ex = SCN[('mono-corp', 'СинтТокен400')].exchanges[0]
        self.assertEqual(ex['response']['status'], 400)
        self.assertTrue(R.header(ex, 'content-type').startswith('text/plain'))
        self.assertEqual(set(R.body_json(ex)), {'errorDescription'})                      # errorCode немає
        for sid in ('СинтПериод400', 'СинтЧужойСчет400'):
            self.assertEqual(body(SCN[('mono-corp', sid)])['errorCode'], 'BAD_REQUEST')
        b = SCN[('mono-corp', 'СинтБалансыСбой')].exchanges[-1]
        self.assertEqual((b['response']['status'], R.body_json(b)['errorCode']), (500, 'INTERNAL_SERVER_ERROR'))
        self.assertIn('документальний', SCN[('mono-corp', 'СинтТокен403')].title)

    def test_fop_errors_carry_only_error_description(self):
        for s in SCN.values():
            if s.bank != 'mono-fop':
                continue
            for e in s.exchanges:
                if e['response'] and e['response']['status'] >= 400:
                    self.assertEqual(set(R.body_json(e)), {'errorDescription'}, s.name)
        self.assertEqual(SCN[('mono-fop', 'СинтТокен403')].exchanges[0]['response']['status'], 403)
        self.assertEqual(SCN[('mono-fop', 'СинтЧужойСчет400')].exchanges[-1]['response']['status'], 400)

    def test_corp_balance_is_float_and_has_a_row_per_day(self):
        s = SCN[('mono-corp', 'СинтСтатусы')]
        rows = body(s, path='/ext/v1/accounts/%s/balances' % s.params.account)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(isinstance(r['balance'], Decimal) and r['balance'] != r['balance'].to_integral_value() for r in rows))

    def test_corp_completed_time_may_precede_time(self):
        s = SCN[('mono-corp', 'СинтСтатусы')]
        first = [e for e in s.exchanges if R.statement_window(e)][0]
        items = R.body_json(first)
        self.assertTrue(any(i.get('completedTime', i['time']) < i['time'] for i in items))

    def test_fop_negative_amounts_are_marked_documentary(self):
        self.assertIn('документальний', SCN[('mono-fop', 'СинтСтатусы')].title)

    def test_day_boundary_scenarios_are_marked(self):
        marked = [k for k in SCN if k[1].startswith('СинтВремя')]
        self.assertTrue(marked)
        for key in marked:
            self.assertIn('у run1 0 операцій у 00:00-02:59', SCN[key].title, key)

    def test_429_scenarios_are_marked_documentary(self):
        marked = [k for k in SCN if k[1].startswith('СинтЛимит429')]
        self.assertTrue(marked)
        for key in marked:
            self.assertIn('документальний', SCN[key].title, key)


class OrderWithinTheSameMoment(unittest.TestCase):
    @staticmethod
    def ops(order):
        base = [{'ПорядковыйНомер': i, 'ДатаОперации': '2026-10-15T10:00:00', 'ИдентификаторОперации': k}
                for i, k in enumerate(order, 1)]
        return base + [{'ПорядковыйНомер': 9, 'ДатаОперации': '2026-10-15T10:01:00', 'ИдентификаторОперации': 'z'}]

    def test_swap_inside_one_moment_is_equal(self):
        self.assertTrue(E.ops_equal_ignoring_order_within_moment(self.ops('ab'), self.ops('ba')))

    def test_control_other_content_or_other_moment_order_is_different(self):
        self.assertFalse(E.ops_equal_ignoring_order_within_moment(self.ops('ab'), self.ops('ac')))
        a = self.ops('ab')
        self.assertFalse(E.ops_equal_ignoring_order_within_moment(a, [a[2], a[0], a[1]]))

    def test_recorded_page_order_is_what_the_etalon_fixes(self):
        s = SCN[('privat', 'СинтСтраницыСлед')]
        e = E.run(s.recording(), s.params)
        self.assertEqual([o['ПорядковыйНомер'] for o in e.ops], list(range(1, 10)))


if __name__ == '__main__':
    unittest.main()
