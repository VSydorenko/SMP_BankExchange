# -*- coding: utf-8 -*-
"""Перевірки D22 а / б / в для знеособлених записів відповідей API (Step 2 задачі 2 плану 05а) і випуск еталонів.

Кожна перевірка повертає словник лише з кількостей і назв полів (значень немає) і список `problems` (шлях поля, не значення);
команда CLI перетворює непорожній `problems` на ненульовий код виходу.

* **а** -- жодне чутливе значення сирого запису не трапляється в знеособленому: по байтах розкодованих тіл і файлів запису, в
  усіх кодуваннях (UTF-8, UTF-16LE/BE, cp1251, cp866, `\\uXXXX` великими й малими, URL-кодування, Base64 зі зсувами 0/1/2),
  по розкодованих рядках JSON і по шляхах і запитах. Чутливе -- значення полів з роллю не KEEP (`schema.py`), їхні похідні
  (хвіст 14 цифр IBAN, ядро номера), числа від 5 цифр і власні назви з імен та призначень. Контроль: та сама перевірка на
  сирому записі мусить дати збіги (інакше вона нічого не доводить).
* **б** -- структура та сама: скелет тіла (ключі, порядок, типи, довжини масивів, пробіли) побайтово однаковий, значення KEEP
  не змінилися, замінені мають ту саму форму (довжина й клас символів для кодів, рахунків, ідентифікаторів; «порожнє /
  непорожнє» для назв і призначень), кодування тіла те саме, послідовність обмінів, статуси й заголовки ті самі.
* **в** -- оракул (обидва режими) на сирому й знеособленому читанні дає ті самі значення в усіх полях, крім замінених; замінене
  поле мусить дорівнювати значенню з мапи (мапа лише читається).

Ґенератори, мапа й сторож -- `sslib` (`gen.Fakes`, `guard`); тут їх використано, не скопійовано."""
import base64
import json
import os
import re
import urllib.parse

from sslib import cfg as cfgmod, gen, guard
from sslib.checks import DIG, WORD
from sslib.util import ws

from . import anonymize as A, common as C, etalon, jsonspan, readings as RD, recording as R, schema
from .synth import BANK_KEYS

SEP = b'\n\xff\xfe\x00SEP\x00\n'
MIN_WHOLE = 8                        # найкоротший «цілий» токен для пошуку підрядком
MIN_WHOLE_POSITIONAL = 6             # довші за це незмінені на своєму місці значення -- збіг; коротші лише рахуються
NAME_ROLES = ('NAME', 'BANKNAME', 'PURPOSE')


class CheckError(Exception):
    """Збій самої перевірки (відсутній файл тощо)."""


def raw_dir_of(raw_root, bank, label):
    return os.path.join(raw_root, bank, label)


def anon_dir_of(anon_root, bank):
    return os.path.join(anon_root, bank)


def map_path_of(map_dir, bank):
    return os.path.join(map_dir, bank + '.json')


def shape(s):
    """Форма рядка: цифра -> 9, велика літера -> A, мала -> a, решта як є."""
    return ''.join('9' if c.isdigit() else ('A' if c.isupper() else ('a' if c.isalpha() else c)) for c in s)


