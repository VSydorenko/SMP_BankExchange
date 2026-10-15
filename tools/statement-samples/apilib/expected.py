# -*- coding: utf-8 -*-
"""Оракул, режим «очікуване»: стара обробка плюс ухвалені відступи плану 05а (Global Constraints, «Відступи від
попередника — лише ці») і контрактні правила D28/D36.

**Відступи** — кожен окрема іменована функція `devN_*` (реєстр `DEVIATIONS`). Кожну можна вимкнути (`disabled={'dev3'}`):
тоді поведінка — попередника. Це і є контроль поломкою: вимкнений відступ мусить дати червоний рівно на записах, де він
спрацьовує (`tests/test_api_expected.py`). Які відступи спрацювали на записі, видно в `Expected.applied`.

| id | Відступ |
|---|---|
| dev1 | чужий рахунок — рядок діагностики через фільтр точки читання (D30), а не мовчки. Валюта ПриватБанку — УМОВНО: |
|      | пункт чекає виміру задачі 1 (чи повертає банк за `acc` рядки кількох валют); тут НЕ реалізовано. |
| dev2 | неостаточні (`hold`, `PENDING`, `PR_PR = p`) і скасовані `DECLINED` — рядок `Предупреждение` замість |
|      | мовчазного пропуску (Привату `p` попередник вантажив), `ГраницаДоверия` не пізніша за першу неостаточну |
| dev3 | забраковані ПриватБанку (`PR_PR = n`) документа не дають (попередник вантажив) |
| dev4 | реверс monobank і сторнована `PR_PR = t` — окрема операція свого напряму; випадок (б) — рядок `Ошибка` |
| dev5 | призначення платежу не обрізається до 255 |
| dev6 | буквений код валюти ПриватБанку перетворює спільний розбір, не довідник валют |
| dev7 | ідентифікатор операції ПриватБанку (вибір D36 п. 6 — параметр `privat_id`) |
| dev8 | усі дати — київський місцевий час з явним поясом, не пояс сеансу |
| dev9 | технічне: `limit` і пауза ПриватБанку; повтор після 429 за заголовком; пауза після client-info; |
|      | кількість і зміст операцій від цього не змінюються |

**Контрактні правила** (не відступи, а розвиток D28/D36 п. 8 для API): `rule_failure_class`, `rule_complete`,
`rule_trust_boundary`, `rule_unknown_state`, `rule_unknown_direction`, `rule_page_without_id`, `rule_dedupe_by_id`.
Їхні рішення — окремий рядок звіту виконавця: планувальник підтверджує або відкидає.
"""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from . import common as C, kyiv, oracle_old, recording as R

DEVIATIONS = {
    'dev1': 'чужий рахунок — діагностика через фільтр точки читання (валюта ПриватБанку — умовно, не реалізовано)',
    'dev2': 'неостаточні й DECLINED — Предупреждение, ГраницаДоверия',
    'dev3': 'PR_PR = n — документа не дає',
    'dev4': 'реверс monobank і PR_PR = t — окрема операція; випадок (б) — Ошибка',
    'dev5': 'призначення не обрізається до 255',
    'dev6': 'буквений код валюти — спільний розбір',
    'dev7': 'ідентифікатор операції ПриватБанку (D36 п. 6)',
    'dev8': 'київський місцевий час з явним поясом',
    'dev9': 'технічне: limit, паузи, повтор після 429',
}

CLS_RETRY = 'Повторить'
CLS_HUMAN = 'ДействиеЧеловека'
PRIVAT_LIMIT = 100                  # dev9: «рекомендовано не більше 100» (privat.txt, параметр limit)
PRIVAT_PAUSE_SECONDS = 1            # dev9: «не частіше 1 запиту в секунду»
MONO_PAUSE_SECONDS = 60             # MF:485-490: ліміт monobank ФОП — 1 запит на 60 с
BANK_NAMES = {'privat': 'ПриватБанк', 'mono-fop': 'monobank ФОП', 'mono-corp': 'monobank юросіб'}
OP_COLUMNS = ['ПорядковыйНомер', 'НомерСчета', 'Валюта', 'ДатаОперации', 'НомерДокумента', 'ДатаДокумента', 'Сумма',
              'Направление', 'ИдентификаторОперации', 'КонтрагентНаименование', 'КонтрагентНомерСчета', 'КонтрагентКод',
              'КонтрагентМФО', 'НазначениеПлатежа']


