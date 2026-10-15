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

from datetime import datetime, timedelta

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
    duplicate_numbers: list = field(default_factory=list)
    silent: int = 0                                  # відкинуто без сліду (лише вимкнений відступ чи старий пропуск)
    nonfinal: list = field(default_factory=list)     # моменти неостаточних операцій
    bank_boundary: object = None                     # межа остаточності від банку (settings / balances), D36 п. 10

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
PRIVAT_AUTH_SERVICE_PREFIX = 'CLIENT_AUTH'      # privat.txt: CLIENT_AUTH, _DENY, _BADSESSION, _P24_CHECK_ERR, _P24_NOT_VALID, _ERROR


def rule_failure_class(bank, ex):
    """Клас відмови (D36 п. 8) і факти для тексту людині. Принцип: чи допоможе повтор?
    «Повторити» — мережа, таймаут, 408, 429 (після дозволеного повтору), 5xx, будь-яка інша нестандартна відповідь;
    «дія людини» — 401, 403 та інші 4xx (токен, права, формат запиту, рахунку немає)."""
    facts = {'Банк': BANK_NAMES[bank]}
    if ex['failure']:
        facts.update(Вид=ex['failure']['kind'], Статус='', ОписаниеБанка='')
        return CLS_RETRY, facts
    st = ex['response']['status']
    facts.update(Вид='http', Статус=st, ОписаниеБанка=C.error_description(ex))
    if st in (408, 429) or st >= 500:
        return CLS_RETRY, facts
    if 400 <= st < 500:
        return CLS_HUMAN, facts
    return CLS_RETRY, facts


def rule_privat_api_error(js):
    """`status: ERROR` при HTTP 200 (тіло за privat.txt: `code` — HTTP-статус рядком, `message`, `serviceCode`).
    Той самий принцип: автентифікація (`serviceCode` починається з CLIENT_AUTH) та 4xx у `code` — «дія людини»;
    решта (5xx, немає коду) — «повторити». Перелік `CLIENT_AUTH*` — з документації."""
    code = C.trim(C.to_str(js.get('code')))
    service = C.trim(C.to_str(js.get('serviceCode')))
    facts = {'Банк': BANK_NAMES['privat'], 'Вид': 'api-error', 'Статус': 200, 'ОписаниеБанка': C.to_str(js.get('message')),
             'КодСервиса': service}
    human = service.startswith(PRIVAT_AUTH_SERVICE_PREFIX) or (code.isdigit() and 400 <= int(code) < 500)
    return (CLS_HUMAN if human else CLS_RETRY), facts


def rule_trust_boundary(out, p):
    """Межа довіри (D36 п. 10): найраніша з `КонецПериода`, моменту першої неостаточної операції й банківської межі
    (ПриватБанк — `date_final_statement`; юросіб — початок першого дня без `isFinal`; ФОП — лише `hold`); не раніша за
    `НачалоПериода`. При непорожньому класі відмови — `НачалоПериода`: нічого не підтверджено."""
    if out.failure_class:
        return p.period_start
    cands = [p.period_end] + list(out.nonfinal)
    if out.bank_boundary is not None:
        cands.append(out.bank_boundary)
    return max(p.period_start, min(cands))


def rule_bank_boundary_privat(settings_day, p):
    """ПриватБанк: `date_final_statement` — «дата, включно з якої є підсумкова виписка». Чи остаточний сам цей день —
    не виміряно; до виміру день вважається НЕ остаточним (межа = його початок), параметр `privat_final_date_inclusive`."""
    start = settings_day.replace(hour=0, minute=0, second=0)
    return start + timedelta(days=1) if p.privat_final_date_inclusive else start


def rule_bank_boundary_corp(balances, p):
    """monobank юросіб: початок ПЕРШОГО дня запитаного періоду без `isFinal = true` (не кінець останнього остаточного
    дня: межа не мусить перескочити діру). День, якого немає у відповіді, до виміру вважається не остаточним
    (`corp_absent_day_is_final`). -> datetime або None, якщо всі дні остаточні."""
    final = {}
    for b in balances:
        if isinstance(b, dict) and b.get('date'):
            final[C.to_str(b['date'])] = b.get('isFinal') is True
    day = datetime(p.period_start.year, p.period_start.month, p.period_start.day)
    last = datetime(p.period_end.year, p.period_end.month, p.period_end.day)
    while day <= last:
        key = day.strftime('%Y-%m-%d')
        ok = final[key] if key in final else p.corp_absent_day_is_final
        if not ok:
            return day
        day += timedelta(days=1)
    return None


def rule_complete(out):
    """Непорожній клас відмови робить читання неповним (D36 п. 8); інакше — стан обходу сторінок."""
    return bool(out.complete and not out.failure_class)


