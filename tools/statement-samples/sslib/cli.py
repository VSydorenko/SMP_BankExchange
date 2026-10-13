# -*- coding: utf-8 -*-
"""Команди інструменту. Перевірки (check-a / check-b / check-c / verify / guard) повертають код 1 при порушенні."""
import argparse
import json
import os

from . import anon as anonmod, cfg as cfgmod, checks, containers


def _load(a):
    cfg = cfgmod.load(a.config)
    samples = cfg['samples']
    if getattr(a, 'only', None):
        samples = [s for s in samples if s['id'] in a.only]
    return cfg, samples


def _anon_bytes(out, s):
    return open(os.path.join(out, s['id'] + '.bin'), 'rb').read()


def _raw_cmp(spec, raw):
    """Сирий файл після того самого скорочення (take_rows), що й у знеособленого."""
    if spec.get('take_rows'):
        return containers.walk(spec, raw, lambda r, t, k: t)
    return raw


def cmd_selfcheck(a):
    from . import selfcheck
    return 1 if selfcheck.run(a.raw) else 0


def cmd_anonymize(a):
    cfg, _ = _load(a)
    fakes, res = anonmod.anonymize_all(cfg, a.raw, a.out)
    for k, v in res.items():
        print('%s: %d байт' % (k, v))
    return 0


def _run_checks(a, which, control=False):
    cfg, samples = _load(a)
    fakes = anonmod.load_fakes(a.out, cfg)
    issued = fakes.m.get('issued', [])
    bad = 0
    report = {}
    raws = {}
    for s in samples:
        spec = cfgmod.spec(s)
        raw = cfgmod.resolve(s, a.raw)
        rc = _raw_cmp(spec, raw)
        an = _anon_bytes(a.out, s)
        raws[s['id']] = (s, rc, an)
        r = {}
        if 'a' in which:
            if control:
                r['a_control'] = checks.check_a(spec, raw, raw, cfg, issued, control=True)
            else:
                r['a'] = checks.check_a(spec, raw, an, cfg, issued)
        if 'b' in which:
            r['b'] = checks.check_b(spec, rc, an)
        if 'c' in which:
            r['c'] = checks.check_c(s, spec, rc, an, fakes)
        report[s['id']] = r
        for v in r.values():
            if not v.get('ok'):
                bad += 1
    if 'c' in which and not control:
        pr = {}
        for x, y in cfg.get('pairs', []):
            if x in raws and y in raws:
                sx, rx, ax = raws[x]
                sy, ry, ay = raws[y]
                pr[x + '|' + y] = checks.check_pair(sx, sy, rx, ry, ax, ay)
                bad += not pr[x + '|' + y]['ok']
        report['_pairs'] = pr
    return report, bad


def _print(report):
    for sid, r in report.items():
        if sid == '_pairs':
            for k, v in r.items():
                print('пара %s: %s' % (k, json.dumps(v, ensure_ascii=False)))
            continue
        for k, v in r.items():
            rest = {x: y for x, y in v.items() if x != 'ok'}
            print('%s %s ok=%s %s' % (sid, k, v.get('ok'), json.dumps(rest, ensure_ascii=False)))


def make_check(which):
    def run(a):
        report, bad = _run_checks(a, which, control=a.control)
        _print(report)
        if a.json:
            with open(a.json, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=1)
        print('ПОРУШЕНЬ: %d' % bad)
        return 1 if bad else 0
    return run


def cmd_verify(a):
    """Усі перевірки а/б/в + контроль (а) на сирому."""
    total = 0
    full = {}
    for ctrl in (True, False):
        report, bad = _run_checks(a, 'a' if ctrl else 'abc', control=ctrl)
        full['control' if ctrl else 'main'] = report
        total += bad
        print('--- %s: порушень %d' % ('контроль (а) на сирому: має давати збіги' if ctrl else 'знеособлене', bad))
        _print(report)
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(full, f, ensure_ascii=False, indent=1)
    return 1 if total else 0


def cmd_etalons(a):
    from . import etalon
    cfg, samples = _load(a)
    os.makedirs(a.out, exist_ok=True)
    for s in samples:
        text = etalon.build(s, _anon_bytes(a.out, s))
        with open(os.path.join(a.out, s['id'] + '.etalon.txt'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        print('%s: %d рядків еталона' % (s['id'], text.count('\n')))
    return 0


def cmd_epf_list(a):
    names = sorted(n for n in os.listdir(a.epf_src)
                   if os.path.isdir(os.path.join(a.epf_src, n)) and not any(x in n for x in (a.exclude or [])))
    text = '\n'.join(names) + '\n'
    if a.out:
        with open(a.out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
    print('обробок у переліку: %d' % len(names))
    return 0


def cmd_guard(a):
    """Сторож перед комітом: збіги лексем мапи у файлах (код виходу 1, якщо є) + контроль, що пошук уміє падати."""
    import subprocess
    from . import guard
    cfg = cfgmod.load(a.config)
    nums, names = guard.raw_lexicon(cfg, a.raw)
    ctl = guard.control(nums, names)
    print('лексикон: чисел %d, власних назв %d; контроль знаходить %d з підмішаних' % (len(nums), len(names), ctl))
    if ctl == 0:
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


def main(argv):
    ap = argparse.ArgumentParser(prog='samples.py')
    ap.add_argument('--config', default=None)
    sub = ap.add_subparsers(dest='cmd', required=True)

    def common(p):
        p.add_argument('--raw', required=True, help='корінь робочої копії сирих зразків (у temp/)')
        p.add_argument('--out', required=True, help='каталог знеособлених файлів і мапи (у temp/)')
        p.add_argument('--only', nargs='*', help='ідентифікатори зразків')
    p = sub.add_parser('selfcheck', help='крок 1: самоперевірка оракула на сирих зразках')
    p.add_argument('--raw', required=True)
    p.set_defaults(f=cmd_selfcheck)
    p = sub.add_parser('anonymize', help='знеособити всі зразки з конфігурації')
    common(p)
    p.set_defaults(f=cmd_anonymize)
    for name, which in (('check-a', 'a'), ('check-b', 'b'), ('check-c', 'c')):
        p = sub.add_parser(name, help='перевірка D22 (%s); ненульовий код при порушенні' % which)
        common(p)
        p.add_argument('--control', action='store_true', help='(а): контроль на сирому файлі, має дати збіги')
        p.add_argument('--json')
        p.set_defaults(f=make_check(which))
    p = sub.add_parser('verify', help='а + контроль (а) + б + в + пари')
    common(p)
    p.add_argument('--json')
    p.set_defaults(f=cmd_verify)
    p = sub.add_parser('etalons', help='еталони (текст очікуваних операцій) зі знеособлених файлів')
    common(p)
    p.set_defaults(f=cmd_etalons)
    p = sub.add_parser('epf-list', help='перелік обробок epf/src (для матриці задачі 11)')
    p.add_argument('--epf-src', required=True)
    p.add_argument('--exclude', nargs='*', default=['Сбербанк'])
    p.add_argument('--out')
    p.set_defaults(f=cmd_epf_list)
    p = sub.add_parser('guard', help='сторож перед комітом: лексеми мапи у файлах; ненульовий код при збігах')
    p.add_argument('--raw', required=True)
    p.add_argument('--files', nargs='*')
    p.add_argument('--staged', action='store_true')
    p.set_defaults(f=cmd_guard)
    a = ap.parse_args(argv)
    if not hasattr(a, 'control'):
        a.control = False
    return a.f(a)