class RecordingMismatch(Exception):
    """Запис не відповідає тому, що зробив би конектор (кінчається раніше, чужий шлях тощо)."""


@dataclass
class Item:
    n: int
    raw: dict
    seq: int


@dataclass
class Expected:
    bank: str
    ops: list = field(default_factory=list)
    diags: list = field(default_factory=list)
    foreign: dict = field(default_factory=dict)      # НомерСчета -> [номери рядків]
    complete: bool = True
    trust: object = None
    failure_class: str = ''
    requests: list = field(default_factory=list)
    pauses: list = field(default_factory=list)
    applied: set = field(default_factory=set)        # id відступів, що спрацювали (змінили результат проти попередника)
    rules: set = field(default_factory=set)          # id контрактних правил, що спрацювали
    items: int = 0                                   # скільки записів прочитано (для інваріанта «жодна не зникла»)
    duplicates: int = 0
    silent: int = 0                                  # відкинуто без сліду (лише вимкнений відступ чи старий пропуск)
    nonfinal: list = field(default_factory=list)     # моменти неостаточних операцій

    def diag(self, level, n, essence, dev=None, **facts):
        self.diags.append({'Уровень': level, 'ПорядковыйНомер': n, 'Суть': essence, 'Отступ': dev or '', 'Факты': facts})
        if dev:
            self.applied.add(dev)


def run(rec, p, disabled=frozenset()):
    if rec.bank not in C.BANKS:
        raise ValueError('невідомий банк ' + rec.bank)
    out = Expected(rec.bank)
    {'privat': _privat, 'mono-fop': _mono, 'mono-corp': _mono}[rec.bank](rec, p, out, frozenset(disabled))
    out.requests = [{'Метод': e['request']['method'], 'Хост': e['request']['host'], 'Путь': e['request']['path'],
                     'Запрос': [list(kv) for kv in R.query_pairs(e)]} for e in rec.exchanges]
    out.pauses = dev9_pauses(rec, p, 'dev9' not in disabled, out)
    out.trust = rule_trust_boundary(out, p)
    out.complete = rule_complete(out)
    return out


# ====================================================================== відступи
def dev1_foreign_account(out, disabled, n, own_value, acct):
    """Чужий рахунок: операція доходить до точки читання, яка пише діагностику (D30). -> 'emit' | 'silent'."""
    if 'dev1' in disabled:
        out.silent += 1
        return 'silent'
    out.foreign.setdefault(own_value, []).append(n)
    out.applied.add('dev1')
    return 'emit'


def dev2_nonfinal(out, disabled, n, state, moment, ident, old_behavior):
    """Неостаточна (hold / PENDING / p) чи скасована (DECLINED) операція. `old_behavior` — 'silent' (monobank) або
    'emit' (ПриватБанк `p`). -> 'handled' | 'silent' | 'emit'."""
    if 'dev2' in disabled:
        if old_behavior == 'silent':
            out.silent += 1
        return old_behavior
    final_kind = state == 'DECLINED'
    out.diag('Предупреждение', n, 'cancelled' if final_kind else 'nonfinal', 'dev2', Состояние=state, Ид=ident,
             Момент=C.iso(moment))
    if not final_kind:
        out.nonfinal.append(moment)
    return 'handled'


def dev3_privat_rejected(out, disabled, n, ident, moment):
    """PR_PR = n: документа не дає, рядок Предупреждение. -> 'handled' | 'emit'."""
    if 'dev3' in disabled:
        return 'emit'
    out.diag('Предупреждение', n, 'cancelled', 'dev3', Состояние='n', Ид=ident, Момент=C.iso(moment))
    return 'handled'


