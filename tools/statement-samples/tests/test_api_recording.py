# -*- coding: utf-8 -*-
"""Формат запису відповідей API (`apilib/recording.py`, `tools/api-recorder/FORMAT.md`): валідація, тека, пакет,
кодування тіла. Дані синтетичні."""
import base64
import copy
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import recording as R, synth


def tiny(body=b'[]', headers=(('content-type', 'application/json;charset=utf-8'),)):
    ex = [R.make_exchange(1, 's', {'host': 'api.monobank.ua', 'path': '/personal/client-info', 'query': ''},
                          {'status': 200, 'headers': list(headers), 'body': body})]
    return R.Recording(R.make_manifest('mono-fop', 'x', ex), ex)


class Format(unittest.TestCase):
    def test_valid_tiny(self):
        tiny()

    def test_body_bytes_and_length(self):
        rec = tiny('[{"а":1}]'.encode('utf-8'))
        self.assertEqual(R.body_bytes(rec.exchanges[0]), '[{"а":1}]'.encode('utf-8'))
        self.assertEqual(rec.exchanges[0]['response']['bodyLength'], len('[{"а":1}]'.encode('utf-8')))

    def test_cp1251_body_decodes_by_charset(self):
        body = '{"x":"Київ"}'.encode('cp1251')
        rec = tiny(body, (('content-type', 'application/json;charset=cp1251'),))
        self.assertEqual(R.body_json(rec.exchanges[0]), {'x': 'Київ'})
        self.assertRaises(UnicodeDecodeError, body.decode, 'utf-8')       # байти не UTF-8: без charset було б сміття

    def test_html_is_not_json(self):
        rec = tiny(b'<html>proxy</html>')
        self.assertRaises(R.NotJson, R.body_json, rec.exchanges[0])

    def test_violations_are_rejected(self):
        rec = tiny()
        cases = []
        e = copy.deepcopy(rec.exchanges)
        e[0]['request']['headers'] = [['token', 'x']]
        cases.append(e)                                                  # заголовки запиту
        e = copy.deepcopy(rec.exchanges)
        e[0]['response']['headers'].append(['set-cookie', 'a=b'])
        cases.append(e)                                                  # заголовок поза білим списком
        e = copy.deepcopy(rec.exchanges)
        e[0]['response']['bodyLength'] += 1
        cases.append(e)                                                  # довжина тіла
        e = copy.deepcopy(rec.exchanges)
        e[0]['request']['method'] = 'POST'
        cases.append(e)                                                  # метод
        e = copy.deepcopy(rec.exchanges)
        e[0]['failure'] = {'kind': 'timeout', 'text': 't'}
        cases.append(e)                                                  # і response, і failure
        for ex in cases:
            with self.assertRaises(R.FormatError):
                R.Recording(rec.manifest, ex)

    def test_failure_exchange(self):
        ex = [R.make_exchange(1, 's', {'host': 'h', 'path': '/p'}, failure={'kind': 'timeout', 'text': 'timed out'})]
        rec = R.Recording(R.make_manifest('privat', 'x', ex), ex)
        self.assertEqual(rec.manifest['exchanges'][0]['failure'], 'timeout')
        self.assertIsNone(rec.manifest['exchanges'][0]['status'])


AUTH = {'method': 'POST', 'host': 'service.example.test', 'port': 4103, 'path': '/api/search', 'query': ''}


def v2(**extra):
    """Запис із одного обміну формату v2: запит `AUTH` плюс форма тіла/порт із `extra` (ключі make_exchange)."""
    req = dict(AUTH, **extra)
    ex = [R.make_exchange(1, 's', req, {'status': 200, 'headers': [], 'body': b'[]'})]
    return R.Recording(R.make_manifest('privat', 'x', ex), ex)


