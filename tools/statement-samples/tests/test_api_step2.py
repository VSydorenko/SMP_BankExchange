# -*- coding: utf-8 -*-
"""Step 2 задачі 2: знеособлення записів відповідей API і перевірки D22 а / б / в. Усі записи тут -- ВИГАДАНІ (синтетика
`synth.py`, що грає роль «сирого» запису); справжніх записів у тестах немає. Кожна перевірка має тест, що вона вміє
падати: на пошкодженому знеособленому записі код виходу ненульовий, а на сирому запис (контроль) дає збіги."""
import base64
import contextlib
import copy
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import anonymize as A, cli, jsonspan, readings as RD, recording as R, schema, step2, synth
import sslib.gen as sgen

try:
    from stdnum import iban as sn_iban
    from stdnum.ua import edrpou as sn_edrpou, rntrc as sn_rntrc
except ImportError:                      # pragma: no cover
    sn_iban = None

PICK = {'privat': ('СинтСтраницыСлед', 'СинтПоля', 'СинтСтатусы', 'СинтТокен401', 'СинтГраницаДыра'),
        'mono-corp': ('СинтСтатусы', 'СинтТокен400', 'СинтГраницаДыра', 'СинтКратнаяСтраница'),
        'mono-fop': ('СинтСтатусы', 'СинтТокен403', 'СинтСтраницы')}


