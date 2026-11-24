# -*- coding: utf-8 -*-
"""Step 2 задачі 2: знеособлення записів відповідей API і перевірки D22 а / б / в. Усі записи тут -- ВИГАДАНІ (синтетика
`synth.py`, що грає роль «сирого» запису); справжніх записів у тестах немає. Кожна перевірка має тест, що вона вміє
падати: на пошкодженому знеособленому записі код виходу ненульовий, а на сирому запис (контроль) дає збіги."""
import base64
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import anonymize as A, recording as R, step2, synth
import sslib.gen as sgen


class Env:
    """Вигаданий «прогін»: для кожного банку один запис (сценарії синтетики злиті в один маніфест не можна -- кожен сценарій
    окремий запис, тож зберігаємо їх як окремі «мітки»)."""

    def __init__(self, bank, sid, root):
        self.bank, self.sid = bank, sid
        s = [x for x in synth.all_scenarios() if x.bank == bank and x.sid == sid][0]
        self.scn = s
        self.raw_root, self.anon_root, self.map_dir = (os.path.join(root, n) for n in ('raw', 'anon', 'map'))
        self.raw = os.path.join(self.raw_root, bank, 'run1')
        s.recording().to_dir(self.raw)
        self.anon = os.path.join(self.anon_root, bank)
        self.map = os.path.join(self.map_dir, bank + '.json')

    def anonymize(self):
        return A.anonymize_bank(self.bank, self.raw, self.anon, self.map)

    def args(self, cmd):
        return [cmd, '--raw-root', self.raw_root, '--label', 'run1', '--anon-root', self.anon_root, '--map-dir', self.map_dir,
                '--bank', self.bank]


def mutate_body(anon_dir, seq, fn, fix_length=True):
    """Змінює текст тіла обміну `seq` у знеособленому записі функцією `fn(текст)->текст` (кодування зберігається)."""
    path = os.path.join(anon_dir, '%04d.json' % seq)
    with open(path, encoding='utf-8') as f:
        ex = json.load(f)
    cs = 'cp1251' if 'cp1251' in json.dumps(ex['response']['headers']) else 'utf-8'
    text = base64.b64decode(ex['response']['bodyBase64']).decode(cs)
    body = fn(text).encode(cs)
    ex['response']['bodyBase64'] = base64.b64encode(body).decode('ascii')
    if fix_length:
        ex['response']['bodyLength'] = len(body)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(ex, f, ensure_ascii=False, indent=1)


def mutate_exchange(anon_dir, seq, fn):
    path = os.path.join(anon_dir, '%04d.json' % seq)
    with open(path, encoding='utf-8') as f:
        ex = json.load(f)
    fn(ex)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(ex, f, ensure_ascii=False, indent=1)