def dev4_reversal(out, disabled, n, state, ident, collides, old_behavior):
    """Реверс monobank / PR_PR = t. Випадок (а): окремий запис зі своїм ідентифікатором — звичайна операція.
    Випадок (б): запис повернення з ідентифікатором оригіналу в тому самому читанні — рядок Ошибка, не операція.
    `old_behavior`: 'silent' (юросіб) чи 'emit' (Приват). -> 'handled' | 'emit' | 'silent'."""
    if 'dev4' in disabled:
        if old_behavior == 'silent':
            out.silent += 1
        return old_behavior
    if collides:
        out.diag('Ошибка', n, 'reversal-state-change', 'dev4', Состояние=state, Ид=ident)
        return 'handled'
    out.applied.add('dev4') if old_behavior == 'silent' else None
    return 'emit'


def dev5_purpose(text, disabled, mono=True):
    """Призначення платежу не обрізається до 255 (довжину перевіряє платформа). Обрізання мав лише monobank
    (MF:586, MU:558); `OSND` ПриватБанку попередник не обрізав."""
    return text if (not mono or 'dev5' not in disabled) else text[:255]


def dev6_currency(ccy, disabled, p):
    """Буквений код ПриватБанку -> числовий ISO 4217 спільним розбором (не довідник Валюты)."""
    if 'dev6' in disabled:
        return '980' if ccy == 'UAH' else p.old_currency_catalog.get(ccy, '')
    return C.numeric_currency(ccy)


def dev7_privat_identifier(raw, p, disabled):
    """Ідентифікатор операції ПриватБанку за вибором D36 п. 6 (`p.privat_id`). Попередник його в документ не писав."""
    if 'dev7' in disabled or p.privat_id is None:
        return ''
    if p.privat_id == 'REF+REFN':
        v = C.to_str(raw.get('REF')) + C.to_str(raw.get('REFN'))
    else:
        v = C.to_str(raw.get(p.privat_id))
    return v


def dev8_local_time(sec, p, disabled):
    """Київський місцевий час явним поясом (а не поясом сеансу)."""
    if 'dev8' in disabled:
        return C.session_local(sec, p.old_session_tz)
    return kyiv.unix_to_local(sec)


def dev9_pauses(rec, p, enabled, out):
    """Паузи між запитами. Старі (monobank ФОП: 60 с між запитами виписки, MF:282-285; юросіб: після 429 і при
    x-rate-limit-remaining = 0, MU:370-397) завжди; нові відступу dev9 — лише коли він увімкнений: ПриватБанк 1 с між
    сторінками, пауза після client-info ФОП, повтор після 429 за заголовком (ФОП: старий модуль повтору не мав)."""
    ex = rec.exchanges
    res = []
    last = len(ex)

    def add(after, sec, why, new):
        if after >= last or sec <= 0:
            return
        if new and not enabled:
            return
        res.append({'ПослеЗапроса': after, 'Секунд': sec, 'Причина': why})
        if new:
            out.applied.add('dev9')

    if rec.bank == 'privat':
        for k in range(1, last):
            add(k, PRIVAT_PAUSE_SECONDS, 'privat-1-per-second', True)
    elif rec.bank == 'mono-fop':
        seen_stmt = False
        for k, e in enumerate(ex, 1):
            path = e['request']['path']
            nxt = ex[k] if k < last else None
            if path == C.FOP_CLIENT_INFO:
                add(k, p.fop_pause_after_client_info, 'after-client-info', True)
            elif R.statement_window(e):
                if nxt is not None and R.statement_window(nxt):
                    if e['response'] and e['response']['status'] == 429:
                        add(k, _retry_seconds(e), 'after-429', True)
                    else:
                        add(k, MONO_PAUSE_SECONDS, 'between-statements', False)
                seen_stmt = True
    else:
        for k, e in enumerate(ex, 1):
            r = e['response']
            if not r:
                continue
            if r['status'] == 429:
                add(k, _retry_seconds(e), 'after-429', False)
            elif r['status'] == 200 and R.header(e, 'x-rate-limit-remaining') == '0':
                add(k, _retry_seconds(e), 'limit-exhausted', False)
    return res


def _retry_seconds(ex):
    """Пауза за заголовками відповіді: x-rate-limit-retry-after-seconds, далі retry-after, інакше 60 (MU:388-396)."""
    for name in ('x-rate-limit-retry-after-seconds', 'retry-after'):
        v = R.header(ex, name)
        try:
            s = int(Decimal((v or '').strip()))
        except (InvalidOperation, ValueError):
            continue
        if s > 0:
            return s
    return 60


