# -*- coding: utf-8 -*-
"""Правила раунду 1 задачі 2: класи відмов за принципом «чи допоможе повтор», автентифікація при 200 + ERROR, порядок
фільтра статусів і дедуплікації, дублі ПриватБанку, межа довіри (D36 п. 10), перелік валют як у BSL, пояс сеансу,
сторож на згенерованому. Дані синтетичні."""
import os
import re
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import common as C, expected as E, leakguard, oracle_old as O, recording as R, synth as S
from apilib.common import Params
from sslib import guard

from test_api_oracle import DAY, IBAN, OWN14, corp, fop, mono, privat, tx

SCN = {(s.bank, s.sid): s for s in S.all_scenarios()}


def run(bank, sid, **kw):
    s = SCN[(bank, sid)]
    return s, E.run(s.recording(), replace(s.params, **kw) if kw else s.params)


class FailureClasses(unittest.TestCase):
    def privat_error(self, body):
        p = Params(account=IBAN, period_start=DAY, period_end=datetime(2026, 10, 15, 23, 59, 59))
        b = S.Builder('privat', 't', p)
        b.settings(S.resp_json(200, S.privat_settings_body()))
        b.privat(S.resp_json(200, body))
        return E.run(R.Recording(R.make_manifest('privat', 't', b.ex), b.ex), p)

    def test_privat_error_at_200_is_classified_by_content(self):
        base = {'status': 'ERROR', 'type': 'transactions', 'message': 'm'}
        cases = [(dict(base, code='401', serviceCode='CLIENT_AUTH_P24_NOT_VALID'), E.CLS_HUMAN),
                 (dict(base, serviceCode='CLIENT_AUTH'), E.CLS_HUMAN),
                 (dict(base, serviceCode='CLIENT_AUTH_BADSESSION', code='500'), E.CLS_HUMAN),
                 (dict(base, code='403'), E.CLS_HUMAN), (dict(base, code='422', serviceCode='X'), E.CLS_HUMAN),
                 (dict(base, code='408'), E.CLS_RETRY), (dict(base, code='429', serviceCode='X'), E.CLS_RETRY),
                 (dict(base, code='500', serviceCode='SERVICE_ERROR_LOCAL_JOURNAL'), E.CLS_RETRY),
                 (dict(base), E.CLS_RETRY), (dict(base, code='503'), E.CLS_RETRY)]
        for body, cls in cases:
            e = self.privat_error(body)
            self.assertEqual((e.failure_class, e.complete, e.trust), (cls, False, DAY), body)
            self.assertEqual(e.diags[0]['Уровень'], 'Предупреждение')

    def test_synthetic_pair(self):
        self.assertEqual(run('privat', 'СинтОшибкаСтатус')[1].failure_class, E.CLS_RETRY)
        s, e = run('privat', 'СинтОшибкаАвторизация')
        self.assertEqual((e.failure_class, e.diags[0]['Факты']['КодСервиса']), (E.CLS_HUMAN, 'CLIENT_AUTH_P24_NOT_VALID'))

    def test_http_principle_does_retry_help(self):
        mk = lambda st: {'failure': None, 'response': {'status': st}, 'request': {}}
        with mock.patch.object(C, 'error_description', lambda ex: ''):
            for st, cls in ((408, E.CLS_RETRY), (429, E.CLS_RETRY), (500, E.CLS_RETRY), (502, E.CLS_RETRY), (504, E.CLS_RETRY),
                            (401, E.CLS_HUMAN), (403, E.CLS_HUMAN), (400, E.CLS_HUMAN), (404, E.CLS_HUMAN), (422, E.CLS_HUMAN)):
                self.assertEqual(E.rule_failure_class('mono-corp', mk(st))[0], cls, st)
        self.assertEqual(E.rule_failure_class('privat', {'failure': {'kind': 'timeout', 'text': ''}, 'response': None})[0], E.CLS_RETRY)

    def test_every_failure_row_is_a_warning_and_boundary_is_period_start(self):
        for s in SCN.values():
            e = E.run(s.recording(), s.params)
            if e.failure_class:
                self.assertEqual(e.trust, s.params.period_start, s.name)
                self.assertFalse(e.complete)
                for d in e.diags:
                    if d['Суть'] in ('read-failed', 'account-not-found', 'work-balance'):
                        self.assertEqual(d['Уровень'], 'Предупреждение', s.name)
        e = run('privat', 'СинтБезСледующей')[1]
        self.assertEqual((e.failure_class, e.diags[-1]['Уровень']), (E.CLS_RETRY, 'Предупреждение'))

    def test_error_level_only_for_operations_that_cannot_be_presented(self):
        allowed = {'reversal-state-change', 'unknown-state', 'unknown-direction', 'unknown-currency', 'bad-amount', 'bad-date',
                   'conflicting-duplicate'}
        for s in SCN.values():
            for d in E.run(s.recording(), s.params).diags:
                if d['Уровень'] == 'Ошибка':
                    self.assertIn(d['Суть'], allowed, s.name)
                    self.assertGreater(d['ПорядковыйНомер'], 0)


