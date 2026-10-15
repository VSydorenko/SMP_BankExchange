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
