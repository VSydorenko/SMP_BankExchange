# -*- coding: utf-8 -*-
"""Оракул (`apilib/oracle_old.py`, `apilib/expected.py`) на малих записах, побудованих тут. Очікування — літерали, що
випливають з коду попередників (рядки модулів — у `oracle_old.ASSUMPTIONS`) і з рішень плану. Дані синтетичні."""
import os
import sys
import unittest
from dataclasses import replace
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import expected as E, kyiv, oracle_old as O, recording as R, synth as S
from apilib import common as C
from apilib.common import Params

OWN14 = '26001234567890'
BBAN = '305299' + OWN14.rjust(19, '0')
import sslib.gen as sg
IBAN = 'UA' + sg.iban_check_digits('UA', BBAN) + BBAN
DAY = datetime(2026, 10, 15)


def tx(when=datetime(2026, 10, 15, 10, 0, 0), tran='C', state='r', amount='10.00', own=IBAN, cnt='26009999999999',
       ccy='UAH', num='N1', ref=None, refn='1', tid='111', osnd='призначення', **kw):
    ref = ref or 'REF' + tid
    d = {'AUT_MY_ACC': own, 'AUT_CNTR_ACC': cnt, 'AUT_CNTR_NAM': 'Контрагент', 'AUT_CNTR_CRF': '12345678', 'AUT_CNTR_MFO': '305299',
         'CCY': ccy, 'PR_PR': state, 'NUM_DOC': num, 'OSND': osnd, 'SUM': amount, 'REF': ref, 'REFN': refn,
         'DATE_TIME_DAT_OD_TIM_P': when.strftime('%d.%m.%Y %H:%M:%S'), 'ID': tid, 'TRANTYPE': tran,
         'TECHNICAL_TRANSACTION_ID': tid}                 # run1: ID = TECHNICAL_TRANSACTION_ID
    d.update(kw)
    return d


def privat(pages, flags=None, absent=(), balance=True, settings=True, **kw):
    """Читання ПриватБанку: сторінки транзакцій (кожна -- список; пара `(список, _)` теж приймається) і `/balance`."""
    p = Params(**{'account': IBAN, 'period_start': DAY, 'period_end': datetime(2026, 10, 15, 23, 59, 59),
                  'old_account_currency': '980', **kw})
    b = S.Builder('privat', 't', p)
    if settings:
        b.settings(S.resp_json(200, S.privat_settings_body(work_balance=settings if isinstance(settings, str) else 'N')))
    b.privat_pages([x[0] if isinstance(x, tuple) else x for x in pages])
    if balance:
        b.privat_balance(S.resp_json(200, S.privat_balance_body(p, flags, absent)))
    return R.Recording(R.make_manifest('privat', 't', b.ex), b.ex), p


def mono(bank, items, start=DAY, end=datetime(2026, 10, 15, 23, 59, 59), flags=None, **kw):
    iban = IBAN
    p = Params(**{'account': iban, 'period_start': start, 'period_end': end, 'old_account_currency': '980', **kw})
    b = S.Builder(bank, 't', p)
    b.p_acct = 'acc-id'
    if bank == 'mono-fop':
        b.client_info(S.resp_json(200, {'accounts': [{'id': 'acc-id', 'iban': iban}]}))
    b.statement(S.to_unix(start), S.to_unix(end), S.resp_json(200, sorted(items, key=lambda x: -x['time'])))
    if bank == 'mono-corp':
        b.balances(S.resp_json(200, S.corp_balances_body(p, flags)))
    return R.Recording(R.make_manifest(bank, 't', b.ex), b.ex), p


def fop(id, t, amount, **kw):
    d = {'id': id, 'time': t, 'description': 'd', 'hold': False, 'amount': amount, 'currencyCode': 980, 'commissionRate': 0,
         'cashbackAmount': 0}
    d.update(kw)
    return d


def corp(id, t, amount, **kw):
    d = {'id': id, 'time': t, 'description': 'd', 'amount': amount, 'currencyCode': '980', 'reverse': False, 'status': 'DONE'}
    d.update(kw)
    return d


