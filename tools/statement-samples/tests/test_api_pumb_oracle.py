# -*- coding: utf-8 -*-
"""Оракул ПУМБ, режим «очікуване» (задача 2a, Step 2): очікування -- РУКАМИ, зі спеки й рішень плану (відступи 1-8, D36 п. 8, 10, 11), а не з коду оракула.
Усі значення ВИГАДАНІ. «Стара обробка» для ПУМБ не застосовується (рішення власника) -- її контроль у `test_api_oracle.py`. Пагінація й формат дати --
гіпотези до виміру: запит із `pagingRequest` (конектор його не шле, Р4) і інший формат `operationDate` -- явна відмова; кілька запитів `searcher` без `pagingRequest` -- ділення навпіл (тести в `test_api_pumb_synth.py`, ручне очікуване)."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import anonymize as A, common as C, expected as E, readings as RD, recording as R, step2
from apilib.common import Params
from test_api_pumb_anonymize import IBAN, _post, _resp

OTHER = 'UA' + '0' * 27
DAY0, DAY1 = '01.11.2026 00:00:00', '01.11.2026 23:59:59'
ACCT = {'id': 7000123456, 'accountId': 5500123456, 'mfo': '322001', 'currency': 'UAH', 'iban': IBAN, 'clientName': 'Вигадана компанія'}


def doc(n, state='PROCESSED', when='01.11.2026 10:00:00', amount='100.50', out=True, ccy='UAH', **kw):
    d = {'id': 9000 + n, 'docId': 8000 + n, 'state': state, 'type': 'UAH', 'amount': amount, 'currencyCode': ccy, 'operationDate': when,
         'description': 'призначення %d' % n, 'direction': 'OUTBOUND' if out else 'INBOUND', 'accountId': ACCT['accountId'],
         'senderIBAN': IBAN if out else OTHER, 'correspondentIBAN': OTHER if out else IBAN, 'senderName': 'Відправник', 'correspondentName': 'Одержувач',
         'senderTaxId': '3122334455', 'correspondentTaxId': '3098712345', 'senderBankMfo': '322001', 'correspondentBankMfo': '300001'}
    d.update(kw)
    return d


def reading(docs, acct_status=200, search_status=200, auth_status=200, search_body=None, scenario='pumb_a1_searcher_nopaging', auth_body=None, **kw):
    body = search_body or {'fromDate': DAY0, 'toDate': DAY1, 'documentAccounts': [str(ACCT['accountId'])]}
    auth = R.make_exchange(1, 'pumb_auth', {'method': 'POST', 'host': 'auth.fuib.com', 'path': '/auth/realms/VegaNet/protocol/openid-connect/token',
                                            'query': '', 'bodyOmitted': 'автентифікація'}, _resp(auth_body or {'token_type': 'Bearer'}, auth_status))
    acc = R.make_exchange(2, 'pumb_account', {'method': 'GET', 'host': 'service.fuib.com', 'port': 4103, 'path': '/war_veganet_api/account', 'query': ''},
                          _resp([ACCT], acct_status))
    srch = R.make_exchange(3, scenario, _post('/document/searcher', body), _resp(docs, search_status))
    ex = [auth, acc, srch]
    rec = R.Recording(R.make_manifest('pumb', 'run1', ex), ex)
    p = Params(account=IBAN, period_start=C.pumb_date(body['fromDate']), period_end=C.pumb_date(body['toDate']), reading_moment=C.DEFAULT_READING_MOMENT, **kw)
    return rec, p


def summary(e):
    return [(o['ПорядковыйНомер'], o['Сумма'], o['Направление'], o['НомерДокумента'], o['КонтрагентНомерСчета']) for o in e.ops], \
           sorted((d['Уровень'], d['ПорядковыйНомер'], d['Суть']) for d in e.diags)


MIXED = [doc(1), doc(2, out=False, amount='200.00', when='01.11.2026 11:00:00'), doc(3, state='ACCEPTED', when='01.11.2026 12:00:00'),
         doc(4, state='REJECTED', when='01.11.2026 13:00:00'), doc(5, amount='0.00'), doc(6, ccy='USD')]


class PumbExpected(unittest.TestCase):
    def test_by_hand_states_amounts_currency_and_trust(self):
        # відступи 3 (стани), 5 (сума), 1 (валюта), 6 (id), 7 (дата): ручне очікуване
        rec, p = reading(MIXED)
        e = E.run(rec, p)
        ops, diags = summary(e)
        self.assertEqual(ops, [(1, '100.50', 'Списано', '8001', OTHER), (2, '200.00', 'Поступило', '8002', OTHER)])
        self.assertEqual(diags, [('Ошибка', 5, 'bad-amount'), ('Предупреждение', 3, 'nonfinal'), ('Предупреждение', 4, 'cancelled'),
                                 ('Предупреждение', 6, 'foreign-currency')])
        self.assertEqual([(o['ИдентификаторОперации'], o['Валюта'], o['ДатаОперации'], o['ДатаДокумента']) for o in e.ops],
                         [('8001', '980', '2026-11-01T10:00:00', '2026-11-01'), ('8002', '980', '2026-11-01T11:00:00', '2026-11-01')])
        self.assertEqual((e.complete, e.failure_class), (True, ''))
        self.assertEqual(e.trust, datetime(2026, 11, 1, 12, 0, 0))              # не пізніша за першу неостаточну (D36 п. 10); скасована межу не тримає
        self.assertEqual([(r['Метод'], r['Хост'], r.get('Порт'), r['Путь']) for r in e.requests],
                         [('POST', 'auth.fuib.com', None, '/auth/realms/VegaNet/protocol/openid-connect/token'),
                          ('GET', 'service.fuib.com', 4103, '/war_veganet_api/account'),
                          ('POST', 'service.fuib.com', 4103, '/war_veganet_api/document/searcher')])
        self.assertEqual(e.requests[2]['Тело']['documentAccounts'], [str(ACCT['accountId'])])
        self.assertTrue(e.requests[0]['ТелоОпущено'])
        # відступи -- іменовані функції: вимкнений = попередник (стани зникають без сліду, id порожній), підміна ловиться
        e3 = E.run(rec, p, {'pumb3'})
        self.assertEqual([d['ПорядковыйНомер'] for d in e3.diags if d['Суть'] in ('nonfinal', 'cancelled')], [])
        self.assertEqual(e3.trust, p.period_end)
        self.assertEqual({o['ИдентификаторОперации'] for o in E.run(rec, p, {'pumb6'}).ops}, {''})
        self.assertEqual(sorted(e.applied), ['pumb1', 'pumb3', 'pumb5', 'pumb6'])

    def test_by_hand_a4_no_iban_error_error_description_cut_and_empty_id(self):
        # Р-д: документ без IBAN обох сторін -- Ошибка no-iban (рахунок з accountId запиту НЕ виводиться), не операція; сусідні документи -- як було
        rec, p = reading([doc(1), doc(2, senderIBAN=None, correspondentIBAN=''), doc(3, out=False, amount='7.00')])
        e = E.run(rec, p)
        self.assertEqual(([o['ПорядковыйНомер'] for o in e.ops], [(d['Уровень'], d['ПорядковыйНомер'], d['Суть']) for d in e.diags]),
                         ([1, 3], [('Ошибка', 2, 'no-iban')]))
        self.assertEqual(e.foreign, {})
        self.assertNotIn(str(ACCT['accountId']), json.dumps([e.ops, e.diags], ensure_ascii=False))
        self.assertEqual(set(e.diags[0]['Факты']), {'Ид'})                                      # лише ідентифікатор документа
        # Р-е: error_description (OAuth2) читається для діагностики, значення облікових даних вирізаються (без регістру). Контроль, що вміє впасти: БЕЗ вирізання логін у тексті є
        login = 'fiktivnyi_login_77'
        body = {'error': 'invalid_grant', 'error_description': 'Invalid user %s or password' % login.upper()}
        rec, p = reading([doc(1)], auth_status=400, auth_body=body)
        leaky = E.run(rec, p).diags[0]['Факты']['ОписаниеБанка']
        self.assertIn(login, leaky.lower())                                                     # без облікових даних у Params вирізати нічого: фікстура справді «витікала б»
        rec, p = reading([doc(1)], auth_status=400, auth_body=body, credentials=(login,))
        e = E.run(rec, p)
        self.assertEqual(e.diags[0]['Факты']['ОписаниеБанка'], 'Invalid user %s or password' % E.PUMB_CUT_MARK)
        self.assertNotIn(login, json.dumps(e.diags, ensure_ascii=False).lower())
        self.assertEqual(e.failure_class, 'ДействиеЧеловека')
        # error_description старший за message; інакше message; облікові дані не потрапляють в etalon-параметри
        self.assertEqual(E.pumb_error_description(rec.exchanges[0]), 'Invalid user %s or password' % login.upper())
        self.assertNotIn('credentials', json.dumps(p.to_json()).lower())
        # pumb6 (виміряно run1b): ідентифікатор -- docId; id (майже завжди null, у 2 входженнях непорожній і != docId) основним НЕ є; порожній docId -- Ошибка bad-identifier
        rec, p = reading([doc(1, id=''), doc(2, id=None), doc(3), doc(4, docId=None, id=7777), doc(5, docId='')])
        e = E.run(rec, p)
        self.assertEqual([o['ИдентификаторОперации'] for o in e.ops], ['8001', '8002', '8003'])
        self.assertEqual([(d['Уровень'], d['ПорядковыйНомер'], d['Суть'], d['Факты']) for d in e.diags], [('Ошибка', 4, 'bad-identifier', {'Количество': 0}), ('Ошибка', 5, 'bad-identifier', {'Количество': 0})])

    def test_by_hand_d36_failures_period_format_and_pagination(self):
        # п. 8: автентифікація / 4xx -- дія людини; 5xx -- повторити; п. 10: відмова -- межа = НачалоПериода, читання неповне
        for kw, cls in (({'auth_status': 401}, 'ДействиеЧеловека'), ({'acct_status': 403}, 'ДействиеЧеловека'),
                        ({'search_status': 500}, 'Повторить'), ({'search_status': 429}, 'Повторить')):
            rec, p = reading([doc(1)], **kw)
            e = E.run(rec, p)
            self.assertEqual((e.failure_class, e.complete, e.trust, e.ops), (cls, False, p.period_start, []), kw)
        rec, p = reading([doc(1)], acct_status=403)
        self.assertEqual(len(E.run(rec, p).requests), 2)                       # після відмови списку рахунків searcher не йде
        # п. 11: період навпаки -- дія людини без запитів; період цілком після моменту читання -- порожнє ПОВНЕ читання, межа = початок
        rec, p = reading([doc(1)])
        e = E.run(rec, Params(account=IBAN, period_start=p.period_end, period_end=p.period_start, reading_moment=p.reading_moment))
        self.assertEqual((e.failure_class, e.requests), ('ДействиеЧеловека', []))
        e = E.run(rec, Params(account=IBAN, period_start=datetime(2026, 12, 1), period_end=datetime(2026, 12, 2), reading_moment=p.reading_moment))
        self.assertEqual((e.complete, e.trust, e.ops, e.requests), (True, datetime(2026, 12, 1), [], []))
        # п. 11: аномалія меж -- операція поза межами ЗАПИТУ (fromDate/toDate з тіла searcher): повторити, читання неповне, межа = початок, сторінку не беремо, без значень у діагностиці;
        # рівність межі аномалією не є (включність не виміряна)
        for when in ('02.11.2026 00:00:00', '31.10.2026 23:59:59'):
            rec, p = reading([doc(1), doc(2, when=when)])
            e = E.run(rec, p)
            self.assertEqual((e.failure_class, e.complete, e.trust, e.ops), ('Повторить', False, p.period_start, []), when)
            self.assertEqual([(d['Уровень'], d['Суть'], d['Факты']) for d in e.diags],
                             [('Предупреждение', 'out-of-bounds', {'Банк': 'ПУМБ', 'Вид': 'out-of-bounds', 'Статус': 200, 'ОписаниеБанка': ''})])
        rec, p = reading([doc(1, when=DAY0), doc(2, when=DAY1)])
        self.assertEqual([o['ПорядковыйНомер'] for o in E.run(rec, p).ops], [1, 2])
        # формат operationDate -- гіпотеза: інший формат -- явна відмова, не здогад
        rec, p = reading([doc(1, when='2026-11-01T10:00:00')])
        with self.assertRaises(C.PumbDateFormat):
            E.run(rec, p)
        # Р4: конектор пагінації не використовує -- запит з pagingRequest оракул відхиляє явно (перелік «не змодельовано» названий)
        rec, p = reading([doc(1)], search_body={'fromDate': DAY0, 'toDate': DAY1, 'documentAccounts': ['5500123456'], 'pagingRequest': {'pageSize': 1}})
        with self.assertRaises(E.PaginationUnmeasured):
            E.run(rec, p)
        readings, skipped = RD.pumb_split(rec)
        self.assertEqual((readings, [s[0] for s in skipped]), ([], ['pumb_a1_searcher_nopaging']))

    def test_check_c_on_anonymized_pumb_reading_incl_request_bodies(self):
        rec, p = reading(MIXED[:4])
        with tempfile.TemporaryDirectory() as d:
            raw, anon, mp = (os.path.join(d, n) for n in ('raw', 'anon', 'map.json'))
            rec.to_dir(raw)
            A.anonymize_bank('pumb', raw, anon, mp)
            res = step2.check_c('pumb', raw, anon, mp)
        self.assertEqual((res['problems'], res['readings'], res['compared_ok']), ([], 1, 1))
        self.assertEqual(res['requests_compared'], 3)


if __name__ == '__main__':
    unittest.main()