def rule_unknown_state(out, n, state, ident):
    out.diag('Ошибка', n, 'unknown-state', None, Состояние=state, Ид=ident)
    out.rules.add('rule_unknown_state')


def rule_unknown_direction(out, n, value, ident):
    out.diag('Ошибка', n, 'unknown-direction', None, Значение=value, Ид=ident)
    out.rules.add('rule_unknown_direction')


def _fail(out, cls, facts, essence='read-failed'):
    """Збій читання з непорожнім класом: неповне читання (курсор утримується), даних не втрачено -> `Предупреждение`.
    `Ошибка` — лише операція, яку неможливо подати."""
    out.failure_class = cls
    out.complete = False
    out.diag('Предупреждение', 0, essence, None, **facts)
    out.rules.add('rule_failure_class')


def _failure(out, ex, bank):
    cls, facts = rule_failure_class(bank, ex)
    _fail(out, cls, facts)


def _fail_not_json(out, bank, kind='not-json'):
    _fail(out, CLS_RETRY, {'Банк': BANK_NAMES[bank], 'Вид': kind, 'Статус': 200, 'ОписаниеБанка': ''})


def rule_page_without_id(out, ex):
    """exist_next_page без next_page_id: читати далі нічим — читання неповне, «повторити», `Предупреждение`."""
    _fail(out, CLS_RETRY, {'Банк': BANK_NAMES['privat'], 'Вид': 'page-without-id', 'Статус': 200, 'ОписаниеБанка': ''})
    out.rules.add('rule_page_without_id')


def rule_dedupe_by_id(out, items, ident_of, is_final, is_reversal):
    """Дублі в одному читанні — за ідентифікатором операції. Фільтр стану СПЕРШУ, як у попередника (MU:309-323,
    MF:312-324): неостаточний запис у `seen` не потрапляє, тож `DONE` з тим самим id на наступній сторінці не губиться.
    Тотожний запис (id і вміст) — один раз; той самий id з іншим вмістом, що не реверс, — `Ошибка conflicting-duplicate`.
    Якщо ідентифікатора немає (`ident_of` дає порожнє — зокрема Приват без стабільного ідентифікатора), дедуплікації за
    вмістом НЕМАЄ: дві справжні однакові операції не зливаються (D35.4). -> множина номерів, які далі не обробляються."""
    seen, seen_nonfinal, skip = {}, {}, set()
    for it in items:
        idv = ident_of(it)
        if not idv:
            continue
        table = seen if is_final(it) else seen_nonfinal
        prev = table.get(idv)
        if prev is None:
            table[idv] = it
        elif prev.raw == it.raw:
            out.duplicates += 1
            out.duplicate_numbers.append(it.n)
            skip.add(it.n)
            out.rules.add('rule_dedupe_by_id')
        elif table is seen and not (is_reversal(it) or is_reversal(prev)):
            out.diag('Ошибка', it.n, 'conflicting-duplicate', None, Ид=idv)
            skip.add(it.n)
            out.rules.add('rule_dedupe_by_id')
    return skip


# ====================================================================== ПриватБанк
def _privat_state(raw):
    return C.to_str(raw.get('PR_PR')) or 'r'


def _privat(rec, p, out, disabled):
    items = []
    n = 0
    if not _privat_settings(rec, p, out):
        return
    exs = C.exchanges_for(rec, C.PRIVAT_PATH)
    if not exs:
        raise RecordingMismatch('у записі немає запитів транзакцій ПриватБанку')
    for ex in exs:
        if ex['failure'] or ex['response']['status'] != 200:
            _failure(out, ex, 'privat')
            break
        try:
            js = R.body_json(ex)
        except R.NotJson:
            _fail_not_json(out, 'privat')
            break
        if not isinstance(js, dict):
            _fail_not_json(out, 'privat', 'not-object')
            break
        if js.get('status') != 'SUCCESS':
            if js.get('status') == 'ERROR':
                cls, facts = rule_privat_api_error(js)
            else:
                cls, facts = CLS_RETRY, {'Банк': BANK_NAMES['privat'], 'Вид': 'unexpected-status', 'Статус': 200,
                                         'ОписаниеБанка': C.to_str(js.get('message'))}
            _fail(out, cls, facts)
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