class OldPrivat(unittest.TestCase):
    def test_key_fields(self):
        rec, p = privat([([tx(tran='D', amount='12.50', num='X9', cnt='26005555555555')], None)])
        r = O.run(rec, p).rows[0].fields
        self.assertEqual((r['ДатаДокумента'], r['НомерДокумента'], r['КонтрагентНомерСчета'], r['Сумма']),
                         (datetime(2026, 10, 15, 10, 0), 'X9', '26005555555555', Decimal('12.50')))

    def test_everything_is_loaded_regardless_of_pr_pr(self):
        rec, p = privat([([tx(state=s, tid=str(i)) for i, s in enumerate('rptn')], None)])
        self.assertEqual(len(O.run(rec, p).rows), 4)       # PB: PR_PR не читається

    def test_foreign_account_is_dropped_without_trace(self):
        rec, p = privat([([tx(own=S.Gen('x').iban())], None)])
        res = O.run(rec, p)
        self.assertEqual((len(res.rows), [d[0] for d in res.dropped]), (0, ['foreign-account']))

    def test_account_in_base_is_iban_and_comparison_is_exact(self):
        """run1: AUT_MY_ACC -- IBAN (87 з 87), у базі теж IBAN (слова власника): рядок з IBAN завантажується; рядок із 14 цифрами
        (форми в run1 немає) відкидає регламентний фільтр, як PB:510."""
        rec, p = privat([([tx(tran='D'), tx(tran='C', tid='2')], None)])
        res = O.run(rec, p)
        self.assertEqual(len(res.rows), 2)
        self.assertTrue(res.rows[0].fields['Исходящий'])
        rec, p = privat([([tx(own=OWN14)], None)])
        res = O.run(rec, p)
        self.assertEqual((len(res.rows), [d[0] for d in res.dropped]), (0, ['regulation-filter']))

    def test_regulation_currency_filter(self):
        rec, p = privat([([tx(ccy='UAH')], None)])
        self.assertEqual(len(O.run(rec, replace(p, old_account_currency='840')).rows), 0)
        self.assertEqual(len(O.run(rec, replace(p, old_account_currency=None)).rows), 1)    # валюта рахунку не заповнена

    def test_error_and_missing_next_page_id_abort_everything(self):
        b = S.Builder('privat', 't', Params(account=IBAN, period_start=DAY, period_end=DAY))
        b.privat(S.resp_json(200, S.privat_page([tx()], exist=True)))
        b.privat(S.resp_json(200, {'status': 'ERROR', 'message': 'boom'}), follow='111')
        rec = R.Recording(R.make_manifest('privat', 't', b.ex), b.ex)
        res = O.run(rec, Params(account=IBAN, period_start=DAY, period_end=DAY))
        self.assertEqual((res.rows, res.error['kind']), ([], 'exception'))
        p = Params(account=IBAN, period_start=DAY, period_end=DAY)
        b = S.Builder('privat', 't', p)
        b.privat(S.resp_json(200, S.privat_page([tx()], exist=True, with_id=False)))          # exist_next_page = true без next_page_id
        rec = R.Recording(R.make_manifest('privat', 't', b.ex), b.ex)
        self.assertEqual(O.run(rec, p).error['kind'], 'hang')


class OldMono(unittest.TestCase):
    def test_fop_hold_is_skipped_and_duplicates_dropped(self):
        t = S.utc(2026, 10, 15, 8)
        rec, p = mono('mono-fop', [fop('a', t, -100), fop('b', t + 1, 200, hold=True), fop('a', t, -100)])
        res = O.run(rec, p)
        self.assertEqual([r.fields['НомерДокумента'] for r in res.rows], ['a'])
        self.assertEqual(sorted(d[0] for d in res.dropped), ['duplicate-id', 'hold'])

    def test_corp_only_done_without_reverse_and_completed_time_wins(self):
        t = S.utc(2026, 10, 15, 8)
        items = [corp('1', t, 1000, completedTime=t + 100), corp('2', t + 1, 1, status='PENDING'),
                 corp('3', t + 2, 1, status='DECLINED'), corp('4', t + 3, 1, reverse=True), corp('5', t + 4, 1, status=None)]
        for d in items:
            if d['status'] is None:
                del d['status']
        rec, p = mono('mono-corp', items)
        res = O.run(rec, p)
        self.assertEqual([r.fields['НомерДокумента'] for r in res.rows], ['1'])
        self.assertEqual(res.rows[0].fields['ДатаДокумента'], kyiv.unix_to_local(t + 100))

    def test_day_is_local_not_utc(self):
        t = S.utc(2026, 10, 14, 22, 30)                    # 14.10 ще літній час (UTC+3): 22:30Z = 01:30 15.10 за Києвом
        rec, p = mono('mono-fop', [fop('a', t, -100)])
        local = O.run(rec, p).rows[0].fields['ДатаДокумента']
        self.assertEqual(local, datetime(2026, 10, 15, 1, 30, 0))          # 14.10 22:30Z -> літній час (до 25.10) = +3
        utc_base = O.run(rec, replace(p, old_session_tz='UTC')).rows[0].fields['ДатаДокумента']
        self.assertEqual(utc_base, datetime(2026, 10, 14, 22, 30, 0))      # база не в київському поясі: інша доба

    def test_amount_has_no_rounding_and_sign_is_dropped(self):
        rec, p = mono('mono-fop', [fop('a', S.utc(2026, 10, 15, 8), -123456)])
        self.assertEqual(O.run(rec, p).rows[0].fields['Сумма'], Decimal('1234.56'))

    def test_purpose_composition_and_truncation(self):
        t = S.utc(2026, 10, 15, 8)
        item = fop('a', t, -100, description='  опис ', comment=' коментар ', commissionRate=1050, cashbackAmount=2000)
        rec, p = mono('mono-fop', [item])
        self.assertEqual(O.run(rec, p).rows[0].fields['НазначениеПлатежа'], 'опис\nкоментар Сума комісії 10,5 Кешбек 20')
        item = fop('b', t, -100, description='я' * 300)
        rec, p = mono('mono-fop', [item])
        self.assertEqual(len(O.run(rec, p).rows[0].fields['НазначениеПлатежа']), 255)

    def test_missing_comment_does_not_add_the_word_undefined(self):
        rec, p = mono('mono-fop', [fop('a', S.utc(2026, 10, 15, 8), -100)])
        self.assertNotIn('Неопределено', O.run(rec, p).rows[0].fields['НазначениеПлатежа'])