def run_cli(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = cli.main(list(argv))
    return rc, out.getvalue()


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


class JsonSpan(unittest.TestCase):
    def test_spans_cover_exactly_the_tokens_and_untouched_text_is_identical(self):
        text = '{ "a" : [1, 2.50, "x\\"y", true, null],\n "b": {"c": "Ж"} }'
        root = jsonspan.parse(text)
        self.assertEqual(jsonspan.replace_spans(text, []), text)
        toks = []

        def walk(n):
            if n.kind in ('obj',):
                for _, v in n.items:
                    walk(v)
            elif n.kind == 'arr':
                for v in n.items:
                    walk(v)
            else:
                toks.append(text[n.start:n.end])
        walk(root)
        self.assertEqual(toks, ['1', '2.50', '"x\\"y"', 'true', 'null', '"Ж"'])
        edited = jsonspan.replace_spans(text, [(root.items[0][1].items[1].start, root.items[0][1].items[1].end, '9.99')])
        self.assertEqual(edited, text.replace('2.50', '9.99'))

    def test_skeleton_ignores_values_but_not_types_or_layout(self):
        a, b = '{"x": 1, "y": "s"}', '{"x": 22, "y": "tt"}'
        sk = lambda t: jsonspan.skeleton(t, jsonspan.parse(t))
        self.assertEqual(sk(a), sk(b))
        self.assertNotEqual(sk(a), sk('{"x": 1.5, "y": "s"}'))        # int -> float
        self.assertNotEqual(sk(a), sk('{"x": "1", "y": "s"}'))        # число -> рядок
        self.assertNotEqual(sk(a), sk('{"x":1,"y":"s"}'))             # інші пробіли
        self.assertNotEqual(sk(a), sk('{"y": "s", "x": 1}'))          # інший порядок ключів

    def test_invalid_json_is_an_error_without_content(self):
        with self.assertRaises(jsonspan.JsonSpanError) as cm:
            jsonspan.parse('{"secret": }')
        self.assertNotIn('secret', str(cm.exception))


class FakesExtensions(unittest.TestCase):
    def setUp(self):
        import random
        self.fk = sgen.Fakes(rng=random.Random(5))

    def test_ident_keeps_form_and_length_and_is_stable_and_injective(self):
        raw = ['DNABC123XYZ456', '12345678', 'ab12cd34-ef56-4a78-b9c0-d1e2f3a4b5c6', 'ZuHWzqkKGV1=', 'ABCD-EF12-3456-7890',
               '557091731_online', 'Aa9Bb_-c.d@7']
        out = [self.fk.ident(x) for x in raw]
        for r, o in zip(raw, out):
            self.assertEqual(len(r), len(o))
            self.assertEqual(step2.shape(r), step2.shape(o))
            self.assertNotEqual(r, o)
            self.assertEqual(self.fk.ident(r), o)                                   # одна заміна на прогін
        self.assertEqual(len(set(out)), len(out))
        self.assertRegex(out[2], r'^[0-9a-f-]+$')                                   # hex лишається hex (UUID)
        self.assertRegex(out[3], r'=$')

    def test_ident_prefix_relation_survives(self):
        ref = 'DNREF12345ABCD'
        full = ref + '0123456789012345'
        f_full = self.fk.ident(full, refs=[ref])
        f_ref = self.fk.ident(ref, refs=[ref])
        self.assertTrue(f_full.startswith(f_ref))
        self.assertEqual(len(f_full), 30)

    def test_ident_survives_map_reload(self):
        a = self.fk.ident('XYZ12345')
        fk2 = sgen.Fakes()
        fk2.load(json.loads(json.dumps(self.fk.dump())))
        self.assertEqual(fk2.ident('XYZ12345'), a)
        b = fk2.ident('QQQ98765')
        self.assertNotEqual(b, a)

    def test_number_keeps_shape(self):
        for tok in ('12345', '-7', '1000050.25', '0.5', '10050000', '3.1'):
            n = self.fk.number(tok)
            self.assertEqual(step2.shape(tok), step2.shape(n))
            self.assertEqual(self.fk.number(tok), n)
            json.loads(n)
        self.assertNotEqual(self.fk.number('1000050.25'), '1000050.25')


class Roles(unittest.TestCase):
    """Кожне поле, яке генерує інструмент (а отже, і дзеркальне поле справжнього запису), має роль: невідоме поле
    Step 2 не збереже мовчки. Контроль: вигадане поле -- невідоме."""

    def test_every_synthetic_body_is_walked_by_the_schema(self):
        n = 0
        for s in synth.all_scenarios():
            for ex in s.recording().exchanges:
                if not ex['response']:
                    continue
                try:
                    root = jsonspan.parse(R.body_text(ex))
                except jsonspan.JsonSpanError:
                    continue                                      # HTML проксі
                schema.leaves(s.bank, ex['request']['path'], ex['response']['status'], root)
                n += 1
        self.assertGreater(n, 100)

    def test_unknown_field_is_a_stop_without_the_value(self):
        root = jsonspan.parse('{"status":"SUCCESS","exist_next_page":false,"transactions":[{"AUT_MY_ACC":"UA1","NEW_FIELD":"секретне"}]}')
        with self.assertRaises(schema.UnknownField) as cm:
            schema.leaves('privat', '/api/statements/transactions', 200, root)
        self.assertIn('NEW_FIELD', str(cm.exception))
        self.assertNotIn('секретне', str(cm.exception))

    def test_unknown_field_in_the_body_stops_anonymize(self):
        with tempfile.TemporaryDirectory() as d:
            env = Env('privat', 'СинтСтраницыСлед', d)
            mutate_body(env.raw, 2, lambda t: t.replace('"status":"SUCCESS"', '"status":"SUCCESS","BRAND_NEW":"x"', 1))
            with self.assertRaises(schema.UnknownField):
                env.anonymize()


class Anonymize(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.envs = {}
        for bank, sids in PICK.items():
            for sid in sids:
                sub = os.path.join(cls.tmp, bank + '-' + sid)
                env = Env(bank, sid, sub)
                env.anonymize()
                cls.envs[(bank, sid)] = env

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_all_three_checks_are_green_on_every_record(self):
        for key, env in self.envs.items():
            for cmd in ('check-a', 'check-b', 'check-c'):
                rc, out = run_cli(*env.args(cmd))
                self.assertEqual(rc, 0, (key, cmd, out))

    def test_files_have_the_same_names_and_format(self):
        for key, env in self.envs.items():
            self.assertEqual(sorted(os.listdir(env.raw)), sorted(os.listdir(env.anon)), key)
            R.Recording.from_dir(env.anon)                          # формат v1 перевіряє Recording.validate

    def test_untouched_text_is_byte_identical_outside_replaced_values(self):
        env = self.envs[('privat', 'СинтСтраницыСлед')]
        for x, y in zip(R.Recording.from_dir(env.raw).exchanges, R.Recording.from_dir(env.anon).exchanges):
            if not x['response']:
                continue
            tx, ty = R.body_text(x), R.body_text(y)
            self.assertEqual(jsonspan.skeleton(tx, jsonspan.parse(tx)), jsonspan.skeleton(ty, jsonspan.parse(ty)))

    def test_cp1251_body_stays_cp1251(self):
        env = self.envs[('privat', 'СинтПоля')]
        rx = R.Recording.from_dir(env.raw).exchanges[0]
        ry = R.Recording.from_dir(env.anon).exchanges[0]
        self.assertEqual(R.header(rx, 'content-type'), R.header(ry, 'content-type'))
        by = R.body_bytes(ry)
        with self.assertRaises(UnicodeDecodeError):
            by.decode('utf-8')                                      # як і сирий: невалідне UTF-8
        self.assertTrue(by.decode('cp1251'))

    def test_one_map_per_bank_same_value_same_replacement_across_pages_and_paths(self):
        env = self.envs[('privat', 'СинтСтраницыСлед')]
        a = R.Recording.from_dir(env.anon)
        raw = R.Recording.from_dir(env.raw)
        # next_page_id сторінки = ID її останньої операції, і followId наступного запиту -- та сама вигадана заміна
        p1 = R.body_json(a.exchanges[1])
        q2 = dict(R.query_pairs(a.exchanges[2]))
        self.assertEqual(q2['followId'], p1['next_page_id'])
        self.assertEqual(p1['next_page_id'], p1['transactions'][-1]['ID'])
        self.assertNotEqual(p1['next_page_id'], R.body_json(raw.exchanges[1])['next_page_id'])
        # acc запиту = хвіст власного IBAN у відповіді
        own = p1['transactions'][0]['AUT_MY_ACC']
        self.assertEqual(dict(R.query_pairs(a.exchanges[1]))['acc'], own[-14:])
        # ID = TECHNICAL_TRANSACTION_ID і починається з REF
        for t in p1['transactions']:
            self.assertEqual(t['ID'], t['TECHNICAL_TRANSACTION_ID'])
            self.assertTrue(t['ID'].startswith(t['REF']))

    def test_ids_ibans_and_codes_are_valid_and_of_the_same_form(self):
        if sn_iban is None:
            self.skipTest('python-stdnum недоступний')
        checked = 0
        for (bank, sid), env in self.envs.items():
            for ex in R.Recording.from_dir(env.anon).exchanges:
                texts = [ex['request']['path'], ex['request']['query']]
                if ex['response']:
                    try:
                        root = jsonspan.parse(R.body_text(ex))
                    except jsonspan.JsonSpanError:
                        continue
                    for role, nd, where in schema.leaves(bank, ex['request']['path'], ex['response']['status'], root):
                        if nd.kind == 'str' and role in ('ACC', 'CODE') and nd.value:
                            texts.append(nd.value)
                            if role == 'CODE':
                                ok = sn_edrpou.is_valid(nd.value) if len(nd.value) == 8 else sn_rntrc.is_valid(nd.value)
                                self.assertTrue(ok, (bank, sid))
                                checked += 1
                import re
                for t in texts:
                    for m in re.findall(r'UA\d{27}', t):
                        self.assertTrue(sn_iban.is_valid(m), (bank, sid))
                        checked += 1
        self.assertGreater(checked, 50)

    def test_map_is_reused_and_lives_outside_the_output(self):
        with tempfile.TemporaryDirectory() as d:
            env = Env('mono-corp', 'СинтСтатусы', d)
            env.anonymize()
            first = {n: open(os.path.join(env.anon, n), 'rb').read() for n in os.listdir(env.anon)}
            self.assertTrue(os.path.exists(env.map))
            self.assertFalse(env.map.startswith(env.anon_root))
            shutil.rmtree(env.anon)
            env.anonymize()
            second = {n: open(os.path.join(env.anon, n), 'rb').read() for n in os.listdir(env.anon)}
            self.assertEqual(first, second)                         # та сама мапа -- той самий результат
            self.assertNotIn('map.json', os.listdir(env.anon))

    def test_corp_text_plain_error_body_is_kept_as_is(self):
        env = self.envs[('mono-corp', 'СинтТокен400')]
        x = R.Recording.from_dir(env.raw).exchanges[0]
        y = R.Recording.from_dir(env.anon).exchanges[0]
        self.assertEqual(R.body_bytes(x), R.body_bytes(y))
        self.assertTrue(R.header(y, 'content-type').startswith('text/plain'))


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
        t = R.body_json(raw.exchanges[0])['transactions'][0]
        return t

    def test_raw_name_leaked_into_a_free_text_field(self):
        t = self.first_sensitive()
        err = [e for e in R.Recording.from_dir(self.env.anon).exchanges if e['request']['path'] == '/api/statements/balance'][0]
        mutate_body(self.env.anon, err['seq'], lambda s: s.replace('"type":"balances"', '"type":"%s"' % t['AUT_CNTR_NAM'].replace('"', ''), 1))
        self.assertGreater(self.hits(), 0)

    def test_raw_iban_in_the_path_of_a_request(self):
        t = self.first_sensitive()
        mutate_exchange(self.env.anon, 2, lambda ex: ex['request'].update(query=ex['request']['query'] + '&x=' + t['AUT_CNTR_ACC']))
        self.assertGreater(self.hits(), 0)

    def test_raw_id_unchanged_in_place(self):
        raw = R.Recording.from_dir(self.env.raw)
        rid = R.body_json(raw.exchanges[0])['transactions'][0]['ID']
        anon_first = R.Recording.from_dir(self.env.anon).exchanges[0]
        old = R.body_json(anon_first)['transactions'][0]['ID']
        mutate_body(self.env.anon, 1, lambda s: s.replace(old, rid))
        self.assertGreater(self.hits(), 0)

    def test_leak_hidden_behind_json_unicode_escapes(self):
        t = self.first_sensitive()
        esc = ''.join('\\u%04x' % ord(c) for c in t['AUT_CNTR_ACC'])        # ASCII-токен екранований
        word = [w for w in t['AUT_MY_NAM'].replace('"', ' ').split() if len(w) > 3 and w[0].isupper()]
        name = word[0] if word else 'Вигадана'
        esc_name = ''.join('\\u%04x' % ord(c) for c in t['AUT_CNTR_NAM'].replace('"', ''))
        mutate_body(self.env.anon, 1, lambda s: s.replace('"type":"transactions"', '"type":"%s"' % esc_name, 1))
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


class CliExitCodes(unittest.TestCase):
    def test_unknown_field_is_a_stop_with_code_4_and_no_value(self):
        with tempfile.TemporaryDirectory() as d:
            env = Env('mono-fop', 'СинтСтатусы', d)
            mutate_body(env.raw, 2, lambda t: t.replace('"hold"', '"holdX"', 1))
            rc, out = run_cli(*env.args('check-a'))
            self.assertEqual(rc, 4)
            self.assertIn('holdX', out)                         # ім'я поля -- так; значень немає
            self.assertIn('код виходу: 4', out)

    def test_violation_is_code_1_and_missing_control_is_code_2(self):
        with tempfile.TemporaryDirectory() as d:
            env = Env('mono-fop', 'СинтСтатусы', d)
            env.anonymize()
            shutil.rmtree(env.anon)
            shutil.copytree(env.raw, env.anon)
            self.assertEqual(run_cli(*env.args('check-a'))[0], 1)
            from unittest import mock
            with mock.patch.object(step2, 'scan_whole', lambda blob, tokens: set()), \
                    mock.patch.object(step2, 'scan_lexemes', lambda blob, nums, names: (set(), set())):
                self.assertEqual(run_cli(*env.args('check-a'))[0], 2)          # перевірка, що нічого не знаходить, -- не зелена

    def test_verify_writes_a_report_without_values(self):
        with tempfile.TemporaryDirectory() as d:
            env = Env('mono-corp', 'СинтСтатусы', d)
            env.anonymize()
            report = os.path.join(d, 'report.txt')
            rc, out = run_cli('verify', '--raw-root', env.raw_root, '--anon-root', env.anon_root, '--map-dir', env.map_dir,
                              '--bank', env.bank, '--report', report)
            self.assertEqual(rc, 0)
            text = open(report, encoding='utf-8').read()
            self.assertIn('verify: найгірший код виходу 0', text)
            raw = R.Recording.from_dir(env.raw)
            for ex in raw.exchanges:
                if ex['response'] and ex['response']['status'] == 200:
                    for item in R.body_json(ex):
                        if isinstance(item, dict) and item.get('counterName'):
                            self.assertNotIn(item['counterName'], text)

    def test_etalons_are_written_for_readings(self):
        with tempfile.TemporaryDirectory() as d:
            env = Env('mono-corp', 'СинтСтатусы', d)
            env.anonymize()
            rc, out = run_cli(*env.args('etalons'))
            self.assertEqual(rc, 0)
            names = os.listdir(os.path.join(env.anon_root, 'etalons'))
            self.assertEqual(len(names), 1)
            with open(os.path.join(env.anon_root, 'etalons', names[0]), encoding='utf-8') as f:
                et = json.load(f)
            self.assertEqual((et['format'], et['synthetic']), ('smp-api-etalon', False))
            self.assertGreater(len(et['expected']['Операции']), 0)
            self.assertTrue(os.path.isdir(os.path.join(env.anon_root, 'readings', 'mono-corp')))


if __name__ == '__main__':
    unittest.main()
