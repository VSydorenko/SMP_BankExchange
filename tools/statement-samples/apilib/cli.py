# -*- coding: utf-8 -*-
"""Команди інструменту записів відповідей API (`python -P tools/statement-samples/apisamples.py <команда>`).

| Команда | Що робить | Код виходу |
|---|---|---|
| `list` | перелік синтетичних записів: банк, макет, рядки Review Focus | 0 |
| `synth --out DIR [--only ІМ'Я] [--packs]` | пише `DIR/recordings/<банк>/<Ид>/…`, `DIR/etalons/<СМП_ТестЭталон…>.json` | 0 |
| `selfcheck` | самоперевірка оракула на прикладах з документації | 1, якщо хоч одна перевірка не пройшла |
| `oracle --recording DIR --mode old|expected --account IBAN --start ISO --end ISO` | оракул на записі, JSON у stdout | 0 |
| `pack --recording DIR --out FILE` / `unpack --pack FILE --out DIR` | запис <-> один JSON-файл | 0 |
| `guard-synth --raw R` | сторож (`sslib.guard`) на згенерованих записях, пакетах, еталонах | 1 — збіги, 2 — контроль не падає |
| `guard --raw R [--staged] [--files …]` | сторож для коду й документації режиму API (з `api_guard_allowed_words`) | те саме |
| `anonymize`, `check-a`, `check-b`, `check-c`, `verify` | Step 2 (знеособлення справжніх записів) | 3: ще не виконано |
"""
import argparse
import json
import os
import sys
from datetime import datetime

from . import common as C, etalon, expected, leakguard, oracle_old, recording as R, selfcheck, step2, synth

STEP2_RC = 3


def _write(path, text, binary=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)


def cmd_list(a):
    for s in synth.all_scenarios():
        print('%-10s %-36s фокус %-8s %s' % (s.bank, s.name, ','.join(map(str, s.focus)), s.title))
    return 0


def cmd_synth(a):
    n = 0
    for s in synth.all_scenarios():
        if a.only and a.only not in (s.sid, s.name):
            continue
        rec = s.recording()
        rec.to_dir(os.path.join(a.out, 'recordings', s.bank, s.sid))
        d, _, _ = etalon.build(s)
        _write(os.path.join(a.out, 'etalons', s.etalon_name + '.json'), etalon.dumps(d))
        if a.packs:
            _write(os.path.join(a.out, 'packs', s.name + '.json'), rec.pack())
        n += 1
    print('записів: %d -> %s' % (n, a.out))
    return 0


def cmd_selfcheck(a):
    bad = 0
    for name, ok, detail in selfcheck.run():
        print('%s  %s %s' % ('ok  ' if ok else 'FAIL', name, detail))
        bad += 0 if ok else 1
    print('перевірок: %d, провалено: %d' % (len(selfcheck.CHECKS), bad))
    return 1 if bad else 0


def cmd_oracle(a):
    rec = R.Recording.from_dir(a.recording)
    p = C.Params(account=a.account, period_start=datetime.fromisoformat(a.start), period_end=datetime.fromisoformat(a.end),
                 old_account_format=a.account_format, old_account_obsolete=a.account_obsolete,
                 old_account_currency=a.account_currency, privat_id=(None if a.privat_id == 'none' else a.privat_id))
    if a.mode == 'old':
        res = oracle_old.run(rec, p)
        out = {'ПоляКлюча': etalon._key(res), 'Исключение': res.error, 'Полная': res.complete,
               'ПропущеноБезСледа': [list(x) for x in res.dropped]}
    else:
        e = expected.run(rec, p, set(a.disable or ()))
        out = {'Операции': e.ops, 'Диагностика': e.diags, 'ЧтениеПолное': e.complete, 'КлассОтказа': e.failure_class,
               'ГраницаДоверия': C.iso(e.trust)}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def cmd_guard_synth(a):
    """Сторож на згенерованих файлах (записи, пакети, еталони). 1 — збіги, 2 — контроль не падає."""
    nums, names = leakguard.lexicon(a.raw)
    print('лексикон: чисел %d, власних назв %d' % (len(nums), len(names)))
    if not leakguard.control(nums, names):
        print('КОНТРОЛЬ НЕ ПАДАЄ: сторож нічого не вміє знаходити')
        return 2
    n, bad = leakguard.scan_generated(nums, names)
    print('перевірено файлів: %d; файлів зі збігами: %d; усього збігів: %d' % (n, len(bad), sum(bad.values())))
    return 1 if bad else 0


