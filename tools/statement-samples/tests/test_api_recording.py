# -*- coding: utf-8 -*-
"""Формат запису відповідей API (`apilib/recording.py`, `tools/api-recorder/FORMAT.md`): валідація, тека, пакет,
кодування тіла. Дані синтетичні."""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import recording as R


def tiny(body=b'[]', headers=(('content-type', 'application/json;charset=utf-8'),)):
    ex = [R.make_exchange(1, 's', {'host': 'api.monobank.ua', 'path': '/personal/client-info', 'query': ''},
                          {'status': 200, 'headers': list(headers), 'body': body})]
    return R.Recording(R.make_manifest('mono-fop', 'x', ex), ex)


class Format(unittest.TestCase):
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


AUTH = {'method': 'POST', 'host': 'service.example.test', 'port': 4103, 'path': '/api/search', 'query': ''}


def v2(**extra):
    """Запис із одного обміну формату v2: запит `AUTH` плюс форма тіла/порт із `extra` (ключі make_exchange)."""
    req = dict(AUTH, **extra)
    ex = [R.make_exchange(1, 's', req, {'status': 200, 'headers': [], 'body': b'[]'})]
    return R.Recording(R.make_manifest('privat', 'x', ex), ex)


class FormatV2(unittest.TestCase):
    """Формат v2 (задача 1a плану 05б-2): метод не лише GET, `request.port`, тіло запиту однією з трьох форм."""

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


if __name__ == '__main__':
    unittest.main()
