# -*- coding: utf-8 -*-
"""Знеособлювач записів відповідей API (Step 2 задачі 2 плану 05а). Сирий запис -> знеособлений у ТОМУ САМОМУ форматі
(`tools/api-recorder/FORMAT.md`, версія 1): тіла, `request.path`, `request.query`.

Ґенератори, мапа «реальне -> вигадане» і сторож -- `sslib` (`gen.Fakes`, `guard`); тут лише обхід запису. Мапа одна на
прогін і на банк, спільна для всіх обмінів банку: той самий контрагент, ідентифікатор, рахунок отримує ту саму заміну на
всіх сторінках, у тілах і в шляхах запитів. Мапа лежить ПОЗА робочим деревом (`<корінь записів>/_anon-map/<банк>.json`) і ніколи
не потрапляє в git.

Заміна точкова: змінюються лише значення полів з роллю не KEEP (`schema.py`), решта тіла лишається побайтово тією самою
(пробіли, порядок ключів, форма чисел). Невідоме поле або неочікуваний вигляд тіла -- `schema.UnknownField`, зупинка.
Жодна функція не друкує значення."""
import base64
import copy
import json
import os
import re

from sslib import cfg as cfgmod, gen
from sslib.checks import DIG, WORD

from . import jsonspan, recording as R, schema

IBAN_RX = re.compile(r'UA\d{27}')
FREE_TEXT_KEEP = ('message', 'errorDescription')       # KEEP-поля з вільним текстом (зачищалися від IBAN); тепер зачищається КОЖНЕ рядкове поле KEEP (`Bank.clean_text`)
SWEEP_MIN = 6                                          # найкоротше значення ролі ID / ACC, яке підмінюється всередині рядків KEEP (коротші лише ловить перевірка (а))
REPLACED = ('CODE', 'ACC', 'NAME', 'BANKNAME', 'PURPOSE', 'SCRAMBLE', 'ID')
PRIVAT_KEEP_QUERY = ('startDate', 'endDate', 'limit')
CORP_KEEP_QUERY = ('limit', 'direction', 'dateFrom', 'dateTo')


def body_style(ex):
    """(кодування, JSON-екранування `\\uXXXX`) тіла обміну."""
    cs = R.charset_of(ex)
    cs = {'utf8': 'utf-8', 'windows-1251': 'cp1251'}.get(cs, cs)
    return cs


def path_segments(bank, path):
    """Позиції сегментів шляху, які є рахунком (ACC) чи ідентифікатором рахунку (ID): {індекс: роль}."""
    seg = path.split('/')
    out = {}
    if bank == 'mono-corp':
        for i, s in enumerate(seg):
            if s == 'accounts' and i + 2 < len(seg) and seg[i + 2] == 'balances':
                out[i + 1] = 'ACC'
            if s == 'statement' and i + 1 < len(seg):
                out[i + 1] = 'ACC'
    elif bank == 'mono-fop':
        for i, s in enumerate(seg):
            if s == 'statement' and i + 1 < len(seg):
                out[i + 1] = 'ID'
    return out


def query_pairs_raw(query):
    return [(p.partition('=')[0], p.partition('=')[1], p.partition('=')[2]) for p in query.split('&')] if query else []