class Expected(unittest.TestCase):
    def test_privat_states_and_boundary(self):
        rec, p = privat([([tx(tid='1'), tx(state='p', tid='2', when=datetime(2026, 10, 15, 12, 0)),
                           tx(state='n', tid='3'), tx(state='t', tid='4', ref='R4')], None)])      # баланси за період усі остаточні
        e = E.run(rec, p)
        self.assertEqual([o['ПорядковыйНомер'] for o in e.ops], [1, 4])
        self.assertEqual([(d['Уровень'], d['Суть']) for d in e.diags], [('Предупреждение', 'nonfinal'), ('Предупреждение', 'cancelled')])
        self.assertEqual(e.trust, datetime(2026, 10, 15, 12, 0))

    def test_reversal_case_a_and_b(self):
        rec, p = privat([([tx(tid='1', ref='RA', refn='1'), tx(state='t', tid='2', ref='RB', refn='1'),     # (а): свій ID
                           tx(state='t', tid='1', ref='RA', refn='1', TECHNICAL_TRANSACTION_ID='1x')], None)])   # (б): ID оригіналу
        e = E.run(rec, p)
        self.assertEqual([o['ПорядковыйНомер'] for o in e.ops], [1, 2])
        self.assertEqual([(d['Уровень'], d['Суть'], d['ПорядковыйНомер']) for d in e.diags], [('Ошибка', 'reversal-state-change', 3)])
        # той самий запис, але ідентифікатор — TECHNICAL_TRANSACTION_ID (на випадок, не спостерігалось: у run1 він дорівнює ID)
        e2 = E.run(rec, replace(p, privat_id='TECHNICAL_TRANSACTION_ID'))
        self.assertEqual([d['Суть'] for d in e2.diags], [])

    def test_corp_reversal_case_a_and_b(self):
        t = S.utc(2026, 10, 15, 8)
        items = [corp('o', t, -1000), corp('r1', t + 1, 500, reverse=True), corp('o', t + 2, 1000, reverse=True)]
        rec, p = mono('mono-corp', items)
        e = E.run(rec, p)
        self.assertEqual(sorted((o['НомерДокумента'], o['Направление']) for o in e.ops),
                         [('o', 'Списано'), ('r1', 'Поступило')])
        self.assertEqual([d['Суть'] for d in e.diags], ['reversal-state-change'])

    def test_failure_classes_and_partial_read_is_kept(self):
        def run_with(resp=None, failure=None):
            p = Params(account=IBAN, period_start=DAY, period_end=datetime(2026, 10, 15, 23, 59, 59), old_account_currency='980')
            b = S.Builder('mono-corp', 't', p)
            page = [corp('p%03d' % i, S.utc(2026, 10, 15, 6) + 3 * i, -(i + 1)) for i in range(C.CORP_WORKING_LIMIT)]
            b.statement(S.to_unix(p.period_start), S.to_unix(p.period_end), S.resp_json(200, sorted(page, key=lambda x: -x['time'])))
            b.statement(S.to_unix(p.period_start), S.next_to(min(x['time'] for x in page)), resp, failure)
            return E.run(R.Recording(R.make_manifest('mono-corp', 't', b.ex), b.ex), p)
        cases = [(S.resp_json(500, {'errorDescription': 'x'}), None, 'Повторить'), (S.resp_html(200), None, 'Повторить'),
                 (S.resp_json(503, {}), None, 'Повторить'), (S.resp_json(403, {'errorDescription': 'no'}), None, 'ДействиеЧеловека'),
                 (S.resp_json(404, {}), None, 'ДействиеЧеловека'), (None, {'kind': 'timeout', 'text': 't'}, 'Повторить'),
                 (S.resp_json(408, {}), None, 'Повторить'), (S.resp_json(401, {}), None, 'ДействиеЧеловека'),
                 (S.resp_json(400, {}), None, 'ДействиеЧеловека'), (S.resp_json(422, {}), None, 'ДействиеЧеловека')]
        for resp, fail, cls in cases:
            e = run_with(resp, fail)
            self.assertEqual((e.failure_class, e.complete, len(e.ops), e.trust), (cls, False, C.CORP_WORKING_LIMIT, DAY), (resp, fail))
            self.assertEqual((e.diags[0]['Суть'], e.diags[0]['Уровень']), ('read-failed', 'Предупреждение'))   # неповне читання, не втрата
            self.assertEqual(e.diags[0]['Факты']['Банк'], 'monobank юросіб')

    def test_zero_amount_is_passed_to_the_platform_not_hidden(self):
        rec, p = mono('mono-fop', [fop('z', S.utc(2026, 10, 15, 8), 0)])
        e = E.run(rec, p)
        self.assertEqual([o['Сумма'] for o in e.ops], ['0.00'])

    def test_unknown_values_are_diagnostics_not_guesses(self):
        rec, p = privat([([tx(state='x', tid='1'), tx(tran='?', tid='2'), tx(ccy='XXX', tid='3'), tx(amount='abc', tid='4')], None)])
        e = E.run(rec, p)
        self.assertEqual(e.ops, [])
        self.assertEqual([d['Суть'] for d in e.diags], ['unknown-state', 'unknown-direction', 'unknown-currency', 'bad-amount'])

    def test_currency_letter_code_goes_through_shared_parser(self):
        rec, p = privat([([tx(ccy='USD'), tx(ccy='EUR', tid='2'), tx(ccy='UAH', tid='3')], None)], old_account_currency=None)
        self.assertEqual([o['Валюта'] for o in E.run(rec, p).ops], ['840', '978', '980'])

    def test_purpose_is_not_truncated(self):
        rec, p = mono('mono-fop', [fop('a', S.utc(2026, 10, 15, 8), -100, description='я' * 300)])
        self.assertEqual(len(E.run(rec, p).ops[0]['НазначениеПлатежа']), 300)

    def test_pauses_are_technical_only(self):
        # /settings + 2 сторінки + /balance: пауза після кожного обміну, крім останнього
        rec, p = privat([([tx()], 'n1'), ([tx(tid='2')], None)])
        e = E.run(rec, p)
        self.assertEqual(e.pauses, [{'ПослеЗапроса': k, 'Секунд': 1, 'Причина': 'privat-1-per-second'} for k in (1, 2, 3)])
        e0 = E.run(rec, p, {'dev9'})
        self.assertEqual(e0.pauses, [])
        self.assertEqual(e0.ops, e.ops)                    # кількість і зміст операцій від dev9 не залежать