class CheckA(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = Env('privat', 'СинтСтатусы', self.tmp)
        self.env.anonymize()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def hits(self):
        return step2.check_a(self.env.bank, self.env.raw, self.env.anon)['hits']

    def test_clean_is_zero_and_control_on_raw_has_hits(self):
        self.assertEqual(self.hits(), 0)
        self.assertGreater(step2.check_a(self.env.bank, self.env.raw, self.env.anon, control=True)['hits'], 0)

    def first_sensitive(self):
        raw = R.Recording.from_dir(self.env.raw)
        t = R.body_json(raw.exchanges[1])['transactions'][0]
        return t

    def test_raw_name_leaked_into_a_free_text_field(self):
        t = self.first_sensitive()
        err = [e for e in R.Recording.from_dir(self.env.anon).exchanges if e['request']['path'] == '/api/statements/balance'][0]
        mutate_body(self.env.anon, err['seq'], lambda s: s.replace('"type":"balances"', '"type":"%s"' % t['AUT_CNTR_NAM'].replace('"', ''), 1))
        self.assertGreater(self.hits(), 0)

    def test_raw_iban_in_the_path_of_a_request(self):
        t = self.first_sensitive()
        mutate_exchange(self.env.anon, 3, lambda ex: ex['request'].update(query=ex['request']['query'] + '&x=' + t['AUT_CNTR_ACC']))
        self.assertGreater(self.hits(), 0)

    def test_raw_id_unchanged_in_place(self):
        raw = R.Recording.from_dir(self.env.raw)
        rid = R.body_json(raw.exchanges[1])['transactions'][0]['ID']
        anon_first = R.Recording.from_dir(self.env.anon).exchanges[1]
        old = R.body_json(anon_first)['transactions'][0]['ID']
        mutate_body(self.env.anon, 2, lambda s: s.replace(old, rid))
        self.assertGreater(self.hits(), 0)

    def test_leak_hidden_behind_json_unicode_escapes(self):
        """Назва (кирилиця) і IBAN, екрановані як \\uXXXX у вільному полі `type`: байтовий пошук не бачить, розкодований JSON -- бачить."""
        t = self.first_sensitive()
        for value in (t['AUT_CNTR_NAM'].replace('"', ''), t['AUT_CNTR_ACC']):
            shutil.rmtree(self.env.anon)
            self.env.anonymize()
            self.assertEqual(self.hits(), 0)
            esc = ''.join('\\u%04x' % ord(c) for c in value)
            mutate_body(self.env.anon, 2, lambda s: s.replace('"type":"transactions"', '"type":"%s"' % esc, 1))
            self.assertGreater(self.hits(), 0)

    def test_every_encoding_is_searched(self):
        token = 'Вигадана Назва Підприємства'
        token = 'Вигадана Назва Приватна'                 # кодується в усіх п'яти кодуваннях (без «і»/«ї» для cp866)
        for enc in ('utf-8', 'utf-16le', 'utf-16be', 'cp1251', 'cp866'):
            blob = b'xx{"k":"' + token.encode(enc) + b'"}yy'
            self.assertEqual(step2.scan_whole(blob, {token}), {token}, enc)
        token = 'Вигадана Назва Підприємства'
        esc = json.dumps(token, ensure_ascii=True)[1:-1].encode()
        self.assertEqual(step2.scan_whole(b'..' + esc + b'..', {token}), {token})
        self.assertEqual(step2.scan_whole(b'..' + esc.upper().replace(b'\\U', b'\\u') + b'..', {token}), {token})
        import urllib.parse
        self.assertEqual(step2.scan_whole(b'?q=' + urllib.parse.quote(token).encode(), {token}), {token})
        for shift in (0, 1, 2):
            b64 = base64.b64encode(b'\x00' * shift + token.encode('utf-8'))
            self.assertEqual(step2.scan_whole(b'{"bodyBase64": "' + b64 + b'"}', {token}), {token}, shift)
        self.assertEqual(step2.scan_whole('нічого спільного'.encode('utf-8'), {token}), set())          # контроль: не знаходить зайвого

    def test_check_cannot_pass_on_an_untouched_copy(self):
        shutil.rmtree(self.env.anon)
        shutil.copytree(self.env.raw, self.env.anon)
        self.assertGreater(self.hits(), 0)


class CheckB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = Env('mono-corp', 'СинтСтатусы', self.tmp)
        self.env.anonymize()
        self.stmt = [e['seq'] for e in R.Recording.from_dir(self.env.anon).exchanges if R.statement_window(e)][0]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def problems(self):
        return step2.check_b(self.env.bank, self.env.raw, self.env.anon, self.env.map)['problems']

    def test_green(self):
        self.assertEqual(self.problems(), [])

    def red(self, fn, what):
        mutate_body(self.env.anon, self.stmt, fn)
        self.assertTrue(self.problems(), what)

    def test_dropped_array_item(self):
        def fn(t):
            arr = json.loads(t)
            return json.dumps(arr[:-1], ensure_ascii=False, separators=(',', ':'))
        self.red(fn, 'довжина масиву')

    def test_renamed_key(self):
        self.red(lambda t: t.replace('"status"', '"state"', 1), 'ключ')

    def test_number_became_string(self):
        self.red(lambda t: t.replace('"amount":-', '"amount":"-', 1).replace('"currencyCode"', '"currencyCode"', 1)
                 if '"amount":-' in t else t.replace('"amount":', '"amount":"', 1), 'тип')

    def test_changed_keep_value(self):
        self.red(lambda t: t.replace('"status":"DONE"', '"status":"HOLD"', 1), 'KEEP')

    def test_changed_layout(self):
        self.red(lambda t: t.replace('},{', '}, {', 1), 'пробіли')

    def test_replaced_value_with_other_form(self):
        raw = R.body_json(R.Recording.from_dir(self.env.raw).exchanges[self.stmt - 1])
        anon = R.body_json(R.Recording.from_dir(self.env.anon).exchanges[self.stmt - 1])
        iban = anon[0]['counterIban']
        self.red(lambda t: t.replace(iban, iban[:-1], 1), 'форма IBAN')

    def test_body_encoding_changed(self):
        # сирий -- UTF-8, а знеособлений став cp1251: кодування тіла частина даних
        mutate_exchange(self.env.anon, self.stmt, lambda ex: None)
        path = os.path.join(self.env.anon, '%04d.json' % self.stmt)
        with open(path, encoding='utf-8') as f:
            ex = json.load(f)
        text = base64.b64decode(ex['response']['bodyBase64']).decode('utf-8')
        if text.isascii():
            text = text.replace('"description":"', '"description":"Ж', 1)
        body = text.encode('cp1251')
        ex['response']['bodyBase64'] = base64.b64encode(body).decode('ascii')
        ex['response']['bodyLength'] = len(body)
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(ex, f, ensure_ascii=False, indent=1)
        self.assertTrue(self.problems())

    def test_wrong_body_length(self):
        mutate_body(self.env.anon, self.stmt, lambda t: t, fix_length=False)
        mutate_exchange(self.env.anon, self.stmt, lambda ex: ex['response'].update(bodyLength=ex['response']['bodyLength'] + 1))
        self.assertTrue(self.problems())

    def test_status_and_order_of_exchanges(self):
        mutate_exchange(self.env.anon, self.stmt, lambda ex: ex['response'].update(status=500))
        self.assertTrue(self.problems())

    def test_changed_path_segment_and_query_key(self):
        mutate_exchange(self.env.anon, self.stmt, lambda ex: ex['request'].update(query='lim=30'))
        self.assertTrue(self.problems())

    def test_manifest_changed(self):
        path = os.path.join(self.env.anon, 'recording.json')
        with open(path, encoding='utf-8') as f:
            m = json.load(f)
        m['exchanges'][0]['status'] = 201
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(m, f, ensure_ascii=False, indent=1)
        self.assertTrue(self.problems())


class CheckC(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = Env('mono-corp', 'СинтСтатусы', self.tmp)
        self.env.anonymize()
        self.stmt = [e['seq'] for e in R.Recording.from_dir(self.env.anon).exchanges if R.statement_window(e)][0]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def problems(self):
        return step2.check_c(self.env.bank, self.env.raw, self.env.anon, self.env.map)['problems']

    def test_green_and_it_compares_something(self):
        res = step2.check_c(self.env.bank, self.env.raw, self.env.anon, self.env.map)
        self.assertEqual(res['problems'], [])
        self.assertGreater(res['fields_compared'], 50)
        self.assertGreater(res['fields_replaced'], 10)

    def test_replacement_that_is_not_the_mapped_one_is_red_while_b_is_green(self):
        anon = R.body_json(R.Recording.from_dir(self.env.anon).exchanges[self.stmt - 1])
        iban = anon[0]['counterIban']
        other = 'UA' + sgen.iban_check_digits('UA', '3052990000000000000000001') + '3052990000000000000000001'
        mutate_body(self.env.anon, self.stmt, lambda t: t.replace(iban, other))
        self.assertEqual(step2.check_b(self.env.bank, self.env.raw, self.env.anon, self.env.map)['problems'], [])
        probs = self.problems()
        self.assertTrue(probs)
        self.assertTrue(any('мапи' in p for p in probs))

    def test_changed_operation_amount_is_red(self):
        mutate_body(self.env.anon, self.stmt, lambda t: t.replace('"amount":', '"amount":1', 1))
        self.assertTrue(self.problems())

    def test_oracle_on_raw_and_anon_differ_in_direction(self):
        # знак суми -- напрям операції: змінений знак дає іншу операцію в оракулі
        def fn(t):
            return t.replace('"amount":-', '"amount":', 1) if '"amount":-' in t else t.replace('"amount":', '"amount":-', 1)
        mutate_body(self.env.anon, self.stmt, fn)
        self.assertTrue(self.problems())


if __name__ == '__main__':
    unittest.main()