class Bank:
    """Знеособлення одного банку: одна мапа на всі його записи."""

    def __init__(self, bank, fakes, refs=(), ibans=(), ids=(), accs=()):
        self.bank, self.fakes, self.refs, self.ibans = bank, fakes, tuple(sorted(refs, key=len, reverse=True)), tuple(ibans)
        self.ids, self.accs = tuple(ids), tuple(accs)    # сирі значення ролей ID і ACC запису (для зачистки полів KEEP)
        self.sweep = []                      # [(сирий токен, вигаданий)] для рядкових полів KEEP

    # ----------------------------------------------------------- значення
    def acc(self, s):
        """Рахунок: IBAN -> IBAN з правильною контрольною сумою; 14 цифр (хвіст власного IBAN) -> хвіст вигаданого IBAN."""
        m = self.fakes.m.setdefault('acc14', {})
        if s in m:
            return m[s]
        if re.fullmatch(r'\d{14}', s):
            for iban in self.ibans:
                if iban.endswith(s):
                    m[s] = self.fakes.account(iban)[-14:]
                    return m[s]
        return self.fakes.account(s)

    def ident(self, s):
        return self.fakes.ident(s, self.refs)

    def scramble(self, s):
        out = self.fakes.apply('SCRAMBLE', s)
        for _ in range(50):
            if out != s or not any(c.isalnum() for c in s):
                break
            self.fakes.m['scramble'].pop(s, None)
            out = self.fakes.apply('SCRAMBLE', s)
        return out

    def value(self, role, s):
        """Заміна рядкового значення за роллю."""
        if s == '' or role == 'KEEP':
            return s
        if role == 'ID':
            return self.ident(s)
        if role == 'ACC':
            return self.acc(s)
        if role == 'SCRAMBLE':
            return self.scramble(s)
        return self.fakes.apply(role, s)

    def clean_text(self, s):
        for raw, fake in self.sweep:
            s = s.replace(raw, fake)
        return s

    def build_sweep(self):
        """Зачистка полів KEEP: сире значення ролі ID чи ACC, що стоїть підрядком у БУДЬ-ЯКОМУ рядковому полі KEEP (приклад -- `NUM_DOC` ПриватБанку містить `DLR` чи `REF`), замінюється
        ТІЄЮ САМОЮ заміною з мапи, що й у своєму полі: ключ D17 і зв'язок ID <-> REF лишаються узгодженими. Значення з <= 2 різних символів і коротші за `SWEEP_MIN` не чіпаються
        (тривіальні рядки не ідентифікують; решту коротких ловить перевірка (а))."""
        pairs = []
        for iban in self.ibans:
            pairs.append((iban, self.acc(iban)))
            pairs.append((iban[-14:], self.acc(iban[-14:])))
        for v in self.accs:
            if len(v) >= SWEEP_MIN and len(set(v)) > 2:
                pairs.append((v, self.acc(v)))
        for v in self.ids:
            if len(v) >= SWEEP_MIN and len(set(v)) > 2:
                pairs.append((v, self.ident(v)))
        seen, out = set(), []
        for raw, fake in sorted(pairs, key=lambda p: -len(p[0])):
            if raw not in seen:
                seen.add(raw)
                out.append((raw, fake))
        self.sweep = out

    # ----------------------------------------------------------- запит
    def request(self, req):
        bank = self.bank
        path = req['path']
        seg = path.split('/')
        for i, role in path_segments(bank, path).items():
            seg[i] = self.acc(seg[i]) if role == 'ACC' else self.ident(seg[i])
        pairs = []
        for k, eq, v in query_pairs_raw(req['query']):
            if bank == 'privat' and k == 'acc':
                v = self._query_value('ACC', v)
            elif bank == 'privat' and k == 'followId':
                v = self._query_value('ID', v)
            elif (bank == 'privat' and k in PRIVAT_KEEP_QUERY) or (bank == 'mono-corp' and k in CORP_KEEP_QUERY):
                pass
            else:
                raise schema.UnknownField('%s: невідомий параметр запиту %s' % (bank, k))
            pairs.append(k + eq + v)
        out = dict(req)
        out['path'] = '/'.join(seg)
        out['query'] = '&'.join(pairs)
        return out

    def _query_value(self, role, v):
        if '%' in v or '+' in v:
            raise schema.UnknownField('%s: у значенні параметра запиту є кодування' % self.bank)
        return self.acc(v) if role == 'ACC' else self.ident(v)

    # ----------------------------------------------------------- тіло
    def body(self, ex):
        """-> нові байти тіла відповіді."""
        r = ex['response']
        raw = R.body_bytes(ex)
        cs = body_style(ex)
        text = raw.decode(cs)
        if text.encode(cs) != raw:
            raise schema.UnknownField('%s: тіло не перекодовується без втрат (%s)' % (self.bank, cs))
        try:
            root = jsonspan.parse(text)
        except jsonspan.JsonSpanError:
            raise schema.UnknownField('%s: тіло не є JSON' % self.bank)
        escaped = '\\u' in text
        edits = []
        for role, nd, where in schema.leaves(self.bank, ex['request']['path'], r['status'], root):
            key = next((w for w in reversed(where) if isinstance(w, str)), '')
            new = self.replace_node(role, nd, key, escaped)
            if new is not None:
                edits.append((nd.start, nd.end, new))
        out = jsonspan.replace_spans(text, edits)
        try:
            return out.encode(cs)
        except UnicodeEncodeError:
            raise schema.UnknownField('%s: вигадане значення не кодується в %s' % (self.bank, cs))

    def replace_node(self, role, nd, key, escaped):
        if nd.kind == 'lit':
            return None
        if nd.kind == 'str':
            if role == 'KEEP':
                clean = self.clean_text(nd.value)
                if clean != nd.value:
                    return json.dumps(clean, ensure_ascii=escaped)
                return None
            new = self.value(role, nd.value)
            return None if new == nd.value else json.dumps(new, ensure_ascii=escaped)
        if nd.kind == 'num':
            if role == 'KEEP':
                return None
            if role == 'SCRAMBLE':
                new = self.fakes.number(nd.value)
                return None if new == nd.value else new
            raise schema.UnknownField('%s: число в полі з роллю %s' % (self.bank, role))
        raise schema.UnknownField('%s: контейнер там, де очікується скаляр' % self.bank)

    def exchange(self, ex):
        out = copy.deepcopy(ex)
        out['request'] = self.request(ex['request'])
        r = out['response']
        if r is not None:
            body = self.body(ex)
            r['bodyBase64'] = base64.b64encode(body).decode('ascii')
            r['bodyLength'] = len(body)
        else:
            out['failure']['text'] = self.clean_text(out['failure']['text'])
        return out