def _privat_settings(rec, p, out):
    """Обмін `/settings` (банківська межа): перший запит читання. Збій — відмова за п. 8. -> True, якщо читати далі."""
    exs = C.exchanges_for(rec, C.PRIVAT_SETTINGS_PATH)
    if not exs:
        raise RecordingMismatch('у записі ПриватБанку немає /settings')
    ex = exs[0]
    if ex['failure'] or ex['response']['status'] != 200:
        _failure(out, ex, 'privat')
        return False
    try:
        js = R.body_json(ex)
    except R.NotJson:
        _fail_not_json(out, 'privat')
        return False
    if isinstance(js, dict) and js.get('status') == 'ERROR':
        cls, facts = rule_privat_api_error(js)
        _fail(out, cls, facts)
        return False
    try:
        day = C.parse_1c_date(C.to_str(js['settings']['date_final_statement']))
    except (KeyError, TypeError, ValueError):
        _fail(out, CLS_RETRY, {'Банк': BANK_NAMES['privat'], 'Вид': 'bad-settings', 'Статус': 200, 'ОписаниеБанка': ''})
        return False
    out.bank_boundary = rule_bank_boundary_privat(day, p)
    return True


def _privat_items(out, items, p, disabled):
    def ident_of(it):
        return dev7_privat_identifier(it.raw, p, set()) if p.privat_id else ''

    def is_final(it):
        return _privat_state(it.raw) in ('r', 't')

    def is_reversal(it):
        return _privat_state(it.raw) == 't'

    skip = rule_dedupe_by_id(out, items, ident_of, is_final, is_reversal)
    by_ident = {}
    for it in items:
        if is_final(it) and ident_of(it):
            by_ident.setdefault(ident_of(it), []).append(it)
    for it in items:
        if it.n in skip:
            continue
        d, n = it.raw, it.n
        state = _privat_state(d)
        # у діагностиці — той самий ідентифікатор, який операція матиме наступного разу (Review Focus 2)
        ident_for_diag = ident_of(it) or C.to_str(d.get('TECHNICAL_TRANSACTION_ID'))
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
            idv = ident_of(it)
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
            _fail_not_json(out, bank)
            return
        if not any(isinstance(a, dict) and a.get('iban') == p.account for a in accounts):
            _fail(out, CLS_HUMAN, {'Банк': BANK_NAMES[bank]}, 'account-not-found')
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
            _fail_not_json(out, bank, 'not-json' if page is None else 'not-array')
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
    if corp and not out.failure_class:
        _corp_balances(rec, p, out)


def _corp_balances(rec, p, out):
    """Обмін `balances` (банківська межа юросіб): після виписки. Збій — відмова за п. 8, прочитане лишається."""
    exs = [e for e in rec.exchanges if e['request']['path'].endswith('/balances')]
    if not exs:
        raise RecordingMismatch('у записі юросіб немає balances')
    ex = exs[0]
    if ex['response'] and ex['response']['status'] == 429 and len(exs) > 1:
        ex = exs[1]                                         # один повтор після 429
    if ex['failure'] or ex['response']['status'] != 200:
        _failure(out, ex, 'mono-corp')
        return
    try:
        balances = R.body_json(ex)
    except R.NotJson:
        balances = None
    if not isinstance(balances, list):
        _fail_not_json(out, 'mono-corp', 'not-json' if balances is None else 'not-array')
        return
    out.bank_boundary = rule_bank_boundary_corp(balances, p)


def _mono_items(out, items, p, disabled, corp):
    def ident_of(it):
        return C.to_str(it.raw.get('id'))

    def is_final(it):
        if corp:
            return C.to_str(it.raw.get('status')) == 'DONE'
        return it.raw.get('hold') is not True

    def is_reversal(it):
        return corp and it.raw.get('reverse') is True

    skip = rule_dedupe_by_id(out, items, ident_of, is_final, is_reversal)
    by_id = {}
    for it in items:
        if is_final(it):
            by_id.setdefault(ident_of(it), []).append(it)
    for it in items:
        if it.n in skip:
            continue
        r, n = it.raw, it.n
        ident = ident_of(it)
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
                collides = any(o is not it and not is_reversal(o) for o in by_id.get(ident, []))
                verdict = dev4_reversal(out, disabled, n, 'reverse', ident, collides, 'silent')
        elif r.get('hold') is True:
            verdict = dev2_nonfinal(out, disabled, n, 'hold', created, ident, 'silent')
        if verdict != 'emit':
            continue
        amount = Decimal(str(r.get('amount'))) / 100
        code = _mono_currency(r.get('currencyCode'))
        if code is None:
            out.diag('Ошибка', n, 'unknown-currency', None, Ид=ident, Код=C.to_str(r.get('currencyCode')))
            continue
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
    """Числовий `currencyCode` monobank (980 / '980') -> три цифри через ту саму таблицю, що `ЧисловойКодВалюты`;
    немає поля -> '' (валюта рахунку); невідомий код -> None."""
    if v is None:
        return ''
    s = C.to_str(v).strip()
    return C.numeric_currency(s.zfill(3) if s.isdigit() else s)


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
