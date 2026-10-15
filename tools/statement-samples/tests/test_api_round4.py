# -*- coding: utf-8 -*-
"""Раунд 4 задачі 2: запити й паузи еталона -- лише спожиті обміни (I1); `/settings` -- обов'язковий перший обмін кожного читання
Привата (I2, R14); вузький виняток перевірки (а) за парою полів DLR ⊂ NUM_DOC (I3); кілька рядків балансу за добу. Дані синтетичні."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import common as C, expected as E, readings as RD, recording as R, step2, synth as S
from apilib.common import Params

from test_api_oracle import DAY, IBAN, corp, tx
from test_api_step2 import Env, mutate_body

END = datetime(2026, 10, 15, 23, 59, 59)


def rec_of(bank, b, label='t'):
    return R.Recording(R.make_manifest(bank, label, b.ex), b.ex)


class UnconsumedExchanges(unittest.TestCase):
    """I1: після відмови конектор запитів більше не робить -- обмін балансів, що лежить у записі далі, в еталон не потрапляє."""

    def privat_failed(self):
        p = Params(account=IBAN, period_start=DAY, period_end=END, old_account_currency='980')
        b = S.Builder('privat', 't', p)
        b.settings(S.resp_json(200, S.privat_settings_body()))
        b.privat(S.resp_json(401, S.privat_error_body(401, 'SE004', 'Invalid token')))
        b.privat_balance(S.resp_json(200, S.privat_balance_body(p)))               # у записі є, але конектор його не зробить
        return rec_of('privat', b), p

    def test_privat_failed_read_has_no_balance_request_and_no_pause_before_it(self):
        rec, p = self.privat_failed()
        self.assertEqual(len(rec.exchanges), 3)                                    # передумова: зайвий обмін у записі є
        e = E.run(rec, p)
        self.assertEqual([x['Путь'] for x in e.requests], [C.PRIVAT_SETTINGS_PATH, C.PRIVAT_PATH])
        self.assertEqual([x['ПослеЗапроса'] for x in e.pauses], [1])               # лише між settings і транзакціями
        self.assertEqual(e.failure_class, E.CLS_HUMAN)

    def test_control_the_old_construction_from_all_exchanges_would_be_red(self):
        rec, p = self.privat_failed()
        e = E.run(rec, p)
        from_all = [x['request']['path'] for x in rec.exchanges]
        self.assertNotEqual([x['Путь'] for x in e.requests], from_all)             # контроль: тест уміє розрізнити

    def test_successful_read_still_has_every_request(self):
        p = Params(account=IBAN, period_start=DAY, period_end=END, old_account_currency='980')
        b = S.Builder('privat', 't', p)
        b.settings(S.resp_json(200, S.privat_settings_body()))
        b.privat_pages([[tx()], [tx(tid='2')]])
        b.privat_balance(S.resp_json(200, S.privat_balance_body(p)))
        e = E.run(rec_of('privat', b), p)
        self.assertEqual([x['Путь'] for x in e.requests],
                         [C.PRIVAT_SETTINGS_PATH, C.PRIVAT_PATH, C.PRIVAT_PATH, C.PRIVAT_BALANCE_PATH])
        self.assertEqual([x['ПослеЗапроса'] for x in e.pauses], [1, 2, 3])

    def test_corp_failed_read_has_no_balances_request(self):
        p = Params(account=IBAN, period_start=DAY, period_end=END, old_account_currency='980')
        b = S.Builder('mono-corp', 't', p)
        b.statement(S.to_unix(DAY), S.to_unix(END), S.resp_json(400, {'errorCode': 'BAD_REQUEST', 'errorDescription': 'x'}))
        b.balances(S.resp_json(200, S.corp_balances_body(p)))
        rec = rec_of('mono-corp', b)
        e = E.run(rec, p)
        self.assertEqual(len(rec.exchanges), 2)
        self.assertEqual(len(e.requests), 1)
        self.assertEqual(e.pauses, [])

    def test_every_synthetic_expected_requests_are_consumed_prefix_of_the_record(self):
        for s in S.all_scenarios():
            e = E.run(s.recording(), s.params)
            paths = [x['Путь'] for x in e.requests]
            self.assertEqual(paths, [x['request']['path'] for x in s.exchanges][:len(paths)], s.name)
            if e.failure_class and e.complete is False and not e.ops and s.bank != 'mono-fop':
                self.assertFalse(any(x.endswith('/balance') or x.endswith('/balances') for x in paths), s.name)

    def multi_run(self):
        """Вигаданий запис прогону Привата з кількома сценаріями: settings, баланс, невдале й вдале читання."""
        p = Params(account=IBAN, period_start=DAY, period_end=END, old_account_currency='980')
        b = S.Builder('privat', 't', p)
        b.settings(S.resp_json(200, S.privat_settings_body()))
        b.privat_balance(S.resp_json(200, S.privat_balance_body(p)))
        b.privat(S.resp_json(401, S.privat_error_body(401, 'SE004', 'Invalid token')))
        b.privat_pages([[tx()]])
        names = ['privat_settings', 'privat_a1_balance_period', 'privat_errors_invalid_token', 'privat_a1_tx_work_limit']
        for ex, n in zip(b.ex, names):
            ex['scenario'] = n
        return rec_of('privat', b)

    def test_readings_add_balance_only_after_success_and_settings_always_first(self):
        rd = {r.scenario: r for r in RD.readings(self.multi_run())}
        bad, good = rd['privat_errors_invalid_token'], rd['privat_a1_tx_work_limit']
        paths = lambda r: [x['request']['path'] for x in r.exchanges]
        self.assertEqual(paths(bad), [C.PRIVAT_SETTINGS_PATH, C.PRIVAT_PATH])
        self.assertEqual(paths(good), [C.PRIVAT_SETTINGS_PATH, C.PRIVAT_PATH, C.PRIVAT_BALANCE_PATH])
        e = E.run(bad.recording(), bad.params)
        self.assertEqual(len(e.requests), len(bad.exchanges))                      # еталон невдалого читання -- без зайвого запиту


class SettingsIsMandatory(unittest.TestCase):
    """I2 (R14): конектор Привата читає `/settings` у КОЖНОМУ читанні; його відсутність -- явна помилка еталона, не мовчанка."""

    def test_every_synthetic_privat_reading_starts_with_settings(self):
        for s in S.all_scenarios():
            if s.bank == 'privat':
                self.assertEqual(s.exchanges[0]['request']['path'], C.PRIVAT_SETTINGS_PATH, s.name)
                self.assertEqual([x['request']['path'] for x in s.exchanges].count(C.PRIVAT_SETTINGS_PATH), 1, s.name)

    def test_missing_or_misplaced_settings_is_an_explicit_error(self):
        p = Params(account=IBAN, period_start=DAY, period_end=END, old_account_currency='980')
        b = S.Builder('privat', 't', p)
        b.privat_pages([[tx()]])
        b.privat_balance(S.resp_json(200, S.privat_balance_body(p)))
        with self.assertRaises(E.RecordingMismatch):
            E.run(rec_of('privat', b), p)
        b = S.Builder('privat', 't', p)
        b.privat_pages([[tx()]])
        b.settings(S.resp_json(200, S.privat_settings_body()))  # не першим
        b.privat_balance(S.resp_json(200, S.privat_balance_body(p)))
        with self.assertRaises(E.RecordingMismatch):
            E.run(rec_of('privat', b), p)

    def test_work_balance_y_stops_the_read_after_settings(self):
        p = Params(account=IBAN, period_start=DAY, period_end=END, old_account_currency='980')
        b = S.Builder('privat', 't', p)
        b.settings(S.resp_json(200, S.privat_settings_body(work_balance='Y')))
        b.privat_pages([[tx()]])
        e = E.run(rec_of('privat', b), p)
        self.assertEqual((e.failure_class, e.ops, [x['Путь'] for x in e.requests]), (E.CLS_RETRY, [], [C.PRIVAT_SETTINGS_PATH]))


class MultipleBalanceRowsPerDay(unittest.TestCase):
    """Кілька рядків балансу за ту саму добу (наприклад, кілька валют одного `acc`): день остаточний, лише якщо ВСІ його рядки такі."""

    P = Params(account=IBAN, period_start=datetime(2026, 10, 14), period_end=datetime(2026, 10, 15, 23, 59, 59))

    def test_privat(self):
        row = lambda day, fin: {'dpd': day + ' 00:00:00', 'is_final_bal': fin}
        for order in (True, False):
            rows = [row('14.10.2026', True), row('15.10.2026', True), row('14.10.2026', False)]
            if order:
                rows.reverse()
            self.assertEqual(E.rule_bank_boundary_privat(rows, self.P), datetime(2026, 10, 14), order)
        self.assertIsNone(E.rule_bank_boundary_privat([row('14.10.2026', True), row('14.10.2026', True), row('15.10.2026', True)], self.P))

    def test_corp(self):
        row = lambda day, fin: {'date': day, 'isFinal': fin}
        for rows in ([row('2026-10-14', False), row('2026-10-14', True), row('2026-10-15', True)],
                     [row('2026-10-14', True), row('2026-10-14', False), row('2026-10-15', True)]):
            self.assertEqual(E.rule_bank_boundary_corp(rows, self.P), datetime(2026, 10, 14))
        self.assertIsNone(E.rule_bank_boundary_corp([row('2026-10-14', True), row('2026-10-14', True), row('2026-10-15', True)], self.P))


class NarrowPairException(unittest.TestCase):
    """I3: виняток (а) -- лише для пари полів DLR ⊂ NUM_DOC; значення, що сховалося в іншому KEEP-полі, -- витік."""

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

    def test_pair_is_allowed_counted_and_reported(self):
        r = self.res()
        self.assertEqual(r['hits'], 0)
        self.assertGreaterEqual(r['pair_counts'].get('DLR_in_NUM_DOC', 0), 1)

    def test_the_value_hidden_in_another_keep_field_is_red(self):
        mutate_body(self.env.anon, self.page, lambda s: s.replace('"type":"transactions"', '"type":"%s"' % self.dlr, 1))
        r = self.res()
        self.assertGreater(r['pair_leaks'], 0)
        self.assertGreater(r['hits'], 0)

    def test_the_value_in_num_doc_itself_is_not_a_leak(self):
        first = R.body_json(R.Recording.from_dir(self.env.anon).exchanges[self.page - 1])['transactions'][0]
        mutate_body(self.env.anon, self.page, lambda s: s.replace('"NUM_DOC":"%s"' % first['NUM_DOC'], '"NUM_DOC":"Z%s"' % self.dlr, 1))
        self.assertEqual(self.res()['pair_leaks'], 0)

    def test_without_the_pair_the_same_value_in_keep_is_red(self):
        """Контроль: якщо DLR у сирому записі НЕ є частиною NUM_DOC, його поява в NUM_DOC знеособленого -- уже витік."""
        shutil.rmtree(self.tmp)
        self.tmp = tempfile.mkdtemp()
        self.env = Env('privat', 'СинтСтраницыСлед', self.tmp)
        raw = R.Recording.from_dir(self.env.raw)
        t = R.body_json(raw.exchanges[self.page - 1])['transactions'][0]
        self.env.anonymize()
        mutate_body(self.env.anon, self.page, lambda s: s.replace('"NUM_DOC":"%s"' % t['NUM_DOC'], '"NUM_DOC":"Z%s"' % t['DLR'], 1))
        self.assertGreater(self.res()['hits'], 0)


if __name__ == '__main__':
    unittest.main()