class Conservation(unittest.TestCase):
    """Жодна прочитана операція не зникає мовчки (D3): кожен прочитаний запис — або операція, або рядок діагностики, або
    дубль зі сторінкової межі. Контроль: з вимкненим відступом, що мовчки пропускає, інваріант порушується."""

    @staticmethod
    def accounted(e):
        numbers = [o['ПорядковыйНомер'] for o in e.ops] + [d['ПорядковыйНомер'] for d in e.diags if d['ПорядковыйНомер'] > 0]
        return len(numbers) == len(set(numbers)) and len(numbers) + e.duplicates + e.silent == e.items

    def test_every_synthetic_record_is_accounted_for(self):
        for s in S.all_scenarios():
            e = E.run(s.recording(), s.params)
            self.assertTrue(self.accounted(e), s.name)
            self.assertEqual(e.silent, 0, s.name)

    def test_control_disabled_deviation_hides_records(self):
        s = [x for x in S.all_scenarios() if x.bank == 'mono-corp' and x.sid == 'СинтСтатусы'][0]
        e = E.run(s.recording(), s.params, {'dev2'})
        self.assertGreater(e.silent, 0)                                   # PENDING і DECLINED зникли без сліду
        self.assertLess(len(e.diags), len(E.run(s.recording(), s.params).diags))


if __name__ == '__main__':
    unittest.main()