def corp_two_pages(extra_first, second, balances=True):
    """Юросіб: повна сторінка 500 (`extra_first` — найраніший запис, зсув межі) і друга сторінка `second`."""
    p = Params(account=IBAN, period_start=DAY, period_end=datetime(2026, 10, 15, 23, 59, 59), old_account_currency='980')
    base = S.utc(2026, 10, 15, 6)
    page1 = [corp('f%03d' % i, base + 10 + 10 * i, -1) for i in range(499)] + [dict(extra_first, time=base)]
    b = S.Builder('mono-corp', 't', p)
    b.statement(S.to_unix(p.period_start), S.to_unix(p.period_end), S.resp_json(200, sorted(page1, key=lambda x: -x['time'])))
    b.statement(S.to_unix(p.period_start), S.next_to(base), S.resp_json(200, second))
    if balances:
        b.balances(S.resp_json(200, S.corp_balances_body(p)))
    return R.Recording(R.make_manifest('mono-corp', 't', b.ex), b.ex), p


class Dedupe(unittest.TestCase):
    T = S.utc(2026, 10, 15, 6)

    def test_status_filter_before_dedupe_pending_then_done(self):
        rec, p = corp_two_pages(corp('X', self.T, -500, status='PENDING'), [corp('X', self.T, -500, completedTime=self.T + 50)])
        e = E.run(rec, p)
        self.assertEqual(len(e.ops), 500)                                # 499 + завершена X
        self.assertIn('X', [o['НомерДокумента'] for o in e.ops])
        self.assertEqual([(d['Суть'], d['Уровень']) for d in e.diags], [('nonfinal', 'Предупреждение')])
        old = O.run(rec, p)
        self.assertIn('X', [r.fields['НомерДокумента'] for r in old.rows])   # як у попередника (MU:309-323)

    def test_identical_duplicate_is_one_operation(self):
        item = corp('X', self.T, -500, completedTime=self.T + 50)
        e = E.run(*corp_two_pages(item, [item]))
        self.assertEqual((len(e.ops), e.duplicates), (500, 1))

    def test_same_id_other_content_is_an_error_not_a_merge(self):
        e = E.run(*corp_two_pages(corp('X', self.T, -500), [corp('X', self.T, -900)]))
        self.assertEqual([(d['Суть'], d['Уровень']) for d in e.diags], [('conflicting-duplicate', 'Ошибка')])
        self.assertEqual(len([o for o in e.ops if o['НомерДокумента'] == 'X']), 1)

    def test_fop_hold_then_final_same_id(self):
        p = Params(account=IBAN, period_start=DAY, period_end=datetime(2026, 10, 15, 23, 59, 59), old_account_currency='980')
        base = S.utc(2026, 10, 15, 6)
        page1 = [fop('f%03d' % i, base + 10 + 10 * i, -1) for i in range(499)] + [fop('X', base, -5, hold=True)]
        b = S.Builder('mono-fop', 't', p)
        b.p_acct = 'acc-id'
        b.client_info(S.resp_json(200, {'accounts': [{'id': 'acc-id', 'iban': IBAN}]}))
        b.statement(S.to_unix(p.period_start), S.to_unix(p.period_end), S.resp_json(200, sorted(page1, key=lambda x: -x['time'])))
        b.statement(S.to_unix(p.period_start), S.next_to(base), S.resp_json(200, [fop('X', base, -5)]))
        e = E.run(R.Recording(R.make_manifest('mono-fop', 't', b.ex), b.ex), p)
        self.assertIn('X', [o['НомерДокумента'] for o in e.ops])

    def test_privat_duplicates_by_chosen_identifier_only(self):
        a = tx(tid='1', ref='RA')
        rec, p = privat([([a, tx(tid='2', ref='RB')], 'n1'), ([a, tx(tid='3', ref='RC')], None)])
        e = E.run(rec, p)
        self.assertEqual((len(e.ops), e.duplicates), (3, 1))
        # стабільного ідентифікатора немає (ДаетИдентификаторыОперации = Ложь): за вмістом не зливаємо, видимий дубль
        e = E.run(rec, replace(p, privat_id=None))
        self.assertEqual((len(e.ops), e.duplicates, [d['Суть'] for d in e.diags]), (4, 0, []))
        # той самий ідентифікатор, інший вміст (не реверс) — помилка, а не злиття
        rec, p = privat([([tx(tid='1', ref='RA', amount='1.00'), tx(tid='2', ref='RA', amount='2.00')], None)])
        e = E.run(rec, p)
        self.assertEqual(([d['Суть'] for d in e.diags], len(e.ops)), (['conflicting-duplicate'], 1))

    def test_privat_pending_then_final_same_id_is_not_a_conflict(self):
        rec, p = privat([([tx(tid='1', ref='RA', state='p')], 'n1'), ([tx(tid='9', ref='RA', state='r')], None)])
        e = E.run(rec, p)
        self.assertEqual(([o['ПорядковыйНомер'] for o in e.ops], [d['Суть'] for d in e.diags]), ([2], ['nonfinal']))

    def test_synthetic_same_operation_on_two_pages(self):
        s, e = run('privat', 'СинтДубль')
        self.assertEqual((len(e.ops), e.duplicates), (3, 1))
        self.assertEqual(len({o['ИдентификаторОперации'] for o in e.ops}), 3)


