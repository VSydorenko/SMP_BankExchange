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
from sslib.gen import WORD_RX

from . import jsonspan, recording as R, schema

IBAN_RX = re.compile(r'UA\d{27}')
FREE_TEXT_KEEP = ('message', 'errorDescription')       # KEEP-поля з вільним текстом (зачищалися від IBAN); тепер зачищається КОЖНЕ рядкове поле KEEP (`Bank.clean_text`)
# Слова, які генератор сам видає у вигаданих призначеннях (словники `gen.PHRASES` / `gen.SHORT`): за побудовою не ідентифікують, тож не чистяться з полів KEEP і не рахуються витоком у (а). ЄДИНИЙ такий
# словник; явні слова публічного словника -- `allowed_words`, `guard_allowed_words`, `api_guard_allowed_words` із `config.json` (юридичні форми, назви банків, міста).
GEN_WORDS = frozenset(w.casefold() for lst in list(gen.PHRASES.values()) + list(gen.SHORT.values()) for p in lst for w in WORD.findall(p))
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


def request_body(bank, ex):
    """Тіло запиту обміну (формат v2) для обходу: (текст, [(роль, вузол, шлях)]). Тіла немає або `bodyOmitted` -> (None, []).
    Маркер `<masked>` форми `bodyMasked` значенням не є і в перелік не йде. Тіло не UTF-8 / не JSON -> `UnknownField`
    (позиція й код, НЕ фрагмент вхідного тексту): мовчазного копіювання тіла немає."""
    rq = ex['request']
    if 'bodyBase64' not in rq and 'bodyMasked' not in rq:
        return None, []
    try:
        text = R.request_body_text(ex)
    except UnicodeDecodeError as e:
        raise schema.UnknownField('%s: тіло запиту не UTF-8 (позиція %d)' % (bank, e.start))
    try:
        root = jsonspan.parse(text)
    except jsonspan.JsonSpanError as e:
        raise schema.UnknownField('%s: тіло запиту не є JSON (%s)' % (bank, e))
    masked = 'bodyMasked' in rq
    return text, [(role, nd, where) for role, nd, where in schema.request_leaves(bank, rq['path'], root)
                  if not (masked and nd.kind == 'str' and nd.value == R.MASK_MARKER)]


class Bank:
    """Знеособлення одного банку: одна мапа на всі його записи."""

    def __init__(self, bank, fakes, refs=(), ibans=(), ids=(), accs=(), codes=(), words=()):
        self.bank, self.fakes, self.refs, self.ibans = bank, fakes, tuple(sorted(refs, key=len, reverse=True)), tuple(ibans)
        self.ids, self.accs, self.codes = tuple(ids), tuple(accs), tuple(codes)    # сирі значення ролей ID, ACC і CODE запису (для зачистки полів KEEP)
        self.words = frozenset(words)                    # слова (casefold) із значень ролей NAME / BANKNAME запису: прізвища й назви, що не мусять лишитись у рядках KEEP
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
        if self.words:
            s = WORD_RX.sub(lambda m: self.fakes.word(m.group(0)) if m.group(0).casefold() in self.words else m.group(0), s)
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
        for v in self.codes:
            if len(v) >= SWEEP_MIN and len(set(v)) > 2:
                pairs.append((v, self.value('CODE', v)))
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
        self._request_body(req, out)
        return out

    def _request_body(self, req, out):
        """Тіло запиту v2: `port` і `bodyOmitted` лишаються як є; `bodyBase64` -- розкодувати, знеособити ТІЄЮ САМОЮ мапою й ролями, що й
        відповідь, закодувати, перерахувати `bodyLength`; `bodyMasked` -- знеособити `text`, маркери лишити."""
        text, leaves = request_body(self.bank, {'request': req})
        if text is None:
            return
        edits = []
        for role, nd, where in leaves:
            new = self.replace_node(role, nd, next((w for w in reversed(where) if isinstance(w, str)), ''), '\\u' in text)
            if new is not None:
                edits.append((nd.start, nd.end, new))
        new_text = jsonspan.replace_spans(text, edits)
        if 'bodyBase64' in req:
            body = new_text.encode('utf-8')
            out['bodyBase64'] = base64.b64encode(body).decode('ascii')
            out['bodyLength'] = len(body)
        else:
            out['bodyMasked'] = {'text': new_text, 'fields': list(req['bodyMasked']['fields'])}

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
            if role == 'ID':
                # числовий ідентифікатор (ПУМБ: id, docId, accountId, orderedLastId): та сама заміна за ТЕКСТОМ числа, що й для рядкового
                # значення (documentAccounts рекордера -- рядки), тож зв'язок запит <-> відповідь зберігається
                if not re.fullmatch(r'[1-9]\d*', nd.value):
                    raise schema.UnknownField('%s: числовий ідентифікатор не є натуральним цілим' % self.bank)
                new = self.ident(nd.value)
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
        leaves = list(request_body(bank, ex)[1])             # тіло запиту (v2): ті самі ролі, ті самі заборонені значення
        if ex['response']:
            try:
                root = jsonspan.parse(R.body_text(ex))
            except jsonspan.JsonSpanError:
                raise schema.UnknownField('%s: тіло не є JSON' % bank)
            leaves += schema.leaves(bank, req['path'], ex['response']['status'], root)
        for role, nd, where in leaves:
            if (nd.kind != 'str' and not (nd.kind == 'num' and role == 'ID')) or role == 'KEEP' or nd.value == '':
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


def prescan_values(bank, rec, cfg=None):
    """Сирі значення ролей ID, ACC, CODE й слова ролей NAME / BANKNAME (у тілах, шляхах, запитах) для зачистки полів KEEP. Слова з явного словника (`allowed_words`, `guard_allowed_words`,
    `api_guard_allowed_words`) і зі словника генератора (`GEN_WORDS`) і слова коротші за 4 літери не беруться. -> (ids, accs, codes, words)."""
    cfg = cfg or cfgmod.load()
    allowed = {w.casefold() for w in list(cfg.get('allowed_words', [])) + list(cfg.get('guard_allowed_words', [])) + list(cfg.get('api_guard_allowed_words', []))}
    ids, accs, codes, words = set(), set(), set(), set()
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
        leaves = list(request_body(bank, ex)[1])
        if ex['response']:
            try:
                root = jsonspan.parse(R.body_text(ex))
                leaves += schema.leaves(bank, req['path'], ex['response']['status'], root)
            except jsonspan.JsonSpanError:
                pass
        for role, nd, where in leaves:
            if (nd.kind != 'str' and not (nd.kind == 'num' and role == 'ID')) or nd.value.strip() == '':
                continue
            v = nd.value.strip()
            if role == 'ID':
                ids.add(v)
            elif role == 'ACC':
                accs.add(v)
                if IBAN_RX.fullmatch(v):
                    accs.add(v[-14:])
            elif role == 'CODE':
                codes.add(v)
            elif role in ('NAME', 'BANKNAME'):
                words |= {w.casefold() for w in WORD.findall(v) if len(w) >= 4 and w.casefold() not in allowed and w.casefold() not in GEN_WORDS}
    return ids, accs, codes, words


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
    ids, accs, codes, name_words = prescan_values(bank, rec, cfg)
    fk = make_fakes(cfg, words, nums, map_path)
    b = Bank(bank, fk, refs, ibans, ids, accs, codes, name_words)
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
    ids, accs, codes, name_words = prescan_values(bank, rec, cfg)
    fk = make_fakes(cfg, words, nums, map_path)
    b = Bank(bank, fk, refs, ibans, ids, accs, codes, name_words)
    return rec, b
