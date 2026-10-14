# -*- coding: utf-8 -*-
"""Перевірки знеособлення D22 а / б / в. Кожна повертає словник лише з кількостей і прапорців
(значень полів у результатах немає) та поле `ok`. Команди CLI перетворюють `ok=False` на ненульовий
код виходу."""
import re
from collections import Counter

from . import containers, corpus, gen, legacy, named
from .schema import KEEP, CODE, ACC, NAME, BANKNAME, PURPOSE, SCRAMBLE
from .util import ws, q2, split_csv_quoted

DIG = re.compile(r'\d{5,}')
WORD = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґ]+(?:['’ʼ][A-Za-zА-Яа-яІіЇїЄєҐґ]+)*")
IBAN_LIKE = re.compile(r'(?<![A-Za-z0-9])[A-Z]{2}\d{2}[A-Z0-9]{11,30}(?![A-Za-z0-9])')
NUM_8_10 = re.compile(r'(?<!\d)(?:\d{8}|\d{10})(?!\d)')
DELIMITED = ('csv', 'xml')


def lexemes(text):
    """Лексеми для перевірки (а): числа з 5+ цифр (не з однієї повторюваної цифри) і слова з великої
    літери довжиною від 3."""
    out = set()
    for m in DIG.finditer(text):
        t = m.group(0)
        if len(set(t)) > 1:
            out.add(t)
    for m in WORD.finditer(text):
        t = m.group(0)
        if len(t) >= 3 and t[0].isupper():
            out.add(t)
    return out


def views(data):
    return [data.decode('cp1251', errors='replace'), data.decode('utf-16le', errors='ignore'),
            data[1:].decode('utf-16le', errors='ignore')]


def _found(text, tok, delimited):
    start = 0
    isd = tok[0].isdigit()
    while True:
        i = text.find(tok, start)
        if i < 0:
            return False
        if not delimited and isd:
            return True
        j = i + len(tok)
        if isd:
            ok = (i == 0 or not text[i - 1].isdigit()) and (j >= len(text) or not text[j].isdigit())
        else:
            ok = (i == 0 or not text[i - 1].isalpha()) and (j >= len(text) or not text[j].isalpha())
        if ok:
            return True
        start = i + 1


def build_lexicon(spec, raw, allowed, verbatim=()):
    """-> (лексикон чутливих лексем, лічильники виключень, перелік повних значень)."""
    sens, keep = containers.fields(spec, raw)
    struct = containers.structure_words(spec, raw)
    S = set()
    values = set()
    for role, text, key in sens:
        S |= lexemes(text)
        v = ws(text)
        if len(v) >= 6 and role in (NAME, BANKNAME, PURPOSE, CODE, ACC):
            values.add(v)
    K = set()
    for role, text, key in keep:
        K |= lexemes(text)
    ST = set()
    for w in struct:
        ST |= lexemes(str(w)) | {x for x in WORD.findall(str(w))}
    A = set(allowed)
    vb = {ws(t) for t in verbatim}
    lex = {t for t in S if t not in K and t not in ST and t not in A}
    values = {v for v in values if v not in vb}
    stats = dict(sensitive_lexemes=len(S), excluded_preserved=len(S & K), excluded_structure=len(S & ST),
                 excluded_allowed=len(S & A), keep_lexemes=len(K), lexicon=len(lex), values=len(values))
    return lex, stats, values


def find_hits(lex, values, anon, container, units=None):
    """Пошук лексем і повних значень у знеособленому. Для контейнерів із роздільниками (CSV, XML) —
    по всьому тексту в усіх поданнях байтів; для решти (DBF, фіксована ширина, XLS) числа шукаються по
    полях (`units`) з межами поля, бо цифри сусідніх полів зливаються в один ряд, а слова — по всьому тексту."""
    delim = container in DELIMITED
    hits_lex, hits_val = set(), set()
    texts = views(anon)
    for text in texts:
        for t in lex:
            if t in hits_lex or t not in text:
                continue
            if t[0].isdigit() and not delim:
                continue                      # цифри шукаємо по полях нижче
            if _found(text, t, delim):
                hits_lex.add(t)
        flat = re.sub(r'\s+', ' ', text)
        for v in values:
            if v not in hits_val and v in flat:
                hits_val.add(v)
    if not delim:
        for u in (units or []):
            for t in lex:
                if t[0].isdigit() and t not in hits_lex and t in u and _found(u, t, True):
                    hits_lex.add(t)
    return hits_lex, hits_val


def pattern_scan(spec, anon, issued):
    """Додатковий шаблонний пошук: кожен IBAN-подібний рядок і кожне 8/10-цифрове число знеособленого
    мусить бути вигаданим (є серед виданих значень) або не кодом (лежить у збереженому полі:
    дата, сума, номер документа)."""
    sens, keep = containers.fields(spec, anon)
    keep_runs = set()
    for role, text, key in keep:
        keep_runs |= set(re.findall(r'\d+', text))
        keep_runs.add(text.strip())
    issued_list = list(issued)
    units = []
    if spec['container'] in DELIMITED:
        units = [anon.decode('cp1251', errors='replace')]
    else:
        units = [t for _, t, _ in sens] + [t for _, t, _ in keep]
    total = explained_issued = explained_keep = 0
    unexplained = 0
    for u in units:
        for rx in (IBAN_LIKE, NUM_8_10):
            for m in rx.finditer(u):
                t = m.group(0)
                total += 1
                if any(t in v for v in issued_list):
                    explained_issued += 1
                elif t in keep_runs:
                    explained_keep += 1
                else:
                    unexplained += 1
    return dict(total=total, issued=explained_issued, keep=explained_keep, unexplained=unexplained)


LETTERS4 = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґ]{4,}")
BLANK_BYTES = (0x00, 0x20, 0x1A)


def residual_violations(spec, data, cfg):
    """Байти поза полями (скелет, `walk(..., blank=True)`) мають складатися лише зі слів структури й порожніх
    байтів. -> кількість порушень (0 = чисто).

    * csv / xml / lines: лексеми скелета (числа від 5 цифр, слова з великої літери) поза словами структури;
    * dbf: байти прапорців записів, проміжки між полями та хвіст після записів — лише 0x00 / 0x20 / 0x1A (прапорець
      запису ще й 0x2A), заголовок — лише слова структури (імена полів);
    * xls: усе, що не рядок SST і не числова комірка (WRITEACCESS, властивості, імена аркушів і шрифтів), у трьох
      поданнях байтів — слова від 4 літер і числа від 5 цифр поза словами структури, `allowed_words` і
      `binary_structure_words` (технічні слова BIFF / OLE)."""
    kind = spec['container']
    allowed = set(cfg.get('allowed_words', [])) | set(cfg.get('binary_structure_words', []))
    st = set()
    for w in containers.structure_words(spec, data):
        st |= lexemes(str(w)) | set(WORD.findall(str(w)))
    skel = containers.walk(dict(spec, no_scrub=True), data, None, blank=True)   # без зачистки: бачимо, що лишилось
    bad = 0
    if kind in ('csv', 'xml', 'lines'):
        bad += len(lexemes(skel.decode('cp1251', errors='replace')) - st - allowed)
    elif kind == 'dbf':
        fields, nrec, hlen, rlen = containers._dbf_parse(data)
        flen = 1 + sum(f[3] for f in fields)
        bad += rlen != flen                                     # байти запису поза полями
        for i in range(nrec):
            if data[hlen + i * rlen] not in (0x20, 0x2A):
                bad += 1
        bad += sum(1 for b in data[hlen + nrec * rlen:] if b not in BLANK_BYTES)
        head = data[:hlen]
        pos = 32 + 32 * len(fields)
        bad += sum(1 for b in head[pos + 1:] if b not in BLANK_BYTES)
        words = {w for w in LETTERS4.findall(head.decode('cp1251', errors='replace'))} - st - allowed
        bad += len(words)
    elif kind == 'xls':
        found = set()
        v8, v16a, v16b = views(skel)
        # 8-бітне подання бінарного файлу дає шум кирилиці з довільних байтів: там лише латиниця й числа
        found |= set(re.findall(r'[A-Za-z]{4,}', v8)) | {t for t in DIG.findall(v8) if len(set(t)) > 1}
        for v in (v16a, v16b):
            found |= set(LETTERS4.findall(v)) | {t for t in DIG.findall(v) if len(set(t)) > 1}
        bad += len(found - st - allowed)
    return bad


def check_a(spec, raw, anon, cfg, issued, control=False):
    """(а): чутливі значення сирого файлу не трапляються в знеособленому. control=True: anon — сирий
    файл; перевірка мусить дати збіги, інакше вона не вміє падати."""
    lex, stats, values = build_lexicon(spec, raw, cfg.get('allowed_words', []), cfg.get('verbatim_texts', []))
    sens_a, keep_a = containers.fields(spec, anon)
    units = [t for _, t, _ in sens_a] + [t for _, t, _ in keep_a]
    hl, hv = find_hits(lex, values, anon, spec['container'], units)
    res = dict(stats)
    res.update(hits_lexemes=len(hl), hits_values=len(hv))
    # залишок поза полями (скелет файлу) у знеособленому: лише слова структури, порожні байти
    resid = residual_violations(spec, anon, cfg)
    res['residual_unclassified'] = resid
    if control:
        res['ok'] = (len(hl) + len(hv)) > 0
        return res
    pat = pattern_scan(spec, anon, issued)
    res['pattern'] = pat
    res['ok'] = not hl and not hv and pat['unexplained'] == 0 and not resid
    return res


# ----------------------------------------------------------------- (б) структура
def _eol_stats(b):
    return dict(crlf=b.count(b'\r\n'), lf=b.count(b'\n') - b.count(b'\r\n'), cr=b.count(b'\r') - b.count(b'\r\n'),
                nul=b.count(b'\x00'), bom=b[:3] == b'\xef\xbb\xbf', size_class=type(b).__name__)


def _ctl_counts(t):
    return (t.count(';'), t.count('"'), t.count('\x00'), t.count('\n'), t.count('\r'), t.count('«'), t.count('»'))


def check_b(spec, raw_cmp, anon, fakes_issued=None):
    """(б): структура та сама. raw_cmp — сирий файл після однакового скорочення (take_rows)."""
    from stdnum import iban as sn_iban
    from stdnum.ua import edrpou as sn_edrpou, rntrc as sn_rntrc
    res = {}
    kind = spec['container']
    skel_raw = containers.walk(spec, raw_cmp, None, blank=True)
    skel_anon = containers.walk(spec, anon, None, blank=True)
    res['skeleton_equal'] = skel_raw == skel_anon
    res['size_equal'] = len(raw_cmp) == len(anon) if kind in ('lines', 'dbf', 'xls') else None
    e1, e2 = _eol_stats(raw_cmp), _eol_stats(anon)
    res['eol_nul_bom_equal'] = True if kind == 'xls' else e1 == e2
    # кодування: кількість незакодованих байтів не росте
    def bad(b):
        try:
            b.decode('cp1251')
            return 0
        except UnicodeDecodeError:
            return sum(1 for x in b if x == 0x98)
    res['encoding_ok'] = bad(anon) <= bad(raw_cmp)
    # рядки й колонки CSV
    if kind == 'csv':
        def shape(b):
            out = []
            for l in re.split(r'\r\n|\n|\r', b.decode('cp1251', errors='replace')):
                if l.strip():
                    f = split_csv_quoted(l)
                    out.append((len(f), tuple(q for _, _, q in f)))
            return out
        res['rows_cols_quotes_equal'] = shape(raw_cmp) == shape(anon)
        res['rows'] = len(shape(raw_cmp)) - 1
    # поля: ролі, довжини, службові символи, контрольні суми
    rs, rk = containers.fields(spec, raw_cmp)
    as_, ak = containers.fields(spec, anon)
    res['fields'] = len(rs)
    pairs_ok = len(rs) == len(as_)
    len_bad = ctl_bad = chk_bad = 0
    n_code = n_acc = n_code_valid = n_acc_valid = 0
    bankcode_bad = 0
    if pairs_ok:
        for (r1, t1, k1), (r2, t2, k2) in zip(rs, as_):
            if (r1, k1) != (r2, k2) or (t1.strip() == '') != (t2.strip() == ''):
                pairs_ok = False
                break
            if t1.strip() == '':
                continue
            a, b_ = t1.strip(), t2.strip()
            if r1 in (CODE, ACC, SCRAMBLE, 'GAP') and len(a) != len(b_):
                len_bad += 1
            if r1 in (NAME, BANKNAME, PURPOSE) and _ctl_counts(a) != _ctl_counts(b_):
                ctl_bad += 1
            if r1 == CODE and re.fullmatch(r'\d{8}|\d{10}', a):
                n_code += 1
                ok = sn_edrpou.is_valid(b_) if len(a) == 8 else sn_rntrc.is_valid(b_)
                n_code_valid += ok
                chk_bad += not ok
            if r1 == ACC and re.fullmatch(r'UA\d{27}', a):
                n_acc += 1
                ok = sn_iban.is_valid(b_)
                n_acc_valid += ok
                chk_bad += not ok
                bankcode_bad += a[4:10] != b_[4:10]
    res.update(fields_aligned=pairs_ok, length_mismatch=len_bad, control_chars_mismatch=ctl_bad,
               codes=n_code, codes_valid=n_code_valid, ibans=n_acc, ibans_valid=n_acc_valid,
               checksum_bad=chk_bad, bankcode_mismatch=bankcode_bad)
    res['ok'] = bool(res['skeleton_equal'] and res['eol_nul_bom_equal'] and res['encoding_ok'] and pairs_ok
                     and not len_bad and not ctl_bad and not chk_bad and not bankcode_bad
                     and res.get('rows_cols_quotes_equal', True) and res['size_equal'] in (None, True))
    return res


# ----------------------------------------------------------------- (в) розбір оракулом
OP_KEEP = ('date', 'time', 'doc_no', 'doc_date', 'amount', 'direction', 'own_mfo', 'cp_mfo', 'currency', 'op_code',
           'fee_by_code')
OP_ROLE = dict(own_edrpou=CODE, cp_edrpou=CODE, own_acc=ACC, cp_acc=ACC, cp_name=NAME, cp_bank=BANKNAME,
               purpose=PURPOSE, bank_id=SCRAMBLE)


def _named_ops(sample, data):
    key = sample['named']
    if key == 'ukrgaz':
        ops, meta = named.read_ukrgaz(data)
        d = dict(ops=ops, meta=meta)
        corpus.fix_ukrgaz(d)
        return ops
    return corpus.read_any_bytes(data, key)[0]


def _purpose_conform(a, b):
    return (a.strip() == '') == (b.strip() == '') and a.count(';') == b.count(';') and \
        gen.category(a) == gen.category(b) and a.count('"') == b.count('"')


def _cmp_named(sample, raw_ops, anon_ops, fakes):
    fields = Counter()
    bad = Counter()
    if len(raw_ops) != len(anon_ops):
        return dict(rows=(len(raw_ops), len(anon_ops))), False
    for o1, o2 in zip(raw_ops, anon_ops):
        for f in OP_KEEP:
            fields['keep'] += 1
            if getattr(o1, f) != getattr(o2, f):
                bad['keep:' + f] += 1
        for f, role in OP_ROLE.items():
            v1, v2 = getattr(o1, f), getattr(o2, f)
            fields['replaced'] += 1
            if v1 == '' and v2 == '':
                continue
            if role == PURPOSE:
                if not _purpose_conform(v1, v2) or v1.strip() == v2.strip():
                    bad['purpose'] += 1
            elif role == SCRAMBLE:
                if v1 and len(v1) != len(v2):
                    bad[f] += 1
            elif v2 != fakes.lookup(role, v1):
                bad[f] += 1
            elif v1 == v2 and v1.strip():
                bad[f + ':unchanged'] += 1
    return dict(rows=len(raw_ops), compared=dict(fields), mismatches=dict(bad)), not bad


def _cmp_legacy(sample, raw_rows, anon_rows, fakes):
    bad = Counter()
    cnt = Counter()
    if len(raw_rows) != len(anon_rows):
        return dict(rows=(len(raw_rows), len(anon_rows))), False
    for a, b in zip(raw_rows, anon_rows):
        if a.status != b.status or a.n != b.n:
            bad['status'] += 1
            continue
        if a.status != 'ok':
            continue
        r1, r2 = a.r, b.r
        for f in ('num', 'date', 'amount', 'dir', 'cur', 'branch'):
            cnt['keep'] += 1
            if r1.get(f) != r2.get(f):
                bad['keep:' + f] += 1
        for side in ('payer', 'recv'):
            for i, role in enumerate((ACC, CODE, 'MFO', NAME)):
                if i >= len(r1[side]):
                    continue
                v1, v2 = r1[side][i], r2[side][i]
                cnt['replaced' if role != 'MFO' else 'keep'] += 1
                if role == 'MFO':
                    if v1 != v2:
                        bad['keep:mfo'] += 1
                elif v1 == '' and v2 == '':
                    continue
                elif role == NAME and sample.get('layout') == 'otp':
                    # відома особливість: стара обробка читає ім'я зі зсувом від межі поля -> порівнюється довжина
                    cnt['weak'] += 1
                    if len(v1) != len(v2) or v1 == v2:
                        bad[side + ':' + role + ':weak'] += 1
                elif v2 != fakes.lookup(role, v1):
                    bad[side + ':' + role] += 1
        cnt['replaced'] += 1
        if r1['purpose'] or r2['purpose']:
            if not _purpose_conform(r1['purpose'], r2['purpose']) or r1['purpose'] == r2['purpose']:
                bad['purpose'] += 1
        elif r1['purpose'] != r2['purpose']:
            bad['purpose'] += 1
    return dict(rows=len(raw_rows), compared=dict(cnt), mismatches=dict(bad)), not bad


def check_c(sample, spec, raw_cmp, anon, fakes):
    res = {}
    ok = True
    d, k = _cmp_named(sample, _named_ops(sample, raw_cmp), _named_ops(sample, anon), fakes)
    res['named'] = d
    ok &= k
    if sample.get('layout'):
        for mode in ('expected',):
            d, k = _cmp_legacy(sample, legacy.emulate(raw_cmp, sample['layout'], mode),
                               legacy.emulate(anon, sample['layout'], mode), fakes)
            res['legacy_' + mode] = d
            ok &= k
    res['ok'] = bool(ok)
    return res


PAIR_FIELDS = [
    ('напрям', lambda o: o.direction), ('дата', lambda o: o.date), ('дата док.', lambda o: o.doc_date),
    ('сума', lambda o: q2(o.amount)), ('валюта', lambda o: o.currency), ('власний рах.', lambda o: o.own_acc),
    ('рах.контрагента', lambda o: o.cp_acc), ('ЄДРПОУ власн.', lambda o: o.own_edrpou),
    ('ЄДРПОУ контр.', lambda o: o.cp_edrpou), ('МФО контр.', lambda o: o.cp_mfo),
    ('назва контр.', lambda o: ws(o.cp_name)), ('призначення', lambda o: ws(o.purpose))]


def pair_matches(ops_a, ops_b):
    """Збіги полів між двома форматами однієї виписки: за ключем (номер, сума, валюта); -> (пар, {поле: збігів})."""
    from collections import defaultdict
    idx = defaultdict(list)
    for b in ops_b:
        idx[(ws(b.doc_no), q2(b.amount), b.currency)].append(b)
    pairs = []
    for a in ops_a:
        lst = idx.get((ws(a.doc_no), q2(a.amount), a.currency))
        if lst:
            pairs.append((a, lst.pop(0)))
    return len(pairs), {n: sum(1 for a, b in pairs if f(a) == f(b)) for n, f in PAIR_FIELDS}


def check_pair(sample_a, sample_b, raw_a, raw_b, anon_a, anon_b):
    """Знеособлені версії однієї виписки звіряються між собою так само, як сирі."""
    ra, rb = _named_ops(sample_a, raw_a), _named_ops(sample_b, raw_b)
    aa, ab = _named_ops(sample_a, anon_a), _named_ops(sample_b, anon_b)
    if sample_a['named'] == 'otp_dat' and sample_b['named'] == 'dbf_otp':
        # .dat і .dbf однієї виписки зіставляються рядок до рядка (як у дослідженні)
        n1 = len(ra)
        raw_res = (n1, {n: sum(1 for a, b in zip(ra, rb) if f(a) == f(b)) for n, f in PAIR_FIELDS})
        an_res = (len(aa), {n: sum(1 for a, b in zip(aa, ab) if f(a) == f(b)) for n, f in PAIR_FIELDS})
    else:
        raw_res, an_res = pair_matches(ra, rb), pair_matches(aa, ab)
    return dict(raw_pairs=raw_res[0], anon_pairs=an_res[0], raw_full=sum(1 for v in raw_res[1].values() if v == raw_res[0]),
                anon_full=sum(1 for v in an_res[1].values() if v == an_res[0]), fields=len(PAIR_FIELDS),
                ok=raw_res == an_res and raw_res[0] > 0)
