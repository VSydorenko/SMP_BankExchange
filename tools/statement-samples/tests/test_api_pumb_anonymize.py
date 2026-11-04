# -*- coding: utf-8 -*-
"""Знеособлення ПУМБ (задача 2a, частина 1): тіло запиту v2 і поля-особи. Усі значення тут ВИГАДАНІ (справжніх записів немає).
Лише контролі, що вміють впасти: (і) вимкнена заміна в тілі запиту -> (а) знаходить збіг; (іі) вимкнена заміна NAME для
userIdentity / responsible / підписів -> (а) знаходить збіг (підрядком, зокрема ініціали); (ііі) нерозбірне тіло запиту -> відмова
без фрагмента вхідного тексту. Кожен контроль має «зелений» парний прогін, щоб червоний не був випадковим."""
import base64
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import anonymize as A, recording as R, schema, step2
from sslib import gen

ACC_ID = 5500123456                  # accountId у відповіді /account і в тілах запитів (вигаданий)
LAST_ID = 9100123456
SORTED_DATE = '01.11.2026 10:15:00'     # курсор-дата: форма «дата» -> KEEP, лишається як є й дорівнює даті операції
SORTED = 'SV-4821907'               # sortedValue відповіді = orderedLastValue наступного запиту (роль ID: та сама заміна)
PERSON = 'Зіркова Лілія Орестівна'
PERSON_INI = 'Зіркова Л.О.'
ALT = '26005551234567'                                   # account.altNumber (роль ACC, A5)
TYPE_NAME = 'Рахунок Місячний Вітрило'                   # account.accountTypeName (роль NAME, A5)
DETAIL = 'Відмовлено клієнту Островський Вітрило'        # error.detail (роль PURPOSE, A5)
JSON_HDR = [('content-type', 'application/json;charset=utf-8')]
IBAN = 'UA' + gen.iban_check_digits('UA', '3220010000026001234567890') + '3220010000026001234567890'


def _post(path, body=None, masked=None):
    rq = {'method': 'POST', 'host': 'service.fuib.com', 'port': 4103, 'path': '/war_veganet_api' + path, 'query': ''}
    if body is not None:
        rq['body'] = json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if masked is not None:
        rq['bodyMasked'] = masked
    return rq


def _resp(obj, status=200, hdr=JSON_HDR):
    return {'status': status, 'headers': hdr, 'body': json.dumps(obj, ensure_ascii=False).encode('utf-8')}


