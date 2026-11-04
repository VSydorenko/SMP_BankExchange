# -*- coding: utf-8 -*-
"""Сторож витоку для згенерованих файлів режиму API: той самий `sslib.guard` (лексикон з сирих зразків, пошук у всіх
кодуваннях, контроль, що вміє падати), лише застосований до записів, пакетів і еталонів, які генерує `apisamples.py synth`.

Дозволені слова режиму API (публічні назви банку, юридична форма, міста) — окремий список `api_guard_allowed_words` у
`config.json`; спільний `guard_allowed_words` файлових форматів він не розширює."""
import os
import tempfile

from sslib import cfg as cfgmod, guard

from . import etalon, synth


def api_config(path=None):
    cfg = cfgmod.load(path)
    cfg = dict(cfg)
    cfg['guard_allowed_words'] = list(cfg.get('guard_allowed_words', [])) + list(cfg.get('api_guard_allowed_words', []))
    return cfg


def lexicon(raw_root, config_path=None):
    return guard.raw_lexicon(api_config(config_path), raw_root)


def generate(outdir):
    """Пише всі записи (тека), пакети й еталони у `outdir`. -> перелік шляхів файлів."""
    paths = []
    for s in synth.all_scenarios():
        rec = s.recording()
        d = os.path.join(outdir, 'recordings', s.bank, s.sid)
        rec.to_dir(d)
        paths += [os.path.join(d, f) for f in os.listdir(d)]
        for sub, name, text in (('packs', s.name + '.json', rec.pack()), ('etalons', s.etalon_name + '.json', etalon.dumps(etalon.build(s)[0]))):
            fp = os.path.join(outdir, sub, name)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, 'w', encoding='utf-8', newline='\n') as f:
                f.write(text)
            paths.append(fp)
    return paths


def scan_generated(nums, names, outdir=None):
    """-> (кількість файлів, {шлях: кількість збігів} лише зі збігами)."""
    if outdir is None:
        with tempfile.TemporaryDirectory() as d:
            return scan_generated(nums, names, d)
    files = generate(outdir)
    res = guard.scan_files(files, nums, names)
    return len(files), {k: v for k, v in res.items() if v}


def control(nums, names):
    """Контроль: сторож мусить знайти підмішану в нейтральний текст сиру лексему (інакше він нічого не доводить)."""
    return guard.control(nums, names) > 0
