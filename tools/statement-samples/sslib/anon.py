# -*- coding: utf-8 -*-
"""Знеособлювач: сирий зразок -> знеособлений файл. Мапа «реальне -> вигадане» одна на прогін і спільна для
всіх файлів; випадкова (SystemRandom), зберігається лише в каталозі виводу (у temp/, гітігноровано)."""
import json
import os
import re

from . import cfg as cfgmod, containers, gen
from .checks import DIG, WORD


def prescan(cfg, raw_root):
    """Усі слова й числа чутливих полів усіх зразків — заборонені для вигаданих значень."""
    words, nums = set(), set()
    for s in cfg['samples']:
        raw = cfgmod.resolve(s, raw_root)
        sens, keep = containers.fields(cfgmod.spec(s), raw)
        for role, text, key in sens:
            words |= {w.casefold() for w in WORD.findall(text)}
            nums |= set(DIG.findall(text))
            t = text.strip()
            if role in ('CODE', 'ACC') and t:
                nums.add(t)
                nums.add(t.lstrip('0'))
                if re.fullmatch(r'UA\d{27}', t):
                    nums.add(t[10:].lstrip('0'))
    return words, nums


def anonymize_all(cfg, raw_root, out_dir, fakes=None):
    os.makedirs(out_dir, exist_ok=True)
    if fakes is None:
        words, nums = prescan(cfg, raw_root)
        fakes = gen.Fakes(forbidden_words=words, forbidden_numbers=nums, allowed_words=cfg.get('allowed_words', []))
    res = {}
    for s in cfg['samples']:
        raw = cfgmod.resolve(s, raw_root)
        spec = cfgmod.spec(s)
        anon = containers.walk(spec, raw, fakes.apply)
        with open(os.path.join(out_dir, s['id'] + '.bin'), 'wb') as f:
            f.write(anon)
        res[s['id']] = len(anon)
    with open(os.path.join(out_dir, 'map.json'), 'w', encoding='utf-8') as f:
        json.dump(fakes.dump(), f, ensure_ascii=False)
    return fakes, res


def load_fakes(out_dir, cfg):
    with open(os.path.join(out_dir, 'map.json'), encoding='utf-8') as f:
        m = json.load(f)
    fk = gen.Fakes(allowed_words=cfg.get('allowed_words', []))
    fk.load(m)
    return fk