def fake_recording(searcher_body=None, raw_text=None, child=None, errors=None):
    account = {'id': 7000123456, 'accountId': ACC_ID, 'mfo': '322001', 'currency': 'UAH', 'number': '26001234567890',
               'name': 'Поточний Зіркова', 'state': 1, 'hostId': 3, 'branchId': 'XYZ', 'clientId': 'CL778899', 'clientName': PERSON,
               'clientOkpo': '3098712345', 'isDefault': True, 'iban': IBAN, 'balance': '84213.55', 'rest': '84213.55',
               'altNumber': ALT, 'accountTypeName': TYPE_NAME, 'restWithHolds': 84213.55, 'createdOn': '01.01.2020 10:00:00', 'openDate': None,
               'accountCardType': None, 'isDeleted': None, 'clientaccounttotype': 'CURRENT'}
    doc = {'id': LAST_ID + 1, 'hostId': 3, 'docId': 8800123456, 'date': '01.11.2026 10:15:00', 'state': 'PROCESSED', 'type': 'UAH',
           'firstSignature': PERSON, 'secondSignature': PERSON_INI, 'number': '4815', 'accountId': ACC_ID, 'amount': '1500.00',
           'currencyCode': 'UAH', 'description': 'Оплата за послуги Зіркова Л.О.', 'operationDate': '01.11.2026 10:15:00',
           'userIdentity': PERSON_INI, 'direction': 'INBOUND', 'senderName': 'Вигадана компанія', 'correspondentName': PERSON,
           'senderTaxId': '3122334455', 'senderAccountNumber': '26009876543210', 'responsible': PERSON_INI, 'senderIBAN': IBAN,
           'pagingRowInfo': {'rowNumber': 1, 'rowIdentity': LAST_ID + 1, 'sortedValue': SORTED},
           'documentTreatyId': None, 'importId': None, 'linkedDocumentId': None, 'childDocuments': child, 'purposeType': 'PAYMENT', 'isPackage': False,
           'operationDateWithMillis': '01.11.2026 10:15:00.123', 'veganetdocumentdtotype': 'VeganetPaymentDto'}
    doc2 = dict(doc, id=LAST_ID + 2, docId=8800123457, number='4816', operationDate=SORTED_DATE,
                pagingRowInfo={'rowNumber': 2, 'rowIdentity': LAST_ID + 2, 'sortedValue': SORTED_DATE})
    ptx = {'header': {'dateFrom': '01.11.2026 00:00:00', 'dateTo': '01.11.2026 23:59:59', 'currency': 'UAH', 'accountName': 'Поточний Зіркова',
                      'inSaldo': '1000.10', 'outSaldo': '2500.10', 'debitTurn': '0.00', 'creditTurn': '1500.00', 'iban': IBAN},
           'transactions': [{'dcFlag': 1, 'accountName': 'Поточний Зіркова', 'currency': 'UAH', 'amount': '1500.00', 'transactionId': 6600123456,
                             'documentDate': '01.11.2026', 'documentNumber': '4815', 'corrName': PERSON, 'corrIban': IBAN,
                             'narrative': 'Оплата за послуги', 'iban': IBAN}]}
    auth = {'access_token': 'aaaaaaaaaa.aaaaaaaaaa.aaaaaaaaaa', 'expires_in': 300, 'token_type': 'Bearer', 'scope': 'profile'}
    sb = searcher_body or {'fromDate': '01.11.2026 00:00:00', 'toDate': '01.11.2026 23:59:59', 'documentState': ['PROCESSED'],
                           'documentType': ['UAH'], 'documentAccounts': [str(ACC_ID)], 'pagingRequest': {'pageSize': 1, 'orderedLastId': LAST_ID,
                                                           'orderedLastValue': SORTED}}
    searcher = _post('/document/searcher', sb)
    if raw_text is not None:
        searcher['body'] = raw_text
    ex = [
        R.make_exchange(1, 'pumb_auth', {'method': 'POST', 'host': 'auth.fuib.com', 'path': '/auth/realms/VegaNet/protocol/openid-connect/token', 'query': '',
                                          'bodyOmitted': 'автентифікація'}, _resp(auth)),
        R.make_exchange(2, 'pumb_account', {'method': 'GET', 'host': 'service.fuib.com', 'port': 4103, 'path': '/war_veganet_api/account', 'query': ''},
                        _resp([account])),
        R.make_exchange(3, 'pumb_searcher', searcher, _resp([doc, doc2])),
        R.make_exchange(4, 'pumb_ptx', _post('/document/period-transactions', {'accountId': ACC_ID, 'dateFrom': '01.11.2026 00:00:00',
                                                                                'dateTo': '01.11.2026 23:59:59'}), _resp(ptx)),
        R.make_exchange(6, 'pumb_error', _post('/document/searcher', {'fromDate': '01.11.2026 00:00:00'}),
                        _resp({'title': 'Bad Request', 'detail': DETAIL, 'instance': 'urn:err:4417', 'errors': errors}, 400)),
        R.make_exchange(5, 'pumb_ptx_masked', _post('/document/period-transactions', masked={
            'text': '{"accountId":"<masked>","dateFrom":"01.11.2026 00:00:00","dateTo":"01.11.2026 23:59:59"}', 'fields': ['accountId']}), _resp(ptx)),
    ]
    return R.Recording(R.make_manifest('pumb', 'run1', ex), ex)


class Env:
    def __init__(self, root, **kw):
        self.raw, self.anon, self.map = (os.path.join(root, n) for n in ('raw', 'anon', 'map.json'))
        fake_recording(**kw).to_dir(self.raw)

    def anonymize(self):
        return A.anonymize_bank('pumb', self.raw, self.anon, self.map)

    def check(self):
        return step2.check_a('pumb', self.raw, self.anon)


def anon_exchange(env, seq):
    with open(os.path.join(env.anon, '%04d.json' % seq), encoding='utf-8') as f:
        return json.load(f)


def anon_text(env):
    """Усі файли знеособленого запису й розкодовані тіла відповідей -- один рядок (вигадані дані)."""
    out = []
    for n in sorted(os.listdir(env.anon)):
        if n.endswith('.json') and n != 'recording.json':
            with open(os.path.join(env.anon, n), encoding='utf-8') as f:
                raw = f.read()
            out.append(raw)
            b = (json.loads(raw).get('response') or {}).get('bodyBase64')
            if b:
                out.append(base64.b64decode(b).decode('utf-8'))
    return ''.join(out)