class IdentifierStability(unittest.TestCase):
    """p -> r: ті самі REF/REFN, а TECHNICAL_TRANSACTION_ID змінився (гіпотеза _online -> підсумкова виписка)."""

    def test_two_variants_are_distinguishable(self):
        s1, e1 = run('privat', 'СинтСтатусы')
        s2, e2 = run('privat', 'СинтПовтор')
        pending = [d for d in e1.diags if d['Суть'] == 'nonfinal'][0]['Факты']['Ид']
        self.assertEqual(pending, 'DNPENDAB2CDE1A1')
        self.assertIn(pending, [o['ИдентификаторОперации'] for o in e2.ops])
        t1 = [d for d in E.run(s1.recording(), replace(s1.params, privat_id='TECHNICAL_TRANSACTION_ID')).diags
              if d['Суть'] == 'nonfinal'][0]['Факты']['Ид']
        t2 = [o['ИдентификаторОперации'] for o in E.run(s2.recording(), replace(s2.params, privat_id='TECHNICAL_TRANSACTION_ID')).ops]
        self.assertNotIn(t1, t2)


class WorkBalance(unittest.TestCase):
    def test_regulation_of_the_bank_means_no_transaction_requests(self):
        s, e = run('privat', 'СинтРегламентБанка')
        self.assertEqual(len(s.exchanges), 1)                                   # лише /settings
        self.assertEqual((e.failure_class, e.complete, e.trust, e.ops, e.items), (E.CLS_RETRY, False, s.params.period_start, [], 0))
        self.assertEqual([(d['Суть'], d['Уровень'], d['Факты']['Вид']) for d in e.diags],
                         [('work-balance', 'Предупреждение', 'work-balance')])

    def test_n_means_reading_proceeds(self):
        self.assertTrue(run('privat', 'СинтСтатусы')[1].complete)
        self.assertFalse(E.rule_work_balance({'work_balance': 'N'}))
        self.assertTrue(E.rule_work_balance({'work_balance': ' y '}))

    def test_predecessor_never_checked_it(self):
        bsl = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'SMP_BankExchange_SMB', 'cfe', 'src',
                           'CommonModules', 'СМП_РаботаСБанкамиПриватБанкAPIСервер', 'Ext', 'Module.bsl')
        with open(bsl, encoding='utf-8-sig') as f:
            self.assertNotIn('work_balance', f.read())


