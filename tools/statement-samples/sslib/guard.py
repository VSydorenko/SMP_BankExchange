# -*- coding: utf-8 -*-
"""Сторож перед комітом: пошук у файлах лексем з мапи «реальне -> вигадане» (числа від 5 цифр і слова з
великої літери з чутливих полів усіх зразків) та значень з мапи. Нуль збігів — умова точки коміту.
Контроль: той самий пошук над текстом, у який підмішано сирі лексеми, мусить дати збіги."""
import os
import re

from . import cfg as cfgmod, containers
from .checks import DIG, WORD, lexemes


# Поля KEEP, чиї числа лексикон сторожа НЕ бере: лише суми, дати й номери документів (публічні за природою значення). Перелік ЯВНИЙ: поле іншого роду
# (МФО, коди банків, ідентифікатори операцій, текст призначення тощо) винятку не має, і число з нього лишається в лексиконі. Ключі порівнюються після
# `norm_key`: малі літери й латинські відповідники кириличних двійників (у деяких зразках ключ містить змішані літери).
KEEP_NUM_KEYS_RAW = (
    # суми
    'AMOUNTEQ', 'SUMMA', 'SUMMAEQ', 'COMMISSION', 'amount', 'sum', 'sumeq', 'summa', 'db_sum_nom', 'db_sum_eq', 'cr_sum_nom', 'cr_sum_eq',
    'sum_pd_nom', 'sum_pd_eq', 'out_rst_no', 'out_rst_eq', 'дебет', 'кредит', 'гривневе покриття', 'гривневое покрытие',
    # дати
    'ARCDATE', 'BANKDATE', 'BOOKEDDATE', 'DOCUMENTDATE', 'dat', 'dat_arc', 'dat_end', 'dat_gn', 'dat_pr', 'dt', 'data_d', 'data_vyp', 'dat_ost_ob',
    'дата архівування', 'дата документа', 'дата операции', 'дата операції', 'дата проведення',
    # номери документів
    'DOCUMENTNO', 'doc_no', 'n_doc', 'nd', 'ndoc', 'num', 'номер документа', 'документ',
)
_TWINS = str.maketrans('аеорсіху', 'aeopcixy')


def norm_key(key):
    """Ключ поля для порівняння з переліком: малі літери, кириличні двійники латинських -- латинськими."""
    return str(key).casefold().translate(_TWINS)


KEEP_NUM_KEYS = frozenset(norm_key(k) for k in KEEP_NUM_KEYS_RAW)


def raw_lexicon(cfg, raw_root, keep_keys=KEEP_NUM_KEYS):
    """Лексикон сторожа: числа від 5 цифр і власні назви з чутливих полів усіх зразків.
    Не беруться: числа, що збігаються зі збереженими полями з ЯВНОГО переліку `KEEP_NUM_KEYS` (сума, дата, номер документа) будь-якого
    зразка (ЯВНИЙ виняток: без нього у макетах 30 збігів самих цих збережених значень); слова призначень
    (звичайні слова); слова з `allowed_words` і `guard_allowed_words` (назви банків-міток зразків).
    Виняток «слово, чий варіант з малої літери трапляється в сирих текстах» (`lower_words`) прибрано
    (раунд фінального рев'ю): він ховав би прізвище, що збігається зі звичайним словом; на наявних даних це +28 слів
    лексикону й 0 збігів."""
    sens_all, keep_nums = [], set()
    allowed = set(cfg.get('allowed_words', [])) | set(cfg.get('guard_allowed_words', []))
    for s in cfg['samples']:
        raw = cfgmod.resolve(s, raw_root)
        sens, keep = containers.fields(cfgmod.spec(s), raw)
        sens_all += sens
        for r, t, k in keep:
            if keep_keys is not None and norm_key(k) not in keep_keys:
                continue                            # число з поля поза переліком (МФО, код, текст) винятку не має
            keep_nums |= {x for x in lexemes(t) if x[0].isdigit()}
    nums, names = set(), set()
    for role, text, key in sens_all:
        for t in lexemes(text):
            if t[0].isdigit():
                if t not in keep_nums:
                    nums.add(t)
            elif role in ('NAME', 'BANKNAME') and len(t) >= 4 and t not in allowed:
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


def decodings(b):
    """Усі розкладки байтів, у яких сирі лексеми можуть стояти у файлі: UTF-8, windows-1251, cp866
    (OEM, DBF), UTF-16LE (платформа 1С, XLS) — для UTF-16LE з обома вирівнюваннями, бо рядок у
    двійковому контейнері може починатися з непарного зсуву."""
    for enc in ('utf-8', 'cp1251', 'cp866'):
        yield b.decode(enc, errors='replace')
    yield b.decode('utf-16le', errors='replace')
    yield b[1:].decode('utf-16le', errors='replace')


def scan_files(paths, nums, names):
    """-> {шлях: кількість збігів}; байти читаються в усіх розкладках з `decodings`, ім'я файлу — як є."""
    res = {}
    for p in paths:
        b = open(p, 'rb').read()
        hits = set()
        for text in decodings(b):
            hits |= scan_text(text, nums, names)
        hits |= scan_text(os.path.basename(p), nums, names)
        res[p] = len(hits)
    return res


def control(nums, names):
    """Підмішує до нейтрального тексту кілька сирих лексем; сторож мусить їх знайти."""
    sample = ['текст без даних']
    sample += sorted(nums)[:3] + sorted(names)[:3]
    return len(scan_text(' ; '.join(sample), nums, names))