# ====================================================================== контрактні правила
def rule_failure_class(bank, ex, essence=None):
    """Клас відмови (D36 п. 8) і факти для тексту людині. Класифікує конектор, бо знає факт: статус і відповідь банку.
    -> (клас, факти). «Повторити»: мережа, таймаут, 5xx, 429 після дозволеного повтору, тіло не того формату, будь-яка інша
    відповідь; «дія людини»: автентифікація (401/403), 400/404 (формат запиту, рахунку немає)."""
    facts = {'Банк': BANK_NAMES[bank]}
    if ex['failure']:
        facts.update(Вид=ex['failure']['kind'], Статус='', ОписаниеБанка='')
        return CLS_RETRY, facts
    st = ex['response']['status']
    facts.update(Вид='http', Статус=st, ОписаниеБанка=C.error_description(ex))
    if st in (401, 403, 400, 404):
        return CLS_HUMAN, facts
    return CLS_RETRY, facts


def rule_trust_boundary(out, p):
    """Межа довіри: момент першої неостаточної операції, інакше кінець періоду; при відмові — не визначена."""
    if out.failure_class:
        return None
    return min(out.nonfinal) if out.nonfinal else p.period_end


def rule_complete(out):
    """Непорожній клас відмови робить читання неповним (D36 п. 8); інакше — стан обходу сторінок."""
    return bool(out.complete and not out.failure_class)


def rule_unknown_state(out, n, state, ident):
    out.diag('Ошибка', n, 'unknown-state', None, Состояние=state, Ид=ident)
    out.rules.add('rule_unknown_state')


def rule_unknown_direction(out, n, value, ident):
    out.diag('Ошибка', n, 'unknown-direction', None, Значение=value, Ид=ident)
    out.rules.add('rule_unknown_direction')


def rule_page_without_id(out, ex):
    """exist_next_page без next_page_id: читати далі нічим — читання неповне, клас «повторити»."""
    out.failure_class = CLS_RETRY
    out.complete = False
    out.diag('Ошибка', 0, 'read-failed', None, Банк=BANK_NAMES['privat'], Вид='page-without-id', Статус=200,
             ОписаниеБанка='')
    out.rules.add('rule_page_without_id')


def rule_dedupe_by_id(seen, item, ident):
    """Той самий запис на межі сторінок (id і вміст ті самі) — один раз. -> 'dup' | 'conflict' | 'new'."""
    prev = seen.get(ident)
    if prev is None:
        seen[ident] = item
        return 'new'
    return 'dup' if prev.raw == item.raw else 'conflict'


def _failure(out, ex, bank, essence='read-failed'):
    cls, facts = rule_failure_class(bank, ex)
    out.failure_class = cls
    out.complete = False
    out.diag('Ошибка', 0, essence, None, **facts)
    out.rules.add('rule_failure_class')


# ====================================================================== ПриватБанк
def _privat(rec, p, out, disabled):
    items = []
    exs = C.exchanges_for(rec, C.PRIVAT_PATH)
    if not exs:
        raise RecordingMismatch('у записі немає запитів транзакцій ПриватБанку')
    n = 0
    for ex in exs:
        if ex['failure'] or ex['response']['status'] != 200:
            _failure(out, ex, 'privat')
            break
        try:
            js = R.body_json(ex)
        except R.NotJson:
            out.failure_class, out.complete = CLS_RETRY, False
            out.diag('Ошибка', 0, 'read-failed', None, Банк=BANK_NAMES['privat'], Вид='not-json', Статус=200,
                     ОписаниеБанка='')
            out.rules.add('rule_failure_class')
            break
        if not isinstance(js, dict) or js.get('status') != 'SUCCESS':
            desc = C.to_str(js.get('message')) if isinstance(js, dict) else ''
            out.failure_class, out.complete = CLS_RETRY, False
            out.diag('Ошибка', 0, 'read-failed', None, Банк=BANK_NAMES['privat'], Вид='api-error', Статус=200,
                     ОписаниеБанка=desc)
            out.rules.add('rule_failure_class')
            break
        for tx in js.get('transactions') or []:
            n += 1
            items.append(Item(n, tx, ex['seq']))
        if js.get('exist_next_page'):
            if js.get('next_page_id') in (None, ''):
                rule_page_without_id(out, ex)
                break
        else:
            break
    else:
        if not out.failure_class:
            raise RecordingMismatch('запис ПриватБанку кінчається, а exist_next_page лишився true')
    out.items = n
    _privat_items(out, items, p, disabled)