class TrustBoundary(unittest.TestCase):
    def test_privat_final_date_is_the_boundary(self):
        s, e = run('privat', 'СинтГраницаПриват')
        self.assertEqual(e.trust, datetime(2026, 10, 14))              # p лише 15.10 12:00 — межу задає банк
        _, e = run('privat', 'СинтГраницаПриват', privat_final_date_inclusive=True)
        self.assertEqual(e.trust, datetime(2026, 10, 15))              # день date_final_statement остаточний — межа пізніше

    def test_earliest_of_period_end_nonfinal_and_bank(self):
        rec, p = privat([([tx(state='p', when=datetime(2026, 10, 15, 3))], None)], final='16.10.2026 00:00:00')
        self.assertEqual(E.run(rec, p).trust, datetime(2026, 10, 15, 3))             # неостаточна раніше за все
        rec, p = privat([([tx()], None)], final='16.10.2026 00:00:00')
        self.assertEqual(E.run(rec, p).trust, p.period_end)                         # банк пізніше за кінець періоду
        rec, p = privat([([tx()], None)], final='15.10.2026 00:00:00')
        self.assertEqual(E.run(rec, p).trust, datetime(2026, 10, 15))               # банк раніше за кінець

    def test_boundary_not_earlier_than_period_start(self):
        rec, p = privat([([tx()], None)], final='01.10.2026 00:00:00')
        self.assertEqual(E.run(rec, p).trust, p.period_start)

    def test_corp_hole_boundary_is_first_nonfinal_day_start(self):
        s, e = run('mono-corp', 'СинтГраницаДыра')
        self.assertEqual(e.trust, datetime(2026, 10, 15))               # а не кінець останнього остаточного (16.10 24:00)

    def test_mutation_last_final_day_is_red_exactly_on_the_hole(self):
        def last_final(balances, p):
            days = sorted(b['date'] for b in balances if b.get('isFinal') is True)
            if not days:
                return None
            return datetime.strptime(days[-1], '%Y-%m-%d') + timedelta(days=1)
        changed = []
        for s in SCN.values():
            if s.bank != 'mono-corp':
                continue
            base = E.run(s.recording(), s.params).trust
            with mock.patch.object(E, 'rule_bank_boundary_corp', last_final):
                mut = E.run(s.recording(), s.params).trust
            if base != mut:
                changed.append(s.sid)
        self.assertEqual(changed, ['СинтГраницаДыра'])

    def test_corp_absent_day_interpretation_and_all_final(self):
        s = SCN[('mono-corp', 'СинтГраницаДыра')]
        body = S.corp_balances_body(s.params, absent=['2026-10-14'])
        self.assertEqual(E.rule_bank_boundary_corp(body, s.params), datetime(2026, 10, 14))
        self.assertIsNone(E.rule_bank_boundary_corp(body, replace(s.params, corp_absent_day_is_final=True,
                                                                   period_start=datetime(2026, 10, 16))))
        self.assertIsNone(E.rule_bank_boundary_corp(S.corp_balances_body(s.params), s.params))

    def test_fop_has_only_hold(self):
        s, e = run('mono-fop', 'СинтСтатусы')
        self.assertIsNone(e.bank_boundary)
        self.assertEqual(e.trust, min(e.nonfinal))

    def test_exchange_failure_of_settings_and_balances(self):
        s, e = run('privat', 'СинтНастройкиСбой')
        self.assertEqual((e.failure_class, e.trust, e.ops, len(s.exchanges)), (E.CLS_RETRY, s.params.period_start, [], 1))
        s, e = run('privat', 'СинтТокен401')
        self.assertEqual(e.failure_class, E.CLS_HUMAN)
        s, e = run('mono-corp', 'СинтБалансыСбой')
        self.assertEqual((e.failure_class, len(e.ops), e.complete, e.trust), (E.CLS_RETRY, 1, False, s.params.period_start))

    def test_all_synthetic_privat_requests_start_with_settings(self):
        for s in SCN.values():
            if s.bank == 'privat':
                self.assertEqual(s.exchanges[0]['request']['path'], C.PRIVAT_SETTINGS_PATH, s.name)

    def test_etalon_marks_interpretation_dependency(self):
        from apilib import etalon
        for key in (('privat', 'СинтГраницаПриват'), ('mono-corp', 'СинтГраницаДыра')):
            self.assertIn('ТлумачениеГраницы', etalon.build(SCN[key])[0]['dependsOn'])