def cmd_guard_files(a):
    """Сторож перед комітом для коду й документації режиму API: як `samples.py guard`, але з `api_guard_allowed_words`."""
    import subprocess
    from sslib import guard
    nums, names = leakguard.lexicon(a.raw)
    if not leakguard.control(nums, names):
        print('КОНТРОЛЬ НЕ ПАДАЄ: сторож нічого не вміє знаходити')
        return 2
    files = list(a.files or [])
    if a.staged:
        out = subprocess.run(['git', 'diff', '--cached', '--name-only', '-z'], capture_output=True).stdout
        files += [x.decode('utf-8') for x in out.split(b'\x00') if x]
    res = guard.scan_files(files, nums, names)
    bad = sum(1 for v in res.values() if v)
    print('перевірено файлів: %d; файлів зі збігами: %d; усього збігів: %d' % (len(res), bad, sum(res.values())))
    return 1 if bad else 0


def cmd_pack(a):
    _write(a.out, R.Recording.from_dir(a.recording).pack())
    return 0


def cmd_unpack(a):
    with open(a.pack, encoding='utf-8') as f:
        R.Recording.unpack(f.read()).to_dir(a.out)
    return 0


def cmd_step2(a):
    print(step2.STEP2, file=sys.stderr)
    return STEP2_RC


STEP2_COMMANDS = ('anonymize', 'check-a', 'check-b', 'check-c', 'verify')


def main(argv):
    if argv and argv[0] in STEP2_COMMANDS:         # аргументи Step 2 тут не розбираються: команда ще не виконана
        return cmd_step2(None)
    ap = argparse.ArgumentParser(prog='apisamples', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('list').set_defaults(fn=cmd_list)
    p = sub.add_parser('synth')
    p.add_argument('--out', required=True)
    p.add_argument('--only')
    p.add_argument('--packs', action='store_true')
    p.set_defaults(fn=cmd_synth)
    sub.add_parser('selfcheck').set_defaults(fn=cmd_selfcheck)
    p = sub.add_parser('oracle')
    p.add_argument('--recording', required=True)
    p.add_argument('--mode', choices=['old', 'expected'], required=True)
    p.add_argument('--account', required=True)
    p.add_argument('--start', required=True)
    p.add_argument('--end', required=True)
    p.add_argument('--account-format', default='14', choices=['14', 'iban'])
    p.add_argument('--account-obsolete', default='')
    p.add_argument('--account-currency', default=None)
    p.add_argument('--privat-id', default='REF+REFN', choices=['REF+REFN', 'TECHNICAL_TRANSACTION_ID', 'ID', 'none'])
    p.add_argument('--disable', nargs='*', choices=sorted(expected.DEVIATIONS))
    p.set_defaults(fn=cmd_oracle)
    p = sub.add_parser('guard-synth')
    p.add_argument('--raw', required=True)
    p.set_defaults(fn=cmd_guard_synth)
    p = sub.add_parser('guard')
    p.add_argument('--raw', required=True)
    p.add_argument('--files', nargs='*')
    p.add_argument('--staged', action='store_true')
    p.set_defaults(fn=cmd_guard_files)
    p = sub.add_parser('pack')
    p.add_argument('--recording', required=True)
    p.add_argument('--out', required=True)
    p.set_defaults(fn=cmd_pack)
    p = sub.add_parser('unpack')
    p.add_argument('--pack', required=True)
    p.add_argument('--out', required=True)
    p.set_defaults(fn=cmd_unpack)
    for name in STEP2_COMMANDS:
        p = sub.add_parser(name)
        p.add_argument('rest', nargs=argparse.REMAINDER)
        p.set_defaults(fn=cmd_step2)
    a = ap.parse_args(argv)
    return a.fn(a)