def _privat_items(out, items, p, disabled):
    by_ident = {}
    for it in items:
        idv = dev7_privat_identifier(it.raw, p, set()) if p.privat_id else ''
        by_ident.setdefault(idv, []).append(it) if idv else None
    for it in items:
        d, n = it.raw, it.n
        state = C.to_str(d.get('PR_PR')) or 'r'
        # у діагностиці — той самий ідентифікатор, який операція матиме наступного разу (Review Focus 2)
        ident_for_diag = (dev7_privat_identifier(d, p, set()) if p.privat_id else '') or C.to_str(d.get('TECHNICAL_TRANSACTION_ID'))
        try:
            moment = C.parse_1c_date(C.to_str(d.get('DATE_TIME_DAT_OD_TIM_P')))
        except ValueError:
            out.diag('Ошибка', n, 'bad-date', None, Ид=ident_for_diag)
            continue
        verdict = 'emit'
        if state == 'p':
            verdict = dev2_nonfinal(out, disabled, n, 'p', moment, ident_for_diag, 'emit')
        elif state == 'n':
            verdict = dev3_privat_rejected(out, disabled, n, ident_for_diag, moment)
        elif state == 't':
            idv = dev7_privat_identifier(d, p, set()) if p.privat_id else ''
            collides = bool(idv) and any(o is not it for o in by_ident.get(idv, []))
            verdict = dev4_reversal(out, disabled, n, 't', ident_for_diag, collides, 'emit')
        elif state != 'r':
            rule_unknown_state(out, n, state, ident_for_diag)
            continue
        if verdict != 'emit':
            continue
        own = C.to_str(d.get('AUT_MY_ACC'))
        if not C.account_equal(p.account, own):
            if dev1_foreign_account(out, disabled, n, own, None) == 'silent':
                continue
            number = own
        else:
            number = p.account
        tran = d.get('TRANTYPE')
        if tran not in ('D', 'C'):
            rule_unknown_direction(out, n, C.to_str(tran), ident_for_diag)
            continue
        try:
            amount = abs(C.number(d.get('SUM')))
        except ValueError:
            out.diag('Ошибка', n, 'bad-amount', None, Ид=ident_for_diag)
            continue
        ccy_text = C.to_str(d.get('CCY'))
        code = dev6_currency(ccy_text, disabled, p) if ccy_text else ''
        if ccy_text and code is None:
            out.diag('Ошибка', n, 'unknown-currency', None, Ид=ident_for_diag, Код=ccy_text)
            continue
        if ccy_text and ccy_text != 'UAH' and 'dev6' not in disabled:
            if code != p.old_currency_catalog.get(ccy_text, ''):
                out.applied.add('dev6')
        out.ops.append({
            'ПорядковыйНомер': n, 'НомерСчета': number, 'Валюта': code or '', 'ДатаОперации': C.iso(moment),
            'НомерДокумента': C.to_str(d.get('NUM_DOC')), 'ДатаДокумента': C.iso_day(moment),
            'Сумма': C.amount_str(amount), 'Направление': 'Списано' if tran == 'D' else 'Поступило',
            'ИдентификаторОперации': dev7_privat_identifier(d, p, disabled),
            'КонтрагентНаименование': C.to_str(d.get('AUT_CNTR_NAM')),
            'КонтрагентНомерСчета': C.to_str(d.get('AUT_CNTR_ACC')), 'КонтрагентКод': C.to_str(d.get('AUT_CNTR_CRF')),
            'КонтрагентМФО': C.to_str(d.get('AUT_CNTR_MFO')),
            'НазначениеПлатежа': dev5_purpose(C.trim(C.to_str(d.get('OSND'))), disabled, mono=False)})
        if p.privat_id and 'dev7' not in disabled:
            out.applied.add('dev7')