BSL = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'SMP_BankExchange_SMB', 'cfe', 'src',
                   'CommonModules', 'СМП_ЧтениеВыписокОбщее', 'Ext', 'Module.bsl')


def bsl_currency_table(path=BSL):
    with open(path, encoding='utf-8-sig') as f:
        text = f.read()
    m = re.search(r'Функция ТаблицаКодовВалют\(\)(.*?)КонецФункции', text, re.S)
    return dict(re.findall(r'Таблица\.Вставить\("([A-Z]{3})",\s*"(\d{3})"\)', m.group(1)))


class CurrencyList(unittest.TestCase):
    """Перелік оракула — той самий, що знає 1С-функція `ЧисловойКодВалюты`; джерело одне (BSL)."""

    def test_oracle_list_equals_bsl_list(self):
        self.assertEqual(C.ISO4217, bsl_currency_table())

    def test_control_extra_code_is_red(self):
        with mock.patch.dict(C.ISO4217, {'CAD': '124'}):
            self.assertNotEqual(C.ISO4217, bsl_currency_table())
        with mock.patch.dict(C.ISO4217, {'GBP': '827'}):
            self.assertNotEqual(C.ISO4217, bsl_currency_table())

    def test_behaviour_like_the_function(self):
        self.assertEqual([C.numeric_currency(x) for x in (' usd ', '980', '', 'EUR', 'CAD', '124', 'UA', None)],
                         ['840', '980', '', '978', None, None, None, ''])

    def test_unknown_code_is_an_error_row(self):
        rec, p = privat([([tx(ccy='CAD', tid='1'), tx(ccy='USD', tid='2')], None)], old_account_currency=None)
        e = E.run(rec, p)
        self.assertEqual(([o['Валюта'] for o in e.ops], [d['Суть'] for d in e.diags]), (['840'], ['unknown-currency']))
        rec, p = mono('mono-fop', [fop('a', S.utc(2026, 10, 15, 8), -100, currencyCode=124)])
        self.assertEqual([d['Суть'] for d in E.run(rec, p).diags], ['unknown-currency'])

    def test_synthetic_records_use_only_listed_codes(self):
        for s in SCN.values():
            e = E.run(s.recording(), s.params)
            self.assertFalse([d for d in e.diags if d['Суть'] == 'unknown-currency'], s.name)
            self.assertTrue(all(o['Валюта'] in set(C.ISO4217.values()) | {''} for o in e.ops), s.name)


class SessionZone(unittest.TestCase):
    def test_unknown_zone_raises(self):
        with self.assertRaises(ValueError):
            C.session_local(0, 'Europe/Warsaw')
        rec, p = mono('mono-fop', [fop('a', S.utc(2026, 10, 15, 8), -100)])
        with self.assertRaises(ValueError):
            O.run(rec, replace(p, old_session_tz='Europe/Warsaw'))


class LeakGuard(unittest.TestCase):
    def test_clean_and_leaking(self):
        s = SCN[('privat', 'СинтСтатусы')]
        planted = s.params.account[-14:]                       # «сира» лексема, яка справді є у згенерованому
        n, bad = leakguard.scan_generated({planted}, {'Нікчемність'})
        self.assertGreater(n, 100)
        self.assertGreater(len(bad), 0)                        # контроль: сторож знаходить
        n, bad = leakguard.scan_generated({'99999999999999'}, {'Нікчемність'})
        self.assertEqual(bad, {})

    def test_control_can_fail(self):
        self.assertTrue(leakguard.control({'12345678901'}, {'Вигадане'}))
        self.assertFalse(leakguard.control(set(), set()))        # порожній лексикон: сторож нічого не вміє знаходити

    def test_allowed_words_live_in_a_separate_api_list(self):
        cfg = leakguard.api_config()
        from sslib import cfg as cfgmod
        shared = cfgmod.load()
        self.assertNotIn('ПриватБанк', shared['guard_allowed_words'])
        self.assertIn('ПриватБанк', cfg['guard_allowed_words'])


if __name__ == '__main__':
    unittest.main()