class FormatV2(unittest.TestCase):
    """Формат v2 (задача 1a плану 05б-2): метод не лише GET, `request.port`, тіло запиту однією з трьох форм."""

    def test_post_with_port_and_body_bytes(self):
        body = '{"id":"СМП_ТЕСТ_1","limit":10}'.encode('utf-8')
        rec = v2(body=body)
        ex = rec.exchanges[0]
        self.assertEqual((ex['formatVersion'], rec.manifest['formatVersion']), (2, 2))
        self.assertEqual(ex['request']['port'], 4103)
        self.assertEqual(base64.b64decode(ex['request']['bodyBase64']), body)
        self.assertEqual(ex['request']['bodyLength'], len(body))
        with tempfile.TemporaryDirectory() as d:
            rec.to_dir(d)
            again = R.Recording.from_dir(d)
        self.assertEqual((again.manifest, again.exchanges), (rec.manifest, rec.exchanges))
        via_pack = R.Recording.unpack(rec.pack())
        self.assertEqual((via_pack.manifest, via_pack.exchanges), (rec.manifest, rec.exchanges))

    def test_masked_and_omitted_forms(self):
        masked = v2(bodyMasked={'text': '{"login":"<masked>","limit":10}', 'fields': ['login']}).exchanges[0]['request']
        self.assertEqual(masked['bodyMasked']['fields'], ['login'])
        omitted = v2(bodyOmitted='пароль-грант').exchanges[0]['request']
        self.assertTrue(omitted['bodyOmitted'])
        self.assertEqual(omitted['bodyOmittedReason'], 'пароль-грант')

    def test_5a_exchange_stays_v1(self):
        ex = tiny().exchanges[0]
        self.assertEqual((ex['formatVersion'], tiny().manifest['formatVersion']), (1, 1))
        self.assertNotIn('port', ex['request'])

    def test_v2_violations_are_rejected(self):
        masked = {'text': '{"login":"<masked>"}', 'fields': ['login']}
        v2(bodyMasked=masked)                               # контроль: правильні форми проходять, інакше відмови нічого не доводять
        v2(body=b'{}')
        cases = {
            'два види тіла': dict(body=b'{}', bodyOmitted='x'),
            'bodyOmitted без причини': dict(bodyOmitted=''),
            'bodyMasked без переліку полів': dict(bodyMasked={'text': '{"login":"<masked>"}', 'fields': []}),
            'у переліку поле без маркера': dict(bodyMasked={'text': '{"login":"abc"}', 'fields': ['login']}),
            'маркер поза переліком': dict(bodyMasked={'text': '{"login":"<masked>","p":"<masked>"}', 'fields': ['login']}),
            'метод поза GET/POST': dict(method='DELETE', bodyOmitted='x'),
            'порт рядком': dict(port='4103', bodyMasked=masked),
            'порт нуль': dict(port=0, bodyMasked=masked),
        }
        for name, extra in cases.items():
            with self.subTest(name):
                with self.assertRaises(R.FormatError):
                    v2(**extra)
        rec = v2(bodyOmitted='x')
        e = copy.deepcopy(rec.exchanges)
        e[0]['request']['headers'] = [['token', 'x']]
        with self.assertRaises(R.FormatError):              # заголовків запиту немає й у v2
            R.Recording(rec.manifest, e)


class Persistence(unittest.TestCase):
    def test_dir_and_pack_roundtrip_for_every_synthetic(self):
        for s in synth.all_scenarios():
            rec = s.recording()
            with tempfile.TemporaryDirectory() as d:
                rec.to_dir(d)
                again = R.Recording.from_dir(d)
            self.assertEqual(again.manifest, rec.manifest, s.name)
            self.assertEqual(again.exchanges, rec.exchanges, s.name)
            via_pack = R.Recording.unpack(rec.pack())
            self.assertEqual((via_pack.manifest, via_pack.exchanges), (rec.manifest, rec.exchanges), s.name)

    def test_pack_is_ascii_json_with_base64(self):
        rec = synth.all_scenarios()[0].recording()
        pk = json.loads(rec.pack())
        self.assertEqual(pk['format'], R.PACK_FORMAT)
        any_ex = next(iter(pk['exchanges'].values()))
        base64.b64decode(any_ex['response']['bodyBase64'], validate=True)


if __name__ == '__main__':
    unittest.main()
