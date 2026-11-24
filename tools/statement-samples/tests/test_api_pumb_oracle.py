# -*- coding: utf-8 -*-
"""Сторожові перевірки оракула ПУМБ (задача 2a, Step 2): регістронезалежне вирізання облікових даних із тексту відмови автентифікації
і перевірка C знеособленого запису ПУМБ разом із тілами запитів. Усі значення ВИГАДАНІ."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import anonymize as A, common as C, expected as E, kyiv, recording as R, step2
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
    start, end = C.pumb_date(DAY0), C.pumb_date(DAY1)
    if search_body is not None:                              # свій запит тесту: період із його тіла, як було
        start, end = C.pumb_date(search_body['fromDate']), C.pumb_date(search_body['toDate'])
    else:                                  # перший запит -- форма конектора: цілі доби (доба початку 00:00:00, доба Мин(кінець, момент читання) 23:59:59) і три поля (оракул звіряє й перший запит)
        lo, hi = C.pumb_request_bounds(start, min(end, kyiv.to_local(C.DEFAULT_READING_MOMENT)))
        search_body = {'fromDate': lo.strftime('%d.%m.%Y %H:%M:%S'), 'toDate': hi.strftime('%d.%m.%Y %H:%M:%S'), 'documentAccounts': [str(ACCT['accountId'])]}
    body = search_body
    auth = R.make_exchange(1, 'pumb_auth', {'method': 'POST', 'host': 'auth.fuib.com', 'path': '/auth/realms/VegaNet/protocol/openid-connect/token',
                                            'query': '', 'bodyOmitted': 'автентифікація'}, _resp(auth_body or {'token_type': 'Bearer'}, auth_status))
    acc = R.make_exchange(2, 'pumb_account', {'method': 'GET', 'host': 'service.fuib.com', 'port': 4103, 'path': '/war_veganet_api/account', 'query': ''},
                          _resp([ACCT], acct_status))
    srch = R.make_exchange(3, scenario, _post('/document/searcher', body), _resp(docs, search_status))
    ex = [auth, acc, srch]
    rec = R.Recording(R.make_manifest('pumb', 'run1', ex), ex)
    p = Params(account=IBAN, period_start=start, period_end=end, reading_moment=C.DEFAULT_READING_MOMENT, **kw)
    return rec, p


MIXED = [doc(1), doc(2, out=False, amount='200.00', when='01.11.2026 11:00:00'), doc(3, state='ACCEPTED', when='01.11.2026 12:00:00'),
         doc(4, state='REJECTED', when='01.11.2026 13:00:00'), doc(5, amount='0.00'), doc(6, ccy='USD')]


class PumbExpected(unittest.TestCase):
    def test_error_description_cuts_login_case_insensitively(self):
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
