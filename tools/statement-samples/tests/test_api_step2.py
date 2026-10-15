# -*- coding: utf-8 -*-
"""Місце Step 2 в архітектурі: заглушки не мають виглядати зеленими, таблиця ролей повна для всього, що генерує
інструмент, CLI працює. Знеособлення справжніх записів і перевірки а/б/в на них — Step 2 (записів ще немає)."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import cli, recording as R, schema, step2, synth


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli.main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class Stubs(unittest.TestCase):
    def test_stage2_commands_never_return_zero(self):
        for cmd in ('anonymize', 'check-a', 'check-b', 'check-c', 'verify'):
            rc, _, err = run_cli(cmd, '--raw', 'x')
            self.assertEqual(rc, cli.STEP2_RC, cmd)
            self.assertIn('Step 2', err)

    def test_stage2_functions_raise(self):
        for fn, args in ((step2.anonymize_recording, (1, 2, 3)), (step2.check_a, (1, 2, 3)), (step2.check_b, (1, 2)),
                         (step2.check_c, (1, 2, 3, 4))):
            with self.assertRaises(NotImplementedError):
                fn(*args)


class Roles(unittest.TestCase):
    """Кожне поле, яке генерує інструмент (а отже, і дзеркальне поле справжнього запису), має роль: невідоме поле
    Step 2 не збереже мовчки. Контроль: вигадане поле — невідоме."""

    def test_synthetic_fields_have_roles(self):
        for s in synth.all_scenarios():
            for ex in s.recording().exchanges:
                if not ex['response']:
                    continue
                try:
                    js = R.body_json(ex)
                except R.NotJson:
                    continue
                if s.bank == 'privat' and isinstance(js, dict):
                    self.assertEqual(schema.unknown_fields('privat', 'page', js) , [], s.name)
                    for t in js.get('transactions', []):
                        self.assertEqual(schema.unknown_fields('privat', 'tx', t), [], s.name)
                    if 'settings' in js:
                        self.assertEqual(schema.unknown_fields('privat', 'settings', js['settings']), [], s.name)
                elif isinstance(js, list):
                    for t in js:
                        section = 'balance' if 'isFinal' in t else 'tx'
                        self.assertEqual(schema.unknown_fields(s.bank, section, t), [], s.name)
                elif s.bank == 'mono-fop' and 'accounts' in js:
                    self.assertEqual(schema.unknown_fields('mono-fop', 'client', js), [], s.name)
                    for a in js['accounts']:
                        self.assertEqual(schema.unknown_fields('mono-fop', 'account', a), [], s.name)

    def test_unknown_field_is_found(self):
        self.assertEqual(schema.unknown_fields('privat', 'tx', {'AUT_MY_ACC': '1', 'NEW_FIELD': 'x'}), ['NEW_FIELD'])


class Cli(unittest.TestCase):
    def test_synth_selfcheck_oracle_and_pack(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, _ = run_cli('synth', '--out', d, '--packs', '--only', 'СинтСтатусы')
            self.assertEqual(rc, 0)
            names = sorted(os.listdir(os.path.join(d, 'etalons')))
            self.assertEqual(len(names), 3)
            with open(os.path.join(d, 'etalons', names[0]), encoding='utf-8') as f:
                et = json.load(f)
            self.assertEqual(et['format'], 'smp-api-etalon')
            rec_dir = os.path.join(d, 'recordings', et['bank'], et['id'])
            rc, out, _ = run_cli('oracle', '--recording', rec_dir, '--mode', 'expected', '--account', et['parameters']['НомерСчета'],
                                 '--start', et['parameters']['НачалоПериода'], '--end', et['parameters']['КонецПериода'])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(out)['Операции'], et['expected']['Операции'])         # CLI дає той самий результат, що еталон
            pack = os.path.join(d, 'x.json')
            self.assertEqual(run_cli('pack', '--recording', rec_dir, '--out', pack)[0], 0)
            back = os.path.join(d, 'back')
            self.assertEqual(run_cli('unpack', '--pack', pack, '--out', back)[0], 0)
            self.assertEqual(R.Recording.from_dir(back).exchanges, R.Recording.from_dir(rec_dir).exchanges)
        rc, out, _ = run_cli('selfcheck')
        self.assertEqual(rc, 0)
        self.assertIn('провалено: 0', out)


if __name__ == '__main__':
    unittest.main()
