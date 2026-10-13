# -*- coding: utf-8 -*-
"""Сторож перед комітом: пошук у файлах лексем з мапи «реальне -> вигадане» (числа від 5 цифр і слова з
великої літери з чутливих полів усіх зразків) та значень з мапи. Нуль збігів — умова точки коміту.
Контроль: той самий пошук над текстом, у який підмішано сирі лексеми, мусить дати збіги."""
import os
import re

from . import cfg as cfgmod, containers
from .checks import DIG, WORD, lexemes


def raw_lexicon(cfg, raw_root):
    """Лексикон сторожа: числа від 5 цифр і власні назви з чутливих полів усіх зразків.
    Не беруться: числа, що збігаються зі збереженими полями (дата, сума, номер документа) будь-якого
    зразка; слова призначень (звичайні слова); слова, чий варіант з малої літери трапляється в сирих
    текстах; слова з `allowed_words` і `guard_allowed_words` (назви банків-міток зразків)."""
    sens_all, keep_nums, lower_words = [], set(), set()
    allowed = set(cfg.get('allowed_words', [])) | set(cfg.get('guard_allowed_words', []))
    for s in cfg['samples']:
        raw = cfgmod.resolve(s, raw_root)
        sens, keep = containers.fields(cfgmod.spec(s), raw)
        sens_all += sens
        for r, t, k in keep:
            keep_nums |= {x for x in lexemes(t) if x[0].isdigit()}
        for r, t, k in sens + keep:
            lower_words |= {w for w in WORD.findall(t) if w[0].islower()}
    nums, names = set(), set()
    for role, text, key in sens_all:
        for t in lexemes(text):
            if t[0].isdigit():
                if t not in keep_nums:
                    nums.add(t)
            elif role in ('NAME', 'BANKNAME') and len(t) >= 4 and t not in allowed and t.lower() not in lower_words                     and t.casefold() not in lower_words:
                names.add(t)
    return nums, names


def scan_text(text, nums, names):
    hits = set()
    for t in nums:
        if t in text and re.search(r'(?<!\d)' + re.escape(t) + r'(?!\d)', text):
            hits.add(t)
    for t in names:
        if t in text and re.search(r'(?<![^\W\d_])' + re.escape(t) + r'(?![^\W\d_])', text):
            hits.add(t)
    return hits


def scan_files(paths, nums, names):
    """-> {шлях: кількість збігів}; байти читаються як UTF-8 і як windows-1251."""
    res = {}
    for p in paths:
        b = open(p, 'rb').read()
        hits = set()
        for enc in ('utf-8', 'cp1251'):
            hits |= scan_text(b.decode(enc, errors='replace'), nums, names)
        hits |= scan_text(os.path.basename(p), nums, names)
        res[p] = len(hits)
    return res


def control(nums, names):
    """Підмішує до нейтрального тексту кілька сирих лексем; сторож мусить їх знайти."""
    sample = ['текст без даних']
    sample += sorted(nums)[:3] + sorted(names)[:3]
    return len(scan_text(' ; '.join(sample), nums, names))