class PumbRequestBodyAndPersons(unittest.TestCase):
    def test_i_request_body_replaced_with_same_map_and_control_fails_when_disabled(self):
        with tempfile.TemporaryDirectory() as d:
            env = Env(d)
            env.anonymize()
            res = env.check()
            self.assertEqual(res['hits'], 0, res)                                      # зелений парний прогін
            self.assertGreater(res['exchanges'], 0)
            # та сама мапа: accountId запиту = accountId відповіді (`/account`); port, довжина, bodyMasked, bodyOmitted
            acc = json.loads(base64.b64decode(anon_exchange(env, 2)['response']['bodyBase64']))[0]['accountId']
            self.assertNotEqual(acc, ACC_ID)
            e3, e4, e5, e1 = (anon_exchange(env, n)['request'] for n in (3, 4, 5, 1))
            b3 = base64.b64decode(e3['bodyBase64'])
            self.assertEqual(json.loads(b3)['documentAccounts'], [str(acc)])
            self.assertEqual(e3['bodyLength'], len(b3))
            self.assertEqual(json.loads(base64.b64decode(e4['bodyBase64']))['accountId'], acc)
            self.assertEqual(e3['port'], 4103)
            sv = json.loads(base64.b64decode(anon_exchange(env, 3)['response']['bodyBase64']))[0]['pagingRowInfo']['sortedValue']
            self.assertEqual(sv, json.loads(b3)['pagingRequest']['orderedLastValue'])      # узгоджена заміна відповідь <-> запит
            self.assertNotEqual(sv, SORTED)
            d2 = json.loads(base64.b64decode(anon_exchange(env, 3)['response']['bodyBase64']))[1]
            self.assertEqual(d2['pagingRowInfo']['sortedValue'], SORTED_DATE, 'курсор-дата')       # KEEP: не замінено
            self.assertEqual(d2['operationDate'], SORTED_DATE, 'курсор-дата: операція')
            self.assertIn('"accountId":"<masked>"', e5['bodyMasked']['text'])
            self.assertEqual(e5['bodyMasked']['fields'], ['accountId'])
            self.assertTrue(e1['bodyOmitted'])
            # КОНТРОЛЬ: вимкнена заміна тіла запиту -> (а) знаходить сирі значення в тілі запиту
        with tempfile.TemporaryDirectory() as d:
            env = Env(d)
            with mock.patch.object(A.Bank, '_request_body', lambda self, req, out: None):
                env.anonymize()
            res = env.check()
            self.assertGreater(res['hits'], 0, res)

    def test_ii_person_fields_are_name_and_control_fails_when_replacement_disabled(self):
        self.assertTrue(all(schema.ROLES['pumb']['doc'][f] == 'NAME' for f in ('userIdentity', 'responsible', 'firstSignature', 'secondSignature')))
        self.assertIn('зіркова л.о.', step2.person_tokens(PERSON_INI))
        self.assertIn('л.о.', step2.person_tokens(PERSON))                           # ініціали виведено з повного ПІБ
        with tempfile.TemporaryDirectory() as d:
            env = Env(d)
            env.anonymize()
            res = env.check()
            self.assertEqual((res['hits'], res['hits_person']), (0, 0), res)
            self.assertGreater(res['person_tokens'], 0)
        orig = A.Bank.replace_node

        def skip_persons(self, role, nd, key, escaped):
            return None if key in step2.PERSON_FIELDS['pumb'] else orig(self, role, nd, key, escaped)
        with tempfile.TemporaryDirectory() as d:
            env = Env(d)
            with mock.patch.object(A.Bank, 'replace_node', skip_persons):
                env.anonymize()
            res = env.check()
            self.assertGreater(res['hits_person'], 0, res)

    def test_iii_unparseable_request_body_is_refused_without_a_fragment(self):
        for raw in (b'{"accountId": 5500123456, "zzFRAGMENT', b'\xff\xfe{"a":1}'):
            with tempfile.TemporaryDirectory() as d:
                env = Env(d, raw_text=raw)
                with self.assertRaises(schema.UnknownField) as cm:
                    env.anonymize()
                msg = str(cm.exception)
                self.assertIn('тіло запиту', msg)
                self.assertNotIn('zzFRAGMENT', msg)
                self.assertNotIn('5500123456', msg)
                self.assertFalse(os.path.exists(env.anon))                              # нічого не записано

    def test_iv_a5_new_fields_replaced_null_only_fields_stop_and_control_fails_when_roles_are_keep(self):
        # поля, яких немає в swagger (run1b): значення ACC/NAME/PURPOSE у них не лишаються; «лише null» -- ненульове зупиняє (без значення в тексті)
        with tempfile.TemporaryDirectory() as d:
            env = Env(d)
            env.anonymize()
            res = env.check()
            self.assertEqual(res['hits'], 0, res)
            text = anon_text(env)
            for raw in (ALT, 'Місячний', 'Островський'):
                self.assertNotIn(raw, text, raw)
            # дата-поля й дискримінатори -- KEEP: лишаються
            self.assertIn('01.11.2026 10:15:00.123', text)
            self.assertIn('VeganetPaymentDto', text)
        for kw in ({'child': 'X-SECRET-77'}, {'errors': [{'k': 'X-SECRET-77'}]}, {'child': []}):
            with tempfile.TemporaryDirectory() as d:
                env = Env(d, **kw)
                with self.assertRaises(schema.UnknownField) as cm:
                    env.anonymize()
                self.assertIn('лише null', str(cm.exception))
                self.assertNotIn('SECRET', str(cm.exception))
                self.assertFalse(os.path.exists(env.anon))
        # КОНТРОЛЬ: якщо ролі нових полів -- KEEP, значення лишаються сирими й (а) їх знаходить
        with tempfile.TemporaryDirectory() as d:
            env = Env(d)
            with mock.patch.dict(schema.PUMB_ACCOUNT, {'altNumber': 'KEEP', 'accountTypeName': 'KEEP'}), mock.patch.dict(schema.PUMB_ERROR, {'detail': 'KEEP'}):
                env.anonymize()
            res = env.check()
            self.assertGreater(res['hits'], 0, res)


if __name__ == '__main__':
    unittest.main()