# ---------------------------------------------------------------------- прескан і запуск
def prescan(bank, rec):
    """Сирі REF, IBAN-и (у тілах, шляхах, запитах) і заборонені для вигаданих значень слова й числа. -> (refs, ibans, words, nums)."""
    refs, ibans, words, nums = set(), set(), set(), set()
    for ex in rec.exchanges:
        req = ex['request']
        for part in req['path'].split('/') + [v for _, _, v in query_pairs_raw(req['query'])]:
            if IBAN_RX.fullmatch(part):
                ibans.add(part)
        if not ex['response']:
            continue
        try:
            root = jsonspan.parse(R.body_text(ex))
        except jsonspan.JsonSpanError:
            raise schema.UnknownField('%s: тіло не є JSON' % bank)
        for role, nd, where in schema.leaves(bank, req['path'], ex['response']['status'], root):
            if nd.kind != 'str' or role == 'KEEP' or nd.value == '':
                continue
            v = nd.value.strip()
            if role == 'ID' and where and where[-1] == 'REF':
                refs.add(v)
            if role == 'ACC':
                if IBAN_RX.fullmatch(v):
                    ibans.add(v)
                nums |= {v, v.lstrip('0')}
                if IBAN_RX.fullmatch(v):
                    nums.add(v[10:].lstrip('0'))
            if role in ('NAME', 'BANKNAME', 'PURPOSE'):
                words |= {w.casefold() for w in WORD.findall(v)}
            if role == 'CODE':
                nums.add(v)
            nums |= set(DIG.findall(v))
    return refs, ibans, words, nums


def prescan_values(bank, rec):
    """Сирі значення ролей ID і ACC (у тілах, шляхах, запитах) для зачистки полів KEEP. -> (ids, accs)."""
    ids, accs = set(), set()
    for ex in rec.exchanges:
        req = ex['request']
        segs = req['path'].split('/')
        for i, role in path_segments(bank, req['path']).items():
            (accs if role == 'ACC' else ids).add(segs[i])
        for k, _, v in query_pairs_raw(req['query']):
            if bank == 'privat' and k == 'acc':
                accs.add(v)
            elif bank == 'privat' and k == 'followId':
                ids.add(v)
        if not ex['response']:
            continue
        try:
            root = jsonspan.parse(R.body_text(ex))
        except jsonspan.JsonSpanError:
            continue
        for role, nd, where in schema.leaves(bank, req['path'], ex['response']['status'], root):
            if nd.kind != 'str' or nd.value.strip() == '':
                continue
            v = nd.value.strip()
            if role == 'ID':
                ids.add(v)
            elif role == 'ACC':
                accs.add(v)
                if IBAN_RX.fullmatch(v):
                    accs.add(v[-14:])
    return ids, accs


def make_fakes(cfg, words, nums, map_path):
    fk = gen.Fakes(forbidden_words=words, forbidden_numbers=nums, allowed_words=cfg.get('allowed_words', []))
    if map_path and os.path.exists(map_path):
        with open(map_path, encoding='utf-8') as f:
            fk.load(json.load(f))
    return fk


def anonymize_bank(bank, raw_dir, out_dir, map_path, cfg=None):
    """Сирий запис банку -> знеособлений у `out_dir`. Мапа читається з `map_path` (якщо є) і дописується туди ж.
    -> (кількість обмінів, Bank)."""
    cfg = cfg or cfgmod.load()
    rec = R.Recording.from_dir(raw_dir)
    if rec.bank != bank:
        raise schema.UnknownField('%s: у маніфесті інший банк' % bank)
    refs, ibans, words, nums = prescan(bank, rec)
    ids, accs = prescan_values(bank, rec)
    fk = make_fakes(cfg, words, nums, map_path)
    b = Bank(bank, fk, refs, ibans, ids, accs)
    b.build_sweep()
    new = [b.exchange(ex) for ex in rec.exchanges]
    anon = R.Recording(copy.deepcopy(rec.manifest), new)
    anon.to_dir(out_dir)
    if map_path:
        os.makedirs(os.path.dirname(map_path), exist_ok=True)
        with open(map_path, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(fk.dump(), f, ensure_ascii=False)
    return len(new), b


def load_bank(bank, raw_dir, map_path, cfg=None):
    """Bank з уже записаною мапою (для перевірок): нових замін не створює, але `Bank.acc` і `ident` лише читають кеш."""
    cfg = cfg or cfgmod.load()
    rec = R.Recording.from_dir(raw_dir)
    refs, ibans, words, nums = prescan(bank, rec)
    ids, accs = prescan_values(bank, rec)
    fk = make_fakes(cfg, words, nums, map_path)
    b = Bank(bank, fk, refs, ibans, ids, accs)
    return rec, b
