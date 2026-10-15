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
| `anonymize --raw-root R --anon-root A --map-dir M [--label run1] [--bank …]` | знеособлення справжніх записів (Step 2) | 0, 4 -- зупинка (невідоме поле тощо) |
| `check-a`, `check-b`, `check-c` (ті самі аргументи) | перевірки D22 а / б / в | 0; 1 -- порушення; 2 -- контроль (а) не падає; 4 -- зупинка |
| `sets --anon-root A --out DIR` | 12 наборів для макетів тестового розширення (записи й еталони пакетами, R15) | 0 |
| `etalons`, `verify [--report FILE]` | читання й еталони знеособлених записів; а+б+в зі звітом | як перевірки |
"""
import argparse
import json
import os
import sys
from datetime import datetime

from . import sets as sets_mod, anonymize as A, common as C, etalon, expected, leakguard, oracle_old, recording as R, schema, selfcheck, step2, synth

RC_VIOLATION = 1
RC_CONTROL = 2
RC_STOP = 4
BANKS = ('privat', 'mono-corp', 'mono-fop')


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
                 old_account_obsolete=a.account_obsolete,
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


def cmd_sets(a):
    """12 файлів наборів для макетів тестового розширення (R15): записи й еталони пакетами, синтетика і run1."""
    for name, kind, n, size in sets_mod.build(a.anon_root, a.out):
        print('%-40s %-10s записів %3d  байтів %8d' % (name, kind, n, size))
    return 0


def cmd_pack(a):
    _write(a.out, R.Recording.from_dir(a.recording).pack())
    return 0


def cmd_unpack(a):
    with open(a.pack, encoding='utf-8') as f:
        R.Recording.unpack(f.read()).to_dir(a.out)
    return 0


def _banks(a):
    return list(a.bank or BANKS)


def _paths(a, bank):
    return (step2.raw_dir_of(a.raw_root, bank, a.label), step2.anon_dir_of(a.anon_root, bank), step2.map_path_of(a.map_dir, bank))


def cmd_anonymize(a):
    """Сирий запис -> знеособлений (`<anon-root>/<банк>/`); мапа -- у `--map-dir` (поза робочим деревом)."""
    out = []
    for bank in _banks(a):
        raw, anon, mp = _paths(a, bank)
        n, _ = A.anonymize_bank(bank, raw, anon, mp)
        files = len(os.listdir(anon))
        print('anonymize %s: обмінів %d, файлів %d' % (bank, n, files))
        out.append(files)
    return 0


def _run_a(a):
    rc, lines = 0, []
    for bank in _banks(a):
        raw, anon, mp = _paths(a, bank)
        res = step2.check_a(bank, raw, anon)
        ctl = step2.check_a(bank, raw, anon, control=True)
        lines.append('a %s: обмінів %d; токенів %s; збігів: підрядки %d, числа %d, назви %d, незмінені на місці %d '
                     '(коротких без збігу: %d, без пари: %d)' % (
                         bank, res['exchanges'], res['tokens'], res['hits_whole'], res['hits_nums'], res['hits_names'],
                         res['unchanged_long'], res['unchanged_short_info'], res['misaligned']))
        lines.append('a %s: вузькі винятки за парою полів (у сирому записі): %s; значень поза дозволеними полями: %d' % (
            bank, res['pair_counts'] or '{}', res['pair_leaks']))
        lines.append('a %s КОНТРОЛЬ на сирому записі: збігів %d (мусить бути > 0)' % (bank, ctl['hits']))
        if ctl['hits'] == 0 and sum(res['tokens'][k] for k in ('whole', 'nums', 'names')) > 0:
            rc = max(rc, RC_CONTROL)             # чутливі токени є, а контроль на сирому записі їх не знаходить
        elif res['hits']:
            rc = max(rc, RC_VIOLATION)
    return rc, lines


def _run_b(a):
    rc, lines = 0, []
    for bank in _banks(a):
        raw, anon, mp = _paths(a, bank)
        res = step2.check_b(bank, raw, anon, mp)
        lines.append('b %s: %s; проблем %d' % (bank, res['counts'], len(res['problems'])))
        for p in res['problems'][:20]:
            lines.append('  ' + p)
        if res['problems']:
            rc = RC_VIOLATION
    return rc, lines


def _run_c(a):
    rc, lines = 0, []
    for bank in _banks(a):
        raw, anon, mp = _paths(a, bank)
        res = step2.check_c(bank, raw, anon, mp)
        lines.append('c %s: читань %d, зіставлено %d, обидва з винятком %d; полів зіставлено %d (з них замінених %d); запитів %d; '
                     'проблем %d' % (bank, res['readings'], res['compared_ok'], res['both_exception'], res['fields_compared'],
                                     res['fields_replaced'], res['requests_compared'], len(res['problems'])))
        for p in res['problems'][:20]:
            lines.append('  ' + p)
        if res['problems']:
            rc = RC_VIOLATION
    return rc, lines


def _guarded(fn, a):
    try:
        return fn(a)
    except (schema.UnknownField, step2.CheckError, KeyError, ValueError, OSError) as e:
        return RC_STOP, ['ЗУПИНКА: %s (%s)' % (type(e).__name__, e if isinstance(e, (schema.UnknownField, step2.CheckError)) else
                                                'без деталей')]


def _print(rc, lines):
    for l in lines:
        print(l)
    print('код виходу: %d' % rc)
    return rc


def cmd_check_a(a):
    return _print(*_guarded(_run_a, a))


def cmd_check_b(a):
    return _print(*_guarded(_run_b, a))


def cmd_check_c(a):
    return _print(*_guarded(_run_c, a))


def cmd_etalons(a):
    total = 0
    for bank in _banks(a):
        raw, anon, mp = _paths(a, bank)
        n, skipped = step2.write_etalons(bank, anon, a.anon_root)
        print('etalons %s: записано %d; пропущено %d (%s)' % (bank, n, len(skipped), ', '.join('%s:%s' % x for x in skipped)))
        total += n
    return 0


def cmd_verify(a):
    """а, б, в по всіх банках + звіт (`--report`): лише команди, кількості й коди виходу."""
    base = '--raw-root %s --label %s --anon-root %s --map-dir %s' % (a.raw_root, a.label, a.anon_root, a.map_dir)
    report, worst = [], 0
    for name, fn in (('check-a', _run_a), ('check-b', _run_b), ('check-c', _run_c)):
        rc, lines = _guarded(fn, a)
        report.append('$ python -P tools/statement-samples/apisamples.py %s %s' % (name, base))
        report += lines
        report.append('код виходу: %d' % rc)
        report.append('')
        worst = max(worst, rc)
    report.append('verify: найгірший код виходу %d' % worst)
    text = '\n'.join(report) + '\n'
    print(text)
    if a.report:
        os.makedirs(os.path.dirname(os.path.abspath(a.report)), exist_ok=True)
        with open(a.report, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
    return worst


def main(argv):
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
    p.add_argument('--account-obsolete', default='')
    p.add_argument('--account-currency', default=None)
    p.add_argument('--privat-id', default='ID', choices=['REF+REFN', 'TECHNICAL_TRANSACTION_ID', 'ID', 'none'])
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
    p = sub.add_parser('sets')
    p.add_argument('--anon-root', required=True, help='знеособлений вихід run1 (etalons/, readings/)')
    p.add_argument('--out', required=True)
    p.set_defaults(fn=cmd_sets)
    p = sub.add_parser('pack')
    p.add_argument('--recording', required=True)
    p.add_argument('--out', required=True)
    p.set_defaults(fn=cmd_pack)
    p = sub.add_parser('unpack')
    p.add_argument('--pack', required=True)
    p.add_argument('--out', required=True)
    p.set_defaults(fn=cmd_unpack)
    for name, fn in (('anonymize', cmd_anonymize), ('check-a', cmd_check_a), ('check-b', cmd_check_b), ('check-c', cmd_check_c),
                     ('etalons', cmd_etalons), ('verify', cmd_verify)):
        p = sub.add_parser(name)
        p.add_argument('--raw-root', required=True, help='корінь сирих записів: <корінь>/<банк>/<мітка>/')
        p.add_argument('--label', default='run1')
        p.add_argument('--anon-root', required=True, help='знеособлені записи: <корінь>/<банк>/')
        p.add_argument('--map-dir', required=True, help='мапа «реальне -> вигадане» (поза робочим деревом): <тека>/<банк>.json')
        p.add_argument('--bank', nargs='*', choices=BANKS)
        if name == 'verify':
            p.add_argument('--report')
        p.set_defaults(fn=fn)
    a = ap.parse_args(argv)
    return a.fn(a)