# ====================================================================== monobank
def _mono(rec, p, out, disabled):
    corp = rec.bank == 'mono-corp'
    bank = rec.bank
    exs = list(rec.exchanges)
    if not corp and not p.old_cached_account_id:
        info = [e for e in exs if e['request']['path'] == C.FOP_CLIENT_INFO]
        if not info:
            raise RecordingMismatch('у записі ФОП немає client-info')
        e = info[0]
        if e['failure'] or e['response']['status'] != 200:
            _failure(out, e, bank)
            return
        try:
            accounts = R.body_json(e).get('accounts') or []
        except (R.NotJson, AttributeError):
            accounts = None
        if accounts is None:
            out.failure_class, out.complete = CLS_RETRY, False
            out.diag('Ошибка', 0, 'read-failed', None, Банк=BANK_NAMES[bank], Вид='not-json', Статус=200, ОписаниеБанка='')
            out.rules.add('rule_failure_class')
            return
        if not any(isinstance(a, dict) and a.get('iban') == p.account for a in accounts):
            out.failure_class, out.complete = CLS_HUMAN, False
            out.diag('Ошибка', 0, 'account-not-found', None, Банк=BANK_NAMES[bank])
            out.rules.add('rule_failure_class')
            return
    stmts = C.statement_exchanges(rec)
    if not stmts:
        raise RecordingMismatch('у записі немає запитів виписки')
    items, n, complete, i = [], 0, True, 0
    while i < len(stmts):
        ex = stmts[i]
        i += 1
        acct, frm, to = R.statement_window(ex)
        if ex['response'] and ex['response']['status'] == 429:
            # dev9: один повтор після 429 за заголовком (юросіб це вже мав, ФОП — ні)
            if 'dev9' in disabled and not corp:
                _failure(out, ex, bank)
                break
            if i < len(stmts):
                ex = stmts[i]
                i += 1
                out.applied.add('dev9') if not corp else None
            else:
                raise RecordingMismatch('запис кінчається на 429 без повтору')
        if ex['failure'] or ex['response']['status'] != 200:
            _failure(out, ex, bank)
            break
        try:
            page = R.body_json(ex)
        except R.NotJson:
            page = None
        if not isinstance(page, list):
            out.failure_class, out.complete = CLS_RETRY, False
            out.diag('Ошибка', 0, 'read-failed', None, Банк=BANK_NAMES[bank], Вид='not-json' if page is None else 'not-array',
                     Статус=200, ОписаниеБанка='')
            out.rules.add('rule_failure_class')
            break
        earliest = None
        start_local, upper_local = kyiv.unix_to_local(frm), kyiv.unix_to_local(to)
        for tx in page:
            n += 1
            items.append(Item(n, tx, ex['seq']))
            t = kyiv.unix_to_local(int(tx.get('time')))
            earliest = t if earliest is None or t < earliest else earliest
        if len(page) < C.PAGE_SIZE_MONO:
            if corp:
                break
            continue
        if earliest is None or earliest <= start_local:
            if corp:
                complete = False
                break
            continue
        if earliest >= upper_local:
            complete = False
            if corp:
                break
    out.complete = out.complete and complete
    out.items = n
    _mono_items(out, items, p, disabled, corp)


