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
REST = '84213.55'                                        # залишок рахунку, що збігається з amount документа (A6)
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


def fake_recording(searcher_body=None, raw_text=None, child=None, errors=None, doc2_number='4816', ptx_amount='1500.00', ptx_docnum='4815', query='', extra_body=None, doc_id=8800123456, doc_number='4815', alt=ALT, paging=None):
    account = {'id': 7000123456, 'accountId': ACC_ID, 'mfo': '322001', 'currency': 'UAH', 'number': '26001234567890',
               'name': 'Поточний Зіркова', 'state': 1, 'hostId': 3, 'branchId': 'XYZ', 'clientId': 'CL778899', 'clientName': PERSON,
               'clientOkpo': '3098712345', 'isDefault': True, 'iban': IBAN, 'balance': REST, 'rest': REST,
               'altNumber': alt, 'accountTypeName': TYPE_NAME, 'restWithHolds': 84213.55, 'createdOn': '01.01.2020 10:00:00', 'openDate': None,
               'accountCardType': None, 'isDeleted': None, 'clientaccounttotype': 'CURRENT'}
    doc = {'id': LAST_ID + 1, 'hostId': 3, 'docId': doc_id, 'date': '01.11.2026 10:15:00', 'state': 'PROCESSED', 'type': 'UAH',
           'firstSignature': PERSON, 'secondSignature': PERSON_INI, 'number': doc_number, 'accountId': ACC_ID, 'amount': '1500.00',
           'currencyCode': 'UAH', 'description': 'Оплата за послуги Зіркова Л.О.', 'operationDate': '01.11.2026 10:15:00',
           'userIdentity': PERSON_INI, 'direction': 'INBOUND', 'senderName': 'Вигадана компанія', 'correspondentName': PERSON,
           'senderTaxId': '3122334455', 'senderAccountNumber': '26009876543210', 'responsible': PERSON_INI, 'senderIBAN': IBAN,
           'pagingRowInfo': {'rowNumber': 1, 'rowIdentity': LAST_ID + 1, 'sortedValue': SORTED},
           'documentTreatyId': None, 'importId': None, 'linkedDocumentId': None, 'childDocuments': child, 'purposeType': 'PAYMENT', 'isPackage': False,
           'operationDateWithMillis': '01.11.2026 10:15:00.123', 'veganetdocumentdtotype': 'VeganetPaymentDto'}
    doc2 = dict(doc, id=LAST_ID + 2, docId=8800123457, number=doc2_number, amount=REST, operationDate=SORTED_DATE,    # amount документа = залишку рахунку (пара-виняток A6)
                pagingRowInfo={'rowNumber': 2, 'rowIdentity': LAST_ID + 2, 'sortedValue': SORTED_DATE})
    ptx = {'header': {'dateFrom': '01.11.2026 00:00:00', 'dateTo': '01.11.2026 23:59:59', 'currency': 'UAH', 'accountName': 'Поточний Зіркова',
                      'inSaldo': '1000.10', 'outSaldo': '2500.10', 'debitTurn': '0.00', 'creditTurn': '1500.00', 'iban': IBAN},
           'transactions': [{'dcFlag': 1, 'accountName': 'Поточний Зіркова', 'currency': 'UAH', 'amount': ptx_amount, 'transactionId': 6600123456,
                             'documentDate': '01.11.2026', 'documentNumber': ptx_docnum, 'corrName': PERSON, 'corrIban': IBAN,
                             'narrative': 'Оплата за послуги', 'iban': IBAN}]}
    auth = {'access_token': 'aaaaaaaaaa.aaaaaaaaaa.aaaaaaaaaa', 'expires_in': 300, 'token_type': 'Bearer', 'scope': 'profile'}
    sb = searcher_body or {'fromDate': '01.11.2026 00:00:00', 'toDate': '01.11.2026 23:59:59', 'documentState': ['PROCESSED'],
                           'documentType': ['UAH'], 'documentAccounts': [str(ACC_ID)], 'pagingRequest': {'pageSize': paging or 1, 'orderedLastId': LAST_ID,
                                                           'orderedLastValue': SORTED}}
    sb = dict(sb, **(extra_body or {}))
    searcher = _post('/document/searcher', sb)
    if raw_text is not None:
        searcher['body'] = raw_text
    ex = [
        R.make_exchange(1, 'pumb_auth', {'method': 'POST', 'host': 'auth.fuib.com', 'path': '/auth/realms/VegaNet/protocol/openid-connect/token', 'query': '',
                                          'bodyOmitted': 'автентифікація'}, _resp(auth)),
        R.make_exchange(2, 'pumb_account', {'method': 'GET', 'host': 'service.fuib.com', 'port': 4103, 'path': '/war_veganet_api/account', 'query': query},
                        _resp([account])),
        R.make_exchange(3, 'pumb_searcher', searcher, _resp([doc, doc2])),
        R.make_exchange(4, 'pumb_ptx', _post('/document/period-transactions', {'accountId': ACC_ID, 'dateFrom': '01.11.2026 00:00:00',
                                                                                'dateTo': '01.11.2026 23:59:59'}), _resp(ptx)),
        R.make_exchange(6, 'pumb_error', _post('/document/searcher', {'fromDate': '01.11.2026 00:00:00'}),
                        _resp({'title': 'Bad Request', 'detail': DETAIL, 'instance': 'urn:err:4417', 'errors': errors}, 400)),
        R.make_exchange(7, 'pumb_error_ascii', _post('/document/period-transactions', {'accountId': ACC_ID}),
                        _resp({'title': 'Bad Request', 'detail': 'Account not found for this client', 'instance': 'urn:err:4418', 'errors': None}, 500)),
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

    def test_v_short_numeric_id_is_searched_as_a_whole_value_only_and_controls_fail(self):
        # короткий цифровий ID (роль ID, лише цифри, <= 5): (а) шукає ЦІЛЕ значення поля в будь-якому полі (включно з KEEP), у шляху й тілі запиту; підрядком -- ні.
        # Три контролі, що вміють впасти, і зелений парний прогін; ACC із коротким значенням лишається під пошуком підрядком.
        short = '4739'
        with tempfile.TemporaryDirectory() as d:                                     # зелений: docId = 4739 замінено, 4739 більше ніде немає; підрядок (у даті, сумі) не збіг
            env = Env(d, doc_id=int(short), extra_body={'documentAccounts': [str(ACC_ID)]})
            env.anonymize()
            res = env.check()
            self.assertEqual((res['hits'], res['hits_short_ids'], res['unchanged_short_id']), (0, 0, 0), res)
            self.assertGreaterEqual(res['short_id_tokens'], 1)
        with tempfile.TemporaryDirectory() as d:                                     # підрядок НЕ шукається: сире 4739 всередині довшого рядка KEEP -- не збіг
            env = Env(d, doc_id=int(short), doc_number='N4739K', ptx_docnum='4739' + '5')
            env.anonymize()
            res = env.check()
            self.assertEqual((res['hits_short_ids'], res['hits']), (0, 0), res)
        with tempfile.TemporaryDirectory() as d:                                     # контроль 1: сирий короткий docId як ціле значення в ІНШОМУ полі (number, KEEP)
            env = Env(d, doc_id=int(short), doc_number=short)
            env.anonymize()
            self.assertGreater(env.check()['hits_short_ids'], 0)
        orig = A.Bank.ident
        with tempfile.TemporaryDirectory() as d:                                     # контроль 2: сирий короткий docId на своєму місці (заміну вимкнено)
            env = Env(d, doc_id=int(short))
            with mock.patch.object(A.Bank, 'ident', lambda self, s: s if s == short else orig(self, s)):
                env.anonymize()
            res = env.check()
            self.assertGreater(res['unchanged_short_id'], 0, res)
            self.assertGreater(res['hits'], 0, res)
        with tempfile.TemporaryDirectory() as d:                                     # контроль 3: сирий короткий docId як ціле значення в тілі ЗАПИТУ (pageSize, KEEP)
            env = Env(d, doc_id=int(short), paging=int(short))
            env.anonymize()
            res = env.check()
            self.assertGreater(res['hits_short_ids'], 0, res)
        with tempfile.TemporaryDirectory() as d:                                     # ACC без змін: коротке значення шукається підрядком (4-значне altNumber усередині number)
            env = Env(d, alt='5521', doc_number='N5521K')
            env.anonymize()
            self.assertGreater(env.check()['hits_short'], 0)

    def test_vi_generator_never_issues_a_replacement_equal_to_a_raw_short_id(self):
        fk = gen.Fakes()
        fk.forbidden_ids = {str(i) for i in range(1, 9)}
        self.assertEqual(fk.ident('7'), '9')

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

    def test_v_a6_ascii_purpose_keeps_byte_class_and_balance_pair_is_allowed_only_in_amount_fields(self):
        # (б) строга: ASCII-оригінал PURPOSE -> ASCII-заміна (клас байтів зберігається), помилок (б) немає
        with tempfile.TemporaryDirectory() as d:
            env = Env(d)
            env.anonymize()
            self.assertEqual(step2.check_b('pumb', env.raw, env.anon, env.map)['problems'], [])
            body = base64.b64decode(anon_exchange(env, 7)['response']['bodyBase64'])
            self.assertTrue(body.isascii())
            self.assertNotIn(b'Account not found', body)                                       # значення справді замінено
            # (а): залишок = amount документа -> пара-виняток (рахується), витоків немає
            res = env.check()
            self.assertEqual((res['hits'], res['pair_leaks']), (0, 0), res)
            self.assertGreaterEqual(res['pair_counts'].get(step2.PUMB_PAIR_NAME, 0), 1, res)
            amounts = [x['amount'] for x in json.loads(base64.b64decode(anon_exchange(env, 3)['response']['bodyBase64']))]
            self.assertIn(REST, amounts)                                                        # amount (KEEP) лишився як є
            acc = json.loads(base64.b64decode(anon_exchange(env, 2)['response']['bodyBase64']))[0]
            self.assertNotEqual(acc['rest'], REST)                                              # а сам залишок замінено
        # КОНТРОЛЬ (б): ASCII-оригінал із не-ASCII заміною -> (б) знаходить «кодування тіла»
        with tempfile.TemporaryDirectory() as d:
            env = Env(d)
            with mock.patch.object(A.Bank, 'ascii_purpose', lambda self, s: 'Український текст'):
                env.anonymize()
            self.assertTrue(any('кодування тіла' in p for p in step2.check_b('pumb', env.raw, env.anon, env.map)['problems']))
        # A7: `amount` ТРАНЗАКЦІЇ period-transactions теж дозволено (та сама операція в обох основах)
        with tempfile.TemporaryDirectory() as d:
            env = Env(d, ptx_amount=REST)
            env.anonymize()
            res = env.check()
            self.assertEqual((res['hits'], res['pair_leaks']), (0, 0), res)
        # КОНТРОЛЬ (а): те саме значення залишку в БУДЬ-ЯКОМУ іншому місці -- червоне: `number` документа, `documentNumber` транзакції, тіло запиту (запит з невідомим параметром знеособлювач відхиляє ще до перевірки)
        for kw in ({'doc2_number': REST}, {'ptx_docnum': REST}, {'extra_body': {'documentAmount': REST}}):
            with tempfile.TemporaryDirectory() as d:
                env = Env(d, **kw)
                env.anonymize()
                res = env.check()
                self.assertGreater(res['pair_leaks'], 0, (kw, res))
                self.assertGreater(res['hits'], 0, (kw, res))


if __name__ == '__main__':
    unittest.main()