# ======================================================================== (а)
def variants(t):
    """Усі подання токена в байтах: кодування, JSON-екранування, URL, Base64 зі зсувами."""
    out = set()
    out.add(t.encode('utf-8'))
    out.add(t.encode('utf-16le'))
    out.add(t.encode('utf-16be'))
    for enc in ('cp1251', 'cp866'):
        try:
            out.add(t.encode(enc))
        except UnicodeEncodeError:
            pass
    esc = json.dumps(t, ensure_ascii=True)[1:-1]
    out.add(esc.encode('ascii'))
    out.add(re.sub(r'\\u([0-9a-f]{4})', lambda m: '\\u' + m.group(1).upper(), esc).encode('ascii'))
    for q in (urllib.parse.quote(t, safe=''), urllib.parse.quote_plus(t)):
        out.add(q.encode('ascii'))
        out.add(re.sub(r'%([0-9A-F]{2})', lambda m: '%' + m.group(1).lower(), q).encode('ascii'))
    for base in (t.encode('utf-8'), t.encode('utf-16le')):
        for shift in (0, 1, 2):
            enc = base64.b64encode(b'\x00' * shift + base).decode('ascii')
            cut = -(-8 * shift // 6)
            core = enc[cut:len(enc) - 2]
            if len(core) >= 8:
                out.add(core.encode('ascii'))
    return {v for v in out if len(v) >= MIN_WHOLE}


def derived_acc(v):
    """Похідні чутливі токени рахунку: хвіст 14 цифр і ядро IBAN."""
    out = set()
    if re.fullmatch(r'UA\d{27}', v):
        out |= {v[-14:], v[10:], v[10:].lstrip('0')}
    return {x for x in out if x}


class Sensitive:
    """Чутливі токени одного запису. Лічильники -- у `counts()`; значень не друкує."""

    def __init__(self):
        self.whole = set()            # цілі значення й похідні (пошук підрядком)
        self.nums = set()             # числа від 5 цифр
        self.names = set()            # власні назви (слова з великої літери)
        self.positional = []          # [(індекс обміну, шлях у дереві, роль, значення)] -- для порівняння на своєму місці
        self.keep_blob = ''           # усі значення KEEP-полів (крім вільного тексту): що там є, політика лишає видимим
        self.generic = set()          # загальні фрази словника замін

    def exempt(self, v):
        """Не витік: значення з однієї повторюваної цифри/літери (нульовий «неіснуючий» рахунок), частина значення KEEP-поля
        (обороти дня = сума єдиної операції; DLR, що є частиною номера документа) і загальна фраза, яку генератор видає сам."""
        v = str(v).strip()
        return len(set(v)) <= 1 or v in self.generic or v in self.keep_blob

    def counts(self):
        return {'whole': len(self.whole), 'nums': len(self.nums), 'names': len(self.names), 'positional': len(self.positional)}


def collect(bank, rec, cfg):
    sens = Sensitive()
    keep_nums, keep_words, lower_words, keep_values = set(), set(), set(), set()
    allowed = {w.casefold() for w in list(cfg.get('allowed_words', [])) + list(cfg.get('guard_allowed_words', [])) +
               list(cfg.get('api_guard_allowed_words', []))}
    texts = []                                  # (роль, значення)
    for idx, ex in enumerate(rec.exchanges):
        req = ex['request']
        segs = req['path'].split('/')
        for i, role in A.path_segments(bank, req['path']).items():
            texts.append((role, segs[i]))
            sens.positional.append((idx, ('path', i), role, segs[i]))
        for k, _, v in A.query_pairs_raw(req['query']):
            if bank == 'privat' and k in ('acc', 'followId'):
                role = 'ACC' if k == 'acc' else 'ID'
                texts.append((role, v))
                sens.positional.append((idx, ('query', k), role, v))
        if not ex['response']:
            continue
        root = jsonspan.parse(R.body_text(ex))
        for role, nd, where in schema.leaves(bank, req['path'], ex['response']['status'], root):
            if nd.kind == 'lit':
                continue
            val = nd.value if nd.kind == 'str' else nd.value
            if role == 'KEEP':
                if not (nd.kind == 'str' and where and where[-1] in A.FREE_TEXT_KEEP):
                    keep_values.add(val.strip() if nd.kind == 'str' else val)
                if nd.kind == 'str':
                    keep_nums |= set(DIG.findall(val))
                    keep_words |= {w.casefold() for w in WORD.findall(val)}
                    lower_words |= {w.casefold() for w in WORD.findall(val) if w[0].islower()}
                else:
                    keep_nums |= set(DIG.findall(val))
                continue
            if val == '' or (nd.kind == 'str' and val.strip() == ''):
                continue
            texts.append((role, val.strip() if nd.kind == 'str' else val))
            sens.positional.append((idx, ('body',) + tuple(where), role, val))
    for role, v in texts:
        if role in NAME_ROLES:
            lower_words |= {w.casefold() for w in WORD.findall(v) if w[0].islower()}
    for role, v in texts:
        if role in ('ID', 'ACC', 'CODE', 'SCRAMBLE') and len(v) >= MIN_WHOLE:
            sens.whole.add(v)
        if role == 'ACC':
            sens.whole |= {x for x in derived_acc(v) if len(x) >= MIN_WHOLE}
        if role in NAME_ROLES and len(v) >= (MIN_WHOLE if role != 'PURPOSE' else 12):
            sens.whole.add(v)
        for t in DIG.findall(v):
            if len(set(t)) > 1:
                sens.nums.add(t)
        if role in NAME_ROLES:
            for w in WORD.findall(v):
                if len(w) >= 4 and w[0].isupper() and w.casefold() not in allowed and w.casefold() not in lower_words \
                        and w.casefold() not in keep_words:
                    sens.names.add(w)
    sens.nums -= keep_nums
    sens.generic = {x for lst in gen.PHRASES.values() for x in lst} | {x for lst in gen.SHORT.values() for x in lst}
    sens.keep_blob = '\n'.join(sorted(keep_values))
    sens.whole = {t for t in sens.whole if not sens.exempt(t)}
    return sens


def haystacks(directory, bank):
    """Байти запису з диска й похідні подання: (великий блоб для пошуку підрядком, блоб для лексем).
    Блоб лексем не містить Base64 (випадкові п'ятицифрові серії в Base64 дали б хибні збіги)."""
    rec = R.Recording.from_dir(directory)
    sub, lex = [], []
    for name in sorted(os.listdir(directory)):
        if name.endswith('.json'):
            with open(os.path.join(directory, name), 'rb') as f:
                sub.append(f.read())
    for ex in rec.exchanges:
        req = ex['request']
        decoded = urllib.parse.unquote(req['path'] + '?' + req['query'])
        sub.append(decoded.encode('utf-8'))
        lex.append(decoded.encode('utf-8'))
        if ex['response']:
            body = R.body_bytes(ex)
            sub.append(body)
            lex.append(body)
            try:
                root = jsonspan.parse(R.body_text(ex))
            except jsonspan.JsonSpanError:
                continue
            strings = []

            def walk(nd):
                if nd.kind == 'obj':
                    for k, v in nd.items:
                        strings.append(k)
                        walk(v)
                elif nd.kind == 'arr':
                    for v in nd.items:
                        walk(v)
                elif nd.kind in ('str', 'num'):
                    strings.append(nd.value)
            walk(root)
            blob = '\n'.join(strings).encode('utf-8')
            sub.append(blob)
            lex.append(blob)
        else:
            sub.append(ex['failure']['text'].encode('utf-8'))
    return SEP.join(sub), SEP.join(lex)


def scan_whole(blob, tokens):
    """Токени (рядки), що трапляються в блобі в будь-якому поданні. Індекс за 8-байтовим префіксом -- один прохід."""
    idx = {}
    tokens = sorted(tokens)
    for tid, t in enumerate(tokens):
        for nb in variants(t):
            idx.setdefault(nb[:MIN_WHOLE], []).append((nb, tid))
    found = set()
    for i in range(len(blob) - MIN_WHOLE + 1):
        lst = idx.get(blob[i:i + MIN_WHOLE])
        if lst:
            for nb, tid in lst:
                if blob.startswith(nb, i):
                    found.add(tid)
    return {tokens[t] for t in found}


def scan_lexemes(blob, nums, names):
    """Числа й слова сторожа (`sslib.guard.decodings`): точний збіг серії цифр / слова."""
    got_nums, got_names = set(), set()
    for text in guard.decodings(blob):
        got_nums |= {t for t in DIG.findall(text) if t in nums}
        got_names |= {t for t in WORD.findall(text) if t in names}
    return got_nums, got_names


def check_a(bank, raw_dir, anon_dir, cfg=None, control=False):
    """Перевірка (а). `control=True` -- та сама перевірка, але «знеособлений» запис = сирий: мусить дати збіги."""
    cfg = cfg or cfgmod.load()
    raw = R.Recording.from_dir(raw_dir)
    sens = collect(bank, raw, cfg)
    target = raw_dir if control else anon_dir
    sub, lex = haystacks(target, bank)
    whole = scan_whole(sub, sens.whole)
    nums, names = scan_lexemes(lex, sens.nums, sens.names)
    unchanged_long = unchanged_short = misaligned = 0
    if not control:
        anon = R.Recording.from_dir(anon_dir)
        pos_anon = positional_values(bank, anon)
        for idx, where, role, val in sens.positional:
            av = pos_anon.get((idx, where))
            if av is None:
                misaligned += 1
            elif av == val and not sens.exempt(val):
                if len(str(val)) >= MIN_WHOLE_POSITIONAL:
                    unchanged_long += 1
                else:
                    unchanged_short += 1
    hits = len(whole) + len(nums) + len(names) + unchanged_long
    return {'bank': bank, 'control': control, 'exchanges': len(raw.exchanges), 'tokens': sens.counts(),
            'hits_whole': len(whole), 'hits_nums': len(nums), 'hits_names': len(names),
            'unchanged_long': unchanged_long, 'unchanged_short_info': unchanged_short, 'misaligned': misaligned,
            'hits': hits, 'problems': ['збіги: %d' % hits] if hits else []}


def positional_values(bank, rec):
    out = {}
    for idx, ex in enumerate(rec.exchanges):
        req = ex['request']
        segs = req['path'].split('/')
        for i in A.path_segments(bank, req['path']):
            out[(idx, ('path', i))] = segs[i]
        for k, _, v in A.query_pairs_raw(req['query']):
            if bank == 'privat' and k in ('acc', 'followId'):
                out[(idx, ('query', k))] = v
        if ex['response']:
            root = jsonspan.parse(R.body_text(ex))
            for role, nd, where in schema.leaves(bank, req['path'], ex['response']['status'], root):
                if nd.kind != 'lit':
                    out[(idx, ('body',) + tuple(where))] = nd.value
    return out


# ======================================================================== (б)
def _body_class(raw_bytes):
    try:
        raw_bytes.decode('utf-8')
        utf8 = True
    except UnicodeDecodeError:
        utf8 = False
    return (raw_bytes[:3] == b'\xef\xbb\xbf', utf8, any(b > 127 for b in raw_bytes))


def check_b(bank, raw_dir, anon_dir, map_path, cfg=None):
    """Перевірка (б): структура запису збережена."""
    rec, b = A.load_bank(bank, raw_dir, map_path, cfg)
    b.build_sweep()
    problems, counts = [], {'exchanges': 0, 'leaves': 0, 'keep_equal': 0, 'replaced_shape': 0, 'free_text_cleaned': 0}

    def bad(msg):
        problems.append(msg)

    try:
        anon = R.Recording.from_dir(anon_dir)
    except R.FormatError:
        bad('знеособлений запис порушує формат FORMAT.md v1')
        return {'bank': bank, 'counts': counts, 'problems': problems}

    if rec.manifest != anon.manifest:
        bad('маніфест відрізняється')
    if len(rec.exchanges) != len(anon.exchanges):
        bad('кількість обмінів')
        return {'bank': bank, 'counts': counts, 'problems': problems}
    for n, (x, y) in enumerate(zip(rec.exchanges, anon.exchanges), 1):
        counts['exchanges'] += 1
        tag = 'обмін %d' % n
        if set(x) != set(y) or list(x) != list(y):
            bad(tag + ': ключі обміну')
        for k in ('format', 'formatVersion', 'seq', 'scenario', 'startedUtc', 'durationMs'):
            if x.get(k) != y.get(k):
                bad('%s: %s' % (tag, k))
        if x['request']['method'] != y['request']['method'] or x['request']['host'] != y['request']['host'] \
                or set(x['request']) != set(y['request']):
            bad(tag + ': метод/хост/ключі запиту')
        _check_request(bank, tag, x['request'], y['request'], bad)
        if (x['response'] is None) != (y['response'] is None):
            bad(tag + ': response/failure')
            continue
        if x['response'] is None:
            if x['failure']['kind'] != y['failure']['kind'] or b.clean_text(x['failure']['text']) != y['failure']['text']:
                bad(tag + ': failure')
            continue
        rx, ry = x['response'], y['response']
        if rx['status'] != ry['status'] or rx['headers'] != ry['headers'] or set(rx) != set(ry):
            bad(tag + ': статус/заголовки')
        bx, by = R.body_bytes(x), R.body_bytes(y)
        if ry['bodyLength'] != len(by) or rx['bodyLength'] != len(bx):
            bad(tag + ': bodyLength')
        if _body_class(bx) != _body_class(by):
            bad(tag + ': кодування тіла')
        _check_body(bank, tag, x, y, b, counts, bad)
    return {'bank': bank, 'counts': counts, 'problems': problems}


def _check_request(bank, tag, rx, ry, bad):
    sx, sy = rx['path'].split('/'), ry['path'].split('/')
    if len(sx) != len(sy):
        bad(tag + ': довжина шляху')
        return
    roles = A.path_segments(bank, rx['path'])
    for i, (a, c) in enumerate(zip(sx, sy)):
        if (shape(a) != shape(c)) if i in roles else (a != c):
            bad('%s: сегмент шляху %d' % (tag, i))
    qx, qy = A.query_pairs_raw(rx['query']), A.query_pairs_raw(ry['query'])
    if [(k, e) for k, e, _ in qx] != [(k, e) for k, e, _ in qy]:
        bad(tag + ': ключі запиту')
        return
    for (k, _, a), (_, _, c) in zip(qx, qy):
        replaced = bank == 'privat' and k in ('acc', 'followId')
        if (shape(a) != shape(c)) if replaced else (a != c):
            bad('%s: параметр запиту %s' % (tag, k))


def _check_body(bank, tag, x, y, b, counts, bad):
    try:
        tx, ty = R.body_text(x), R.body_text(y)
        nx, ny = jsonspan.parse(tx), jsonspan.parse(ty)
    except UnicodeDecodeError:
        bad(tag + ': тіло не декодується за charset із content-type')
        return
    except jsonspan.JsonSpanError:
        bad(tag + ': тіло не JSON')
        return
    if jsonspan.skeleton(tx, nx) != jsonspan.skeleton(ty, ny):
        bad(tag + ': скелет тіла (ключі, типи, довжини масивів, пробіли)')
        return
    path, status = x['request']['path'], x['response']['status']
    lx = schema.leaves(bank, path, status, nx)
    ly = schema.leaves(bank, path, status, ny)
    if len(lx) != len(ly):
        bad(tag + ': кількість скалярів')
        return
    for (role, a, where), (_, c, _) in zip(lx, ly):
        counts['leaves'] += 1
        here = '%s: %s' % (tag, '.'.join(str(w) for w in where))
        if jsonspan.scalar_type(a) != jsonspan.scalar_type(c):
            bad(here + ': тип')
            continue
        if role == 'KEEP':
            key = next((w for w in reversed(where) if isinstance(w, str)), '')
            if a.kind == 'str' and key in A.FREE_TEXT_KEEP and b.clean_text(a.value) != a.value:
                counts['free_text_cleaned'] += 1
                if b.clean_text(a.value) != c.value:
                    bad(here + ': вільний текст')
            elif a.value != c.value:
                bad(here + ': KEEP змінено')
            else:
                counts['keep_equal'] += 1
            continue
        if a.kind == 'lit':
            if a.value != c.value:
                bad(here + ': літерал')
            continue
        if role in NAME_ROLES:
            if (a.value.strip() == '') != (c.value.strip() == ''):
                bad(here + ': порожнє/непорожнє')
            else:
                counts['replaced_shape'] += 1
        else:
            if shape(a.value) != shape(c.value):
                bad(here + ': форма')
            else:
                counts['replaced_shape'] += 1


# ======================================================================== (в)
class Mapper:
    """Очікувана заміна за мапою: лише читання. Відсутнє в мапі -> KeyError (це збій перевірки, не нова заміна)."""

    def __init__(self, bank):
        self.b = bank
        self.m = bank.fakes.m

    def acc(self, raw):
        if raw == '':
            return raw
        m14 = self.m.get('acc14', {})
        if raw in m14:
            return m14[raw]
        v = raw.strip()
        if re.fullmatch(r'UA\d{27}', v):
            core = v[10:]
            st = core.lstrip('0')
            new = self.m['core'][st].rjust(len(core), '0') if st else core
            bban = v[4:10] + new
            return 'UA' + gen.iban_check_digits('UA', bban) + bban
        if re.fullmatch(r'\d+', v):
            st = v.lstrip('0')
            return v if not st else '0' * (len(v) - len(st)) + self.m['core'][st]
        return self.m['scramble'][v]

    def ident(self, raw):
        return raw if raw == '' else self.m['ident'][raw]

    def code(self, raw):
        if raw.strip() == '':
            return raw
        v = raw.strip()
        return self.m['code'][v] if v in self.m['code'] else self.m['scramble'][v]

    def name(self, raw):
        if raw.strip() == '':
            return raw
        lead = raw[:len(raw) - len(raw.lstrip())]
        trail = raw[len(raw.rstrip()):]
        return lead + self.m['text']['name:' + ws(raw.strip())] + trail

    def text(self, raw):
        return self.b.clean_text(raw)


_PURPOSE_TAIL = re.compile(r'((?: Сума комісії \S+)?(?: Кешбек \S+)?)$')


def purpose_shape(s):
    """Форма призначення: непорожнє?, хвіст «Сума комісії / Кешбек» (з KEEP-чисел), маркер платника юросіб, нове поле
    складання (переніс рядка між description і comment)."""
    return (s.strip() != '', _PURPOSE_TAIL.search(s).group(1), ' Фактичний платник:' in s, '\n' in s.strip())


class Diff:
    def __init__(self, bank_name, mapper):
        self.bank = bank_name
        self.mp = mapper
        self.problems = []
        self.compared = 0
        self.replaced = 0

    def rules(self):
        mp = self.mp
        r = {'НомерСчета': mp.acc, 'КонтрагентНомерСчета': mp.acc, 'КонтрагентКод': mp.code,
             'КонтрагентНаименование': mp.name, 'ИдентификаторОперации': mp.ident, 'Ид': mp.ident}
        if self.bank != 'privat':
            r['НомерДокумента'] = mp.ident
        return r

    def cmp(self, a, b, path):
        if isinstance(a, dict):
            if not isinstance(b, dict) or list(a) != list(b):
                self.problems.append(path + ': ключі')
                return
            for k in a:
                self.field(k, a[k], b[k], path + '.' + k)
        elif isinstance(a, list):
            if not isinstance(b, list) or len(a) != len(b):
                self.problems.append(path + ': довжина')
                return
            for i, (x, y) in enumerate(zip(a, b)):
                self.cmp(x, y, '%s[%d]' % (path, i))
        else:
            self.compared += 1
            if a != b:
                self.problems.append(path)

    def field(self, k, a, b, path):
        rules = self.rules()
        if k == 'НазначениеПлатежа':
            self.compared += 1
            self.replaced += 1
            if purpose_shape(a) != purpose_shape(b):
                self.problems.append(path + ': форма призначення')
            return
        if k in ('ОписаниеБанка', 'text') and isinstance(a, str):
            self.compared += 1
            if self.mp.text(a) != b:
                self.problems.append(path)
            return
        if k in rules and isinstance(a, str):
            self.compared += 1
            self.replaced += 1
            try:
                want = rules[k](a)
            except KeyError:
                self.problems.append(path + ': немає в мапі')
                return
            if want != b:
                self.problems.append(path + ': не дорівнює значенню з мапи')
            return
        if k == 'ОтступыПрименены':
            self.compared += 1
            if sorted(set(a) - {'dev5'}) != sorted(set(b) - {'dev5'}):
                self.problems.append(path)
            return
        if k == 'Запросы':
            return                                   # окремо
        self.cmp(a, b, path)


def _outcome(reading, label):
    """-> ('ok', словник еталона) | ('exc', ім'я виняткy)."""
    try:
        d, exp, old = etalon.build_from(reading.recording(), reading.params, sid=reading.id, title=label, focus=[], macro=reading.name,
                                        synthetic=False)
        return 'ok', d
    except Exception as e:                                  # noqa: BLE001 -- порівнюється вид винятку, не текст
        return 'exc', type(e).__name__


def check_c(bank, raw_dir, anon_dir, map_path, cfg=None):
    """Перевірка (в): оракул на сирому й знеособленому читанні."""
    rec, b = A.load_bank(bank, raw_dir, map_path, cfg)
    b.build_sweep()
    anon = R.Recording.from_dir(anon_dir)
    mp = Mapper(b)
    rr, ra = RD.readings(rec), RD.readings(anon)
    problems = []
    res = {'bank': bank, 'readings': len(rr), 'compared_ok': 0, 'both_exception': 0, 'fields_compared': 0, 'fields_replaced': 0,
           'requests_compared': 0}
    if [r.id for r in rr] != [r.id for r in ra]:
        problems.append('перелік читань')
        res['problems'] = problems
        return res
    for r1, r2 in zip(rr, ra):
        tag = r1.id
        k1, o1 = _outcome(r1, tag)
        k2, o2 = _outcome(r2, tag)
        if k1 != k2 or (k1 == 'exc' and o1 != o2):
            problems.append('%s: результат оракула (%s / %s)' % (tag, k1, k2))
            continue
        if k1 == 'exc':
            res['both_exception'] += 1
            continue
        try:
            want_account = mp.acc(r1.params.account)
        except KeyError:
            want_account = None
        if want_account != r2.params.account:
            problems.append(tag + ': рахунок параметрів')
        d = Diff(bank, mp)
        d.cmp(o1['expected'], o2['expected'], tag + '.expected')
        d.cmp(o1['oldProcessing'], o2['oldProcessing'], tag + '.oldProcessing')
        d.cmp(o1['dependsOn'], o2['dependsOn'], tag + '.dependsOn')
        d.cmp({k: v for k, v in o1['parameters'].items() if k != 'НомерСчета'},
              {k: v for k, v in o2['parameters'].items() if k != 'НомерСчета'}, tag + '.parameters')
        want_req = []
        for ex in r1.exchanges:
            q = b.request(ex['request'])
            want_req.append({'Метод': q['method'], 'Хост': q['host'], 'Путь': q['path'],
                             'Запрос': [list(kv) for kv in urllib.parse.parse_qsl(q['query'], keep_blank_values=True)]})
        got_req = o2['expected']['Запросы']
        if want_req != got_req:
            problems.append(tag + ': запити')
        res['requests_compared'] += len(want_req)
        problems += d.problems
        res['compared_ok'] += 1
        res['fields_compared'] += d.compared
        res['fields_replaced'] += d.replaced
    res['problems'] = problems
    return res


# ======================================================================== випуск еталонів
def write_etalons(bank, anon_dir, out_root):
    """Читання знеособленого запису + еталони (оракулом). -> (записано, пропущено з причиною)."""
    anon = R.Recording.from_dir(anon_dir)
    written, skipped = 0, []
    for r in RD.readings(anon):
        try:
            d, _, _ = etalon.build_from(r.recording(), r.params, sid=r.id, title='знеособлений запис run1: ' + r.scenario, focus=[],
                                        macro=r.name, synthetic=False)
        except Exception as e:                              # noqa: BLE001
            skipped.append((r.id, type(e).__name__))
            continue
        rec_dir = os.path.join(out_root, 'readings', bank, r.id)
        r.recording().to_dir(rec_dir)
        path = os.path.join(out_root, 'etalons', r.etalon_name + '.json')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(etalon.dumps(d))
        written += 1
    return written, skipped