def _mono_items(out, items, p, disabled, corp):
    bank = 'mono-corp' if corp else 'mono-fop'
    by_id = {}
    for it in items:
        by_id.setdefault(C.to_str(it.raw.get('id')), []).append(it)

    def is_reversal(r):
        return corp and r.get('reverse') is True

    seen = {}
    for it in items:
        r, n = it.raw, it.n
        ident = C.to_str(r.get('id'))
        v = rule_dedupe_by_id(seen, it, ident)
        if v == 'dup':
            out.duplicates += 1
            out.rules.add('rule_dedupe_by_id')
            continue
        if v == 'conflict' and not is_reversal(r) and not is_reversal(seen[ident].raw):
            out.diag('Ошибка', n, 'conflicting-duplicate', None, Ид=ident)
            out.rules.add('rule_dedupe_by_id')
            continue
        moment_sec = r.get('completedTime') if corp and r.get('completedTime') is not None else r.get('time')
        try:
            moment = dev8_local_time(int(moment_sec), p, disabled)
            created = dev8_local_time(int(r.get('time')), p, disabled)
        except (TypeError, ValueError):
            out.diag('Ошибка', n, 'bad-date', None, Ид=ident)
            continue
        if 'dev8' not in disabled and p.old_session_tz != 'Europe/Kiev':
            out.applied.add('dev8')
        verdict = 'emit'
        if corp:
            status = C.to_str(r.get('status'))
            if status == 'PENDING':
                verdict = dev2_nonfinal(out, disabled, n, 'PENDING', created, ident, 'silent')
            elif status == 'DECLINED':
                verdict = dev2_nonfinal(out, disabled, n, 'DECLINED', created, ident, 'silent')
            elif status != 'DONE':
                rule_unknown_state(out, n, status, ident)
                continue
            elif r.get('reverse') is True:
                collides = any(o is not it and not is_reversal(o.raw) for o in by_id[ident])
                verdict = dev4_reversal(out, disabled, n, 'reverse', ident, collides, 'silent')
        elif r.get('hold') is True:
            verdict = dev2_nonfinal(out, disabled, n, 'hold', created, ident, 'silent')
        if verdict != 'emit':
            continue
        amount = Decimal(str(r.get('amount'))) / 100
        code = _mono_currency(r.get('currencyCode'))
        out.ops.append({
            'ПорядковыйНомер': n, 'НомерСчета': p.account, 'Валюта': code, 'ДатаОперации': C.iso(moment),
            'НомерДокумента': ident, 'ДатаДокумента': C.iso_day(moment), 'Сумма': C.amount_str(abs(amount)),
            'Направление': 'Списано' if amount < 0 else 'Поступило', 'ИдентификаторОперации': ident,
            'КонтрагентНаименование': C.to_str(r.get('counterName')),
            'КонтрагентНомерСчета': C.to_str(r.get('counterIban')), 'КонтрагентКод': C.to_str(r.get('counterEdrpou')),
            'КонтрагентМФО': '',
            'НазначениеПлатежа': dev5_purpose(oracle_old._mono_purpose_full(r, corp), disabled)})
        if len(oracle_old._mono_purpose_full(r, corp)) > 255:
            out.applied.add('dev5') if 'dev5' not in disabled else None


def _mono_currency(v):
    if v is None:
        return ''
    s = C.to_str(v).strip()
    return s.zfill(3) if s.isdigit() else (C.numeric_currency(s) or '')


# ====================================================================== перевірка запитів запису
def expected_windows(p, bank):
    """Відрізки читання, які зробив би конектор: ФОП — до 31 доби (місцевий час), юросіб — один."""
    if bank == 'mono-fop':
        return C.fop_windows(p.period_start, p.period_end)
    return [(p.period_start, p.period_end)]


def verify_requests(rec, p):
    """Чи відрізки запису збігаються з тим, що зробив би конектор: `from` першого запиту кожного відрізка й `to` першого
    відрізка (далі `to` зсувається за сторінками). -> перелік розбіжностей. Для синтетики — самоперевірка генератора;
    для справжніх записів — лише інформація (рекордер міг ходити інакше)."""
    if rec.bank == 'privat' or not C.statement_exchanges(rec):
        return []
    want = [(kyiv.local_to_unix(a), kyiv.local_to_unix(b)) for a, b in expected_windows(p, rec.bank)]
    starts = []
    for e in C.statement_exchanges(rec):
        w = R.statement_window(e)
        if not starts or starts[-1][0] != w[1]:
            starts.append((w[1], w[2]))
    problems = []
    if [s[0] for s in starts] != [w[0] for w in want]:
        problems.append('from відрізків: запис %r, очікувано %r' % ([s[0] for s in starts], [w[0] for w in want]))
    elif starts and starts[0][1] != want[0][1]:
        problems.append('to першого відрізка: запис %r, очікувано %r' % (starts[0][1], want[0][1]))
    return problems
