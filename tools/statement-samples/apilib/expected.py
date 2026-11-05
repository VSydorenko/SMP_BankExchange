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
| dev9 | технічне: `limit` і пауза ПриватБанку; повтор після 429 за заголовком; пауза після client-info (за замовчуванням 0); |
|      | кількість і зміст операцій від цього не змінюються |

**Контрактні правила** (не відступи, а розвиток D28/D36 п. 8 для API): `rule_failure_class`, `rule_complete`,
`rule_trust_boundary`, `rule_unknown_state`, `rule_unknown_direction`, `rule_page_without_id`, `rule_dedupe_by_id`; ПУМБ: `rule_identifier_length` (D28), `rule_no_iban` (Р-д).
Їхні рішення — окремий рядок звіту виконавця: планувальник підтверджує або відкидає.
"""
import json
import re
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
PAUSE_CEILING = C.PAUSE_CEILING_SECONDS
MONO_PAUSE_SECONDS = 60             # MF:485-490: ліміт monobank ФОП — 1 запит на 60 с
BANK_NAMES = {'privat': 'ПриватБанк', 'mono-fop': 'monobank ФОП', 'mono-corp': 'monobank юросіб', 'pumb': 'ПУМБ'}
OP_COLUMNS = ['ПорядковыйНомер', 'НомерСчета', 'Валюта', 'ДатаОперации', 'НомерДокумента', 'ДатаДокумента', 'Сумма',
              'Направление', 'ИдентификаторОперации', 'КонтрагентНаименование', 'КонтрагентНомерСчета', 'КонтрагентКод',
              'КонтрагентМФО', 'НазначениеПлатежа']


class Consumed:
    """Спожита частина запису: те, що бачить `dev9_pauses`."""

    def __init__(self, bank, exchanges):
        self.bank, self.exchanges = bank, exchanges


def use(out, ex):
    if not any(x is ex for x in out.used):
        out.used.append(ex)


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
    bank_boundary: object = None                     # межа остаточності від банку (balances), D36 п. 10
    used: list = field(default_factory=list)         # обміни запису, які оракул СПОЖИВ, у порядку споживання
    account_currency: object = None                  # валюта рахунку ПриватБанку з /balance (буквений код); None -- невідома
    out_of_period: list = field(default_factory=list)  # номери записів поза періодом (відкинуто мовчки), D36 п. 11
    skipped_nonmove: list = field(default_factory=list)  # ПУМБ: номери документів відомих типів «не рух» (STM, CUR, CUR_C, CUR_S; див. `PUMB_NONMOVEMENT_TYPES`), не операції; ЛІЧИЛЬНИК для звірки «нічого не зникає мовчки», рядка діагностики немає
    foreign_docs: list = field(default_factory=list)   # ПУМБ: номери документів, чий рахунок сторін не збігся ні з IBAN, ні з номером запитаного (не операції; один рядок Предупреждение на читання з кількістю, відступ pumb1)

    def diag(self, level, n, essence, dev=None, **facts):
        self.diags.append({'Уровень': level, 'ПорядковыйНомер': n, 'Суть': essence, 'Отступ': dev or '', 'Факты': facts})
        if dev:
            self.applied.add(dev)


def request_entry(e, bank):
    """Запит для `Запросы` еталона. Для ПУМБ (формат v2) -- ще `Порт` і `Тело` (JSON розібраний; `bodyOmitted` -- `ТелоОпущено`), лише для ПУМБ."""
    rq = e['request']
    d = {'Метод': rq['method'], 'Хост': rq['host'], 'Путь': rq['path'], 'Запрос': [list(kv) for kv in R.query_pairs(e)]}
    if bank == 'pumb':
        if rq.get('port'):
            d['Порт'] = rq['port']
        if rq.get('bodyOmitted'):
            d['ТелоОпущено'] = True
        elif 'bodyBase64' in rq or 'bodyMasked' in rq:
            d['Тело'] = json.loads(R.request_body_text(e))
    return d


def run(rec, p, disabled=frozenset()):
    if rec.bank != 'pumb' and rec.bank not in C.BANKS:
        raise ValueError('невідомий банк ' + rec.bank)
    out = Expected(rec.bank)
    if rec.bank == 'pumb':
        _pumb(rec, p, out, frozenset(disabled))
    else:
        {'privat': _privat, 'mono-fop': _mono, 'mono-corp': _mono}[rec.bank](rec, p, out, frozenset(disabled))
    # Запити й паузи -- лише обміни, які конектор справді зробить: відмова зупиняє читання, обміну балансів після неї немає (I1)
    out.requests = [request_entry(e, rec.bank) for e in out.used]
    out.pauses = dev9_pauses(Consumed(rec.bank, out.used), p, 'dev9' not in disabled, out)
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
            resp = ex[k - 1]['response']
            if resp and resp['status'] == 429:
                add(k, _retry_seconds(ex[k - 1]), 'after-429', True)         # 429: пауза за заголовком (не менша за звичайну)
            else:
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
                add(k, min(_retry_seconds(e), PAUSE_CEILING), 'limit-exhausted', False)      # випереджальна пауза обмежена стелею
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


PUMB_CUT_MARK = '<вирізано>'
PUMB_RECORDER_FORM = 'перший запит searcher у формі рекордера (межі рівно по періоду, фільтри стану й типу), не конектора (межі цілими добами, без фільтрів)'   # run1b, run2


def pumb_error_description(ex, secrets=()):
    """Опис помилки ПУМБ для діагностики (Р-е): `error_description` (Keycloak/OAuth2), далі `errorDescription`, `message`; немає -- порожньо. Текст береться ЛИШЕ через
    вирізання значень облікових даних (`secrets`: логін тощо, без регістру; довші першими) -- замість кожного входження `<вирізано>`. Самих значень не повертає й не пише."""
    try:
        js = R.body_json(ex)
    except R.NotJson:
        return ''
    if not isinstance(js, dict):
        return ''
    for k in ('error_description', 'errorDescription', 'message'):
        if js.get(k) is not None:
            text = C.to_str(js[k])
            for sec in sorted({C.to_str(x) for x in secrets if C.to_str(x)}, key=len, reverse=True):
                text = re.sub(re.escape(sec), PUMB_CUT_MARK, text, flags=re.IGNORECASE)
            return text
    return ''


def rule_failure_class(bank, ex, secrets=()):
    """Клас відмови (D36 п. 8) і факти для тексту людині. Принцип: чи допоможе повтор?
    «Повторити» — мережа, таймаут, 408, 429 (після дозволеного повтору), 5xx, 2xx крім 200;
    «дія людини» — 401, 403 та інші 4xx (токен, права, формат запиту, рахунку немає), а також 1xx і 3xx (тлумачення п. 8).
    `secrets` -- лише ПУМБ: значення облікових даних, що вирізаються з опису банку (`pumb_error_description`)."""
    facts = {'Банк': BANK_NAMES[bank]}
    if ex['failure']:
        facts.update(Вид=ex['failure']['kind'], Статус='', ОписаниеБанка='')
        return CLS_RETRY, facts
    st = ex['response']['status']
    facts.update(Вид='http', Статус=st, ОписаниеБанка=pumb_error_description(ex, secrets) if bank == 'pumb' else C.error_description(ex))
    if st in (408, 429) or st >= 500:
        return CLS_RETRY, facts
    if 200 <= st < 300:
        return CLS_RETRY, facts                 # 2xx, крім очікуваного 200, -- несподівана відповідь, тимчасова проблема
    return CLS_HUMAN, facts                     # 4xx, а також 1xx і 3xx (тлумачення п. 8, як у спільному класі конекторів): повтор не допоможе


def rule_privat_api_error(js):
    """`status: ERROR` при HTTP 200 (тіло за privat.txt: `code` — HTTP-статус рядком, `message`, `serviceCode`).
    Той самий принцип: автентифікація (`serviceCode` починається з CLIENT_AUTH) та 4xx у `code` — «дія людини»;
    решта (5xx, немає коду) — «повторити». Перелік `CLIENT_AUTH*` — з документації."""
    code = C.trim(C.to_str(js.get('code')))
    service = C.trim(C.to_str(js.get('serviceCode')))
    facts = {'Банк': BANK_NAMES['privat'], 'Вид': 'api-error', 'Статус': 200, 'ОписаниеБанка': C.to_str(js.get('message')),
             'КодСервиса': service}
    human = service.startswith(PRIVAT_AUTH_SERVICE_PREFIX) or (
        code.isdigit() and 400 <= int(code) < 500 and int(code) not in (408, 429))   # 408/429 повтор лікує, як і в HTTP
    return (CLS_HUMAN if human else CLS_RETRY), facts


def rule_trust_boundary(out, p):
    """Межа довіри (D36 п. 10): найраніша з `КонецПериода`, моменту першої неостаточної операції й банківської межі
    (подобові баланси: ПриватБанк — `is_final_bal` у `/balance`, юросіб — `isFinal` у `balances`, початок першого дня без ознаки; ФОП — лише `hold`); не раніша за
    `НачалоПериода`. При непорожньому класі відмови — `НачалоПериода`: нічого не підтверджено."""
    if out.failure_class:
        return p.period_start
    cands = [p.period_end] + list(out.nonfinal)
    if p.reading_moment is not None:
        cands.append(kyiv.unix_to_local(C.reading_unix(p)))          # D36 п. 10 (a90f7ea): не пізніша за момент читання
    if out.bank_boundary is not None:
        cands.append(out.bank_boundary)
    return max(p.period_start, min(cands))


def rule_work_balance(settings):
    """`/settings` ПриватБанку: `work_balance = Y` — іде регламент банку, «запити не робити» (privat.txt:101). Конектор запитів
    транзакцій не робить: клас «повторити», `Предупреждение`, читання неповне, межа — `НачалоПериода`.

    ВІДСТУП НА БЕЗПЕЧНИЙ БІК (не з переліку 1–9): попередник `work_balance` не перевіряв і `/settings` не викликав взагалі
    (у `СМП_РаботаСБанкамиПриватБанкAPIСервер` рядка `work_balance` немає; читання — `ПрочитатьВыписки`, PB:2-63, викликається з
    PB:306 і PB:412 одразу, без пробного запиту) — він робив запити попри `Y`, тож під час регламенту банку міг отримати помилку
    або неповні дані."""
    return C.trim(C.to_str(settings.get('work_balance'))).upper() == 'Y'


def _first_nonfinal_day(final, p):
    """Початок ПЕРШОГО дня запитаного періоду без ознаки остаточності. День, якого немає у відповіді, -- неостаточний
    (`absent_day_is_final`, до виміру False). Не кінець останнього остаточного дня: межа не мусить перескочити діру.
    -> datetime або None, якщо всі дні остаточні."""
    day = datetime(p.period_start.year, p.period_start.month, p.period_start.day)
    last = datetime(p.period_end.year, p.period_end.month, p.period_end.day)
    while day <= last:
        key = day.strftime('%Y-%m-%d')
        ok = final[key] if key in final else p.absent_day_is_final
        if not ok:
            return day
        day += timedelta(days=1)
    return None


def rule_bank_boundary_privat(balances, p):
    """ПриватБанк (D36 п. 10): початок першого дня без `is_final_bal = true` у `/balance` за період. День балансу -- поле
    `dpd` (`DD.MM.YYYY HH:MM:SS`; виміряно run1: 44 рядки на 44 доби, від нових до старих). `date_final_statement` з
    `/settings` у межі НЕ бере участі: у run1 воно лежало за 184 доби до кінця періоду (журнал 05а, пункт 6)."""
    final = {}
    for b in balances:
        if isinstance(b, dict) and b.get('dpd'):
            try:
                day = C.parse_1c_date(C.to_str(b['dpd']))
            except ValueError:
                continue
            key = day.strftime('%Y-%m-%d')
            final[key] = final.get(key, True) and b.get('is_final_bal') is True      # день остаточний, лише якщо ВСІ його рядки остаточні
    return _first_nonfinal_day(final, p)


def rule_bank_boundary_corp(balances, p):
    """monobank юросіб (D36 п. 10): початок першого дня без `isFinal = true` у `balances`; день без рядка -- неостаточний."""
    final = {}
    for b in balances:
        if isinstance(b, dict) and b.get('date'):
            key = C.to_str(b['date'])
            final[key] = final.get(key, True) and b.get('isFinal') is True           # те саме: один неостаточний рядок -- день неостаточний
    return _first_nonfinal_day(final, p)


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


def _failure(out, ex, bank, secrets=()):
    cls, facts = rule_failure_class(bank, ex, secrets)
    _fail(out, cls, facts)


def _fail_not_json(out, bank, kind='not-json'):
    _fail(out, CLS_RETRY, {'Банк': BANK_NAMES[bank], 'Вид': kind, 'Статус': 200, 'ОписаниеБанка': ''})


def rule_page_without_id(out, ex):
    """exist_next_page без next_page_id: читати далі нічим — читання неповне, «повторити», `Предупреждение`."""
    _fail(out, CLS_RETRY, {'Банк': BANK_NAMES['privat'], 'Вид': 'page-without-id', 'Статус': 200, 'ОписаниеБанка': ''})
    out.rules.add('rule_page_without_id')


def rule_pause_over_ceiling(out, ex, bank, ask):
    """Пауза за заголовком банку (`retry-after`, `x-rate-limit-retry-after-seconds`) понад стелю конектора (D36 п. 8, спека a90f7ea): конектор
    не чекає -- `Повторить`, читання неповне, діагностика називає запитану паузу. Нерозібраний заголовок (HTTP-дата) -- пауза за
    замовчуванням 60 с (`_retry_seconds`), стелі не перевищує."""
    _fail(out, CLS_RETRY, {'Банк': BANK_NAMES[bank], 'Вид': 'pause-over-ceiling', 'Статус': ex['response']['status'],
                           'ОписаниеБанка': C.error_description(ex), 'Пауза': ask}, 'pause-over-ceiling')
    out.rules.add('rule_pause_over_ceiling')


def rule_cursor_stuck(out, bound_unix, count):
    """Застряглий курсор (D36 п. 11, п. 8; `44d22a1` і уточнення архітектора): запит продовження збігся б із поточним (E >= U - 1, `U` --
    поточна верхня межа). Повтор дав би те саме -> клас «дія людини» (не «повторити»); читання неповне; діагностика називає секунди
    між новою межею (U - 1) і поточною (U) -- київський час -- і кількість отриманих операцій; читання триває далі з межею U - 1."""
    out.failure_class = out.failure_class or CLS_HUMAN
    out.complete = False
    out.diag('Предупреждение', 0, 'cursor-stuck', None, Банк=BANK_NAMES[out.bank], Вид='cursor-stuck',
             Секунда=kyiv.unix_to_local(bound_unix - 1).strftime('%d.%m.%Y %H:%M:%S'),
             Секунда2=kyiv.unix_to_local(bound_unix).strftime('%d.%m.%Y %H:%M:%S'), Количество=count)
    out.rules.add('rule_cursor_stuck')


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


def privat_has_next(js):
    """Кінець читання ПриватБанку (D36 п. 11) -- за `exist_next_page`. `next_page_id` банк віддає й на ОСТАННІЙ сторінці
    (run1, журнал 05а, пункт 8), тож його наявність кінця не означає."""
    return bool(js.get('exist_next_page'))


_DAY_RX = re.compile(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$')


def _parse_day(s):
    """`DAT_OD` ПриватБанку (`DD.MM.YYYY`, без часу, run1: 87 з 87) -> `datetime` на початку доби; не дата -- ValueError."""
    m = _DAY_RX.match(C.trim(s or ''))
    if not m:
        raise ValueError('не дата')
    d, mo, y = (int(g) for g in m.groups())
    return datetime(y, mo, d)


def _norm_account(x):
    """Нормалізація номера рахунку точкою читання (`НормализованныйНомерСчета`): без пробілів і без різниці регістру. Рахунок за 14 цифрами
    конектор не порівнює: чужі рахунки відбирає точка читання (відступ 1 плану)."""
    return x.upper().replace(' ', '').replace('\xa0', '').replace('\t', '')


def _privat_take(out, exs, pos):
    """Наступний обмін шляху з одним повтором після 429 (як юросіб): пауза за заголовком, понад стелю -- `Повторить` без повтору й сну.
    -> обмін або None (відмова виставлена)."""
    if pos[0] >= len(exs):
        raise RecordingMismatch('у записі ПриватБанку немає наступного обміну')
    ex = exs[pos[0]]
    pos[0] += 1
    use(out, ex)
    if ex['response'] and ex['response']['status'] == 429:
        ask = _retry_seconds(ex)
        if ask > C.PAUSE_CEILING_SECONDS:
            rule_pause_over_ceiling(out, ex, 'privat', ask)
            out.applied.add('dev9')
            return None
        if pos[0] >= len(exs):
            raise RecordingMismatch('запис ПриватБанку кінчається на 429 без повтору')
        ex = exs[pos[0]]
        pos[0] += 1
        use(out, ex)
        out.applied.add('dev9')
    return ex


def _privat(rec, p, out, disabled):
    if p.reading_moment is not None and p.period_end < p.period_start:
        # Точка читання відхиляє перевернутий період ДО конектора: запитів немає, клас «дія людини»
        _fail(out, CLS_HUMAN, {}, 'period-reversed')
        out.rules.add('rule_period_reversed')
        return
    if C.privat_days(p) is None:
        out.items = 0                       # D36 п. 11: НачалоПериода пізніший за момент читання -- запитів немає, порожнє повне читання
        return
    items = []
    n = 0
    if not _privat_settings(rec, p, out):
        return
    exs = C.exchanges_for(rec, C.PRIVAT_PATH)
    if not exs:
        raise RecordingMismatch('у записі немає запитів транзакцій ПриватБанку')
    pos, follow_used, pages = [0], set(), 0
    while True:
        if pos[0] >= len(exs):
            raise RecordingMismatch('запис ПриватБанку кінчається, а exist_next_page лишився true')
        ex = _privat_take(out, exs, pos)
        if ex is None:
            break
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
        flag = privat_exist_flag(js)
        if flag is None:
            rule_exist_flag_invalid(out, 'page')
            break
        pages += 1
        if not flag:
            break
        cursor = js.get('next_page_id')
        if cursor in (None, ''):
            rule_page_without_id(out, ex)
            break
        if cursor in follow_used:
            rule_cursor_repeated(out, cursor)
            break
        follow_used.add(cursor)
        if pages >= C.page_ceiling('privat', p):
            moments = []
            for it in items:
                try:
                    moments.append(C.parse_1c_date(C.to_str(it.raw.get('DATE_TIME_DAT_OD_TIM_P'))))
                except ValueError:
                    pass
            rule_page_ceiling(out, 'privat', pages, n, moments[-1] if moments else p.period_start)
            break
    out.items = n
    if not out.failure_class:
        _privat_balance(rec, p, out)               # раніше за операції: з нього береться валюта рахунку (відступ 1)
        if out.failure_class:
            # обмін балансів не вдався (відмова за п. 8): валюту рахунку не визначено, фільтр валюти не застосовується -- той самий рядок, що й при порожній валюті в рядках балансу
            out.diag('Предупреждение', 0, 'currency-unknown', None, Банк=BANK_NAMES['privat'])
    _privat_items(out, items, p, disabled)


def rule_cursor_repeated(out, cursor):
    """`exist_next_page = true`, а `next_page_id` уже використаний як `followId` у цьому читанні: курсор банку не просувається, читати далі нічим (інакше читання не
    скінчилося б). Повтор банку не допоміг би (дані ті самі), тож клас «дія людини» (D36 п. 8; рішення планувальника 2026-11-04, п. 2, про «повторити» відкликано
    на користь D36 п. 8), читання неповне, `Предупреждение` з курсором, що повторився."""
    _fail(out, CLS_HUMAN, {'Банк': BANK_NAMES['privat'], 'Вид': 'cursor-repeated', 'Статус': 200, 'ОписаниеБанка': '', 'Значение': cursor})
    out.rules.add('rule_cursor_repeated')


def privat_exist_flag(js):
    """`exist_next_page` відповіді: True / False, а не булеве значення (рядок «false», число, відсутнє) -- None. Продукт читає прапорець так само (а не `bool(...)` Python)."""
    v = js.get('exist_next_page')
    return v if isinstance(v, bool) else None


def rule_exist_flag_invalid(out, what):
    """`exist_next_page` не булевого типу: кінець читання невідомий -- неповне, `Повторить`."""
    _fail(out, CLS_RETRY, {'Банк': BANK_NAMES['privat'], 'Вид': 'bad-exist-flag-' + what, 'Статус': 200, 'ОписаниеБанка': ''})
    out.rules.add('rule_exist_flag_invalid')


def rule_page_ceiling(out, bank, pages, ops, boundary):
    """Стеля сторінок (`C.PAGE_CEILING`, обґрунтування там): прочитано стільки сторінок, а читання не закінчилось -- «дія людини» (законний обсяг повтор не зменшить),
    діагностика називає кількість сторінок і операцій та межу, на якій читання зупинилось (Привата -- момент останньої прочитаної операції, monobank -- верхня межа
    наступного запиту; київський час), і пропонує звузити період."""
    _fail(out, CLS_HUMAN, {'Банк': BANK_NAMES[bank], 'Вид': 'page-ceiling', 'Статус': 200, 'ОписаниеБанка': '', 'Страниц': pages, 'Операций': ops,
                           'Граница': boundary.strftime('%d.%m.%Y %H:%M:%S')})
    out.rules.add('rule_page_ceiling')


def _privat_settings(rec, p, out):
    """Обмін `/settings` -- ОБОВ'ЯЗКОВИЙ перший обмін кожного читання ПриватБанку (R14: конектор читає його щоразу; ознака
    `work_balance = Y` -- іде регламент банку, `rule_work_balance`). `date_final_statement` у межі довіри участі не бере
    (D36 п. 10). Немає обміну -- ЯВНА помилка еталона (`RecordingMismatch`), а не мовчазне "перевірки немає".
    -> True, якщо читати далі."""
    exs = C.exchanges_for(rec, C.PRIVAT_SETTINGS_PATH)
    if not exs or rec.exchanges[0] is not exs[0]:
        raise RecordingMismatch('у записі ПриватБанку /settings не перший обмін')
    ex = _privat_take(out, exs, [0])
    if ex is None:
        return False
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
    if not isinstance(js, dict) or not isinstance(js.get('settings'), dict):
        _fail(out, CLS_RETRY, {'Банк': BANK_NAMES['privat'], 'Вид': 'bad-settings', 'Статус': 200, 'ОписаниеБанка': ''})
        return False
    if rule_work_balance(js['settings']):
        _fail(out, CLS_RETRY, {'Банк': BANK_NAMES['privat'], 'Вид': 'work-balance', 'Статус': 200, 'ОписаниеБанка': ''},
              'work-balance')
        out.rules.add('rule_work_balance')
        return False
    return True


def _privat_balance(rec, p, out):
    """Обмін `/balance` за ті самі дні, що й транзакції (банківська межа ПриватБанку): після транзакцій. Збій -- відмова за п. 8, прочитане лишається."""
    exs = C.exchanges_for(rec, C.PRIVAT_BALANCE_PATH)
    if not exs:
        raise RecordingMismatch('у записі ПриватБанку немає /balance')
    ex = _privat_take(out, exs, [0])
    if ex is None:
        return
    if ex['failure'] or ex['response']['status'] != 200:
        _failure(out, ex, 'privat')
        return
    try:
        js = R.body_json(ex)
    except R.NotJson:
        _fail_not_json(out, 'privat')
        return
    if isinstance(js, dict) and js.get('status') == 'ERROR':
        cls, facts = rule_privat_api_error(js)
        _fail(out, cls, facts)
        return
    if not isinstance(js, dict) or not isinstance(js.get('balances'), list):
        _fail_not_json(out, 'privat', 'not-object')
        return
    flag = privat_exist_flag(js)
    if flag is None:
        rule_exist_flag_invalid(out, 'balance')
        return
    if flag:
        # баланси на кількох сторінках: межу довіри й валюту з однієї сторінки не визначити -- відмова, а не мовчання
        _fail(out, CLS_RETRY, {'Банк': BANK_NAMES['privat'], 'Вид': 'balance-next-page', 'Статус': 200, 'ОписаниеБанка': ''})
        return
    out.bank_boundary = rule_bank_boundary_privat(js['balances'], p)
    out.account_currency = privat_account_currency(js['balances'])
    if out.account_currency is None:
        # обмін вдався, а валюти рахунку з нього не визначено: фільтр валюти не застосовується, і про це окремий рядок (мовчки нічого не відкидаємо)
        out.diag('Предупреждение', 0, 'currency-unknown', None, Банк=BANK_NAMES['privat'])


def privat_account_currency(balances):
    """Валюта рахунку ПриватБанку за рядками `/balance` (`currency`, буквений код; run1: UAH 44 з 44). Параметрів читання з валютою немає й не буде, тому валюта
    береться з обміну, який конектор і так робить. Рядки з різними значеннями чи без значення -- валюта невідома (None), відступ 1 не застосовується."""
    vals = {C.trim(C.to_str(b.get('currency'))).upper() for b in balances if isinstance(b, dict)}
    return vals.pop() if len(vals) == 1 and next(iter(vals), '') else None


def foreign_currency(out, disabled, n, raw, ident):
    """Відступ 1 (валюта): операція в валюті, відмінній від валюти рахунку, -- рядок Предупреждение (рівень, як для чужого рахунку в точці читання), у Операции
    не йде; попередник такі рядки відкидав мовчки (регламентний фільтр валюти). -> True, якщо операцію відкинуто. Валюта рахунку невідома -- не застосовується."""
    ccy = C.trim(C.to_str(raw.get('CCY'))).upper()
    if 'dev1' in disabled or not out.account_currency or not ccy or ccy == out.account_currency:
        return False
    out.diag('Предупреждение', n, 'foreign-currency', 'dev1', Ид=ident, Код=ccy)
    return True


def _privat_items(out, items, p, disabled):
    def ident_of(it):
        return dev7_privat_identifier(it.raw, p, set()) if p.privat_id else ''

    def is_final(it):
        return _privat_state(it.raw) in ('r', 't')

    def is_reversal(it):
        return _privat_state(it.raw) == 't'

    # D36 п. 11 (d392bc4): період ПриватБанку -- день `DAT_OD`, у межах дня -- час `DATE_TIME_DAT_OD_TIM_P`; `НачалоПериода` і `КонецПериода` включні.
    # Операція поза періодом (але в днях запиту) відкидається мовчки, її `ПорядковыйНомер` лишається зайнятим. Рядок, що не читається, лишається
    # (скаже bad-date). `DAT_KL` не використовується (розходиться з `DAT_OD` у 4 операціях run1).
    def placement(it):
        try:
            moment = C.parse_1c_date(C.to_str(it.raw.get('DATE_TIME_DAT_OD_TIM_P')))
            od = _parse_day(C.to_str(it.raw.get('DAT_OD')))
        except ValueError:
            return None
        return od + timedelta(hours=moment.hour, minutes=moment.minute, seconds=moment.second)

    if p.reading_moment is not None:
        out.out_of_period = [it.n for it in items if placement(it) is not None and not (p.period_start <= placement(it) <= p.period_end)]
        items = [it for it in items if it.n not in set(out.out_of_period)]
    skip = rule_dedupe_by_id(out, items, ident_of, is_final, is_reversal)
    by_ident = {}
    for it in items:
        if it.n not in skip and is_final(it) and ident_of(it):         # пропущені тотожні дублі в пошук оригіналу не йдуть (дубль `t` -- не випадок (б))
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
            od_day = _parse_day(C.to_str(d.get('DAT_OD'))) if p.reading_moment is not None else None
        except ValueError:
            out.diag('Ошибка', n, 'bad-date', None, Ид=ident_for_diag)
            continue
        if od_day is not None and od_day != datetime(moment.year, moment.month, moment.day):
            out.diag('Предупреждение', n, 'date-mismatch', None, Ид=ident_for_diag, ДеньОД=od_day.strftime('%d.%m.%Y'),
                     ДеньВремени=moment.strftime('%d.%m.%Y'))
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
        if _norm_account(own) != _norm_account(p.account):
            if dev1_foreign_account(out, disabled, n, own, None) == 'silent':
                continue
        number = own
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
        if foreign_currency(out, disabled, n, d, ident_for_diag):       # відомий код, відмінний від валюти рахунку
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
def requested_limit(ex):
    """`limit` запиту виписки юросіб (немає -- 10, за замовчуванням документації corp-api)."""
    for k, v in R.query_pairs(ex):
        if k == 'limit' and v.isdigit():
            return int(v)
    return 10


def _mono(rec, p, out, disabled):
    corp = rec.bank == 'mono-corp'
    bank = rec.bank
    exs = list(rec.exchanges)
    if p.reading_moment is not None and p.period_end < p.period_start:
        # Точка читання (`СМП_ЧитателиВыписок`) відхиляє перевернутий період ДО конектора: запитів немає, клас «дія людини», рядок Предупреждение
        _fail(out, CLS_HUMAN, {}, 'period-reversed')
        out.rules.add('rule_period_reversed')
        return
    windows = C.request_windows(p, not corp)                      # межі запиту із запасом (71b3771, a90f7ea); період у майбутньому -- запитів немає
    if not windows:
        out.items = 0
        return                                                   # D36 п. 11: НачалоПериода пізніший за момент читання -- читати нічого
    if not corp and not p.old_cached_account_id:
        info = [e for e in exs if e['request']['path'] == C.FOP_CLIENT_INFO]
        if not info:
            raise RecordingMismatch('у записі ФОП немає client-info')
        e = info[0]
        use(out, e)
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
    # ФОП: відрізки ≤ 31 доби (кожен читається сторінками за D36 п. 11 -- як юросіб); юросіб: один відрізок, межі беруться із запиту
    seg = 0                                                  # поточний відрізок ФОП
    items, n, complete, i = [], 0, True, 0
    pages = 0                                                # прочитано сторінок виписки (для стелі)

    def stop_at_ceiling(boundary_unix):
        """Стеля сторінок: перед запитом, що продовжив би читання (межа `boundary_unix`)."""
        if pages >= C.page_ceiling(bank, p):
            rule_page_ceiling(out, bank, pages, n, kyiv.unix_to_local(boundary_unix))
            return True
        return False
    continuing = False                                       # запит продовження в тому самому відрізку ще попереду
    while i < len(stmts):
        ex = stmts[i]
        i += 1
        use(out, ex)
        acct, frm, to = R.statement_window(ex)
        if not continuing:
            if seg >= len(windows) or (frm, to) != windows[seg]:
                raise RecordingMismatch('перший запит відрізка запису (%d..%d) не збігається з межами запиту читання (%r)' % (frm, to, windows[seg:seg + 1]))
        continuing = False
        if ex['response'] and ex['response']['status'] == 429:
            # dev9: один повтор після 429 за заголовком (юросіб це вже мав, ФОП — ні)
            if 'dev9' in disabled and not corp:
                _failure(out, ex, bank)
                break
            ask = _retry_seconds(ex)
            if ask > C.PAUSE_CEILING_SECONDS:
                rule_pause_over_ceiling(out, ex, bank, ask)              # D36 п. 8 (a90f7ea): без сну й без повтору
                out.applied.add('dev9') if not corp else None           # ФОП: обробка 429 -- відступ dev9
                break
            if i < len(stmts):
                ex = stmts[i]
                i += 1
                use(out, ex)
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
        earliest_unix = None
        if any(isinstance(tx, dict) and isinstance(tx.get('time'), int) and (tx['time'] > to or tx['time'] < frm) for tx in page):
            # ПОЗА виміряним (запобіжник, D36 п. 8 і рішення за рев'ю задачі 4): відповідь виходить за межі запиту -- `time` > `to` або
            # `time` < `from` (`time` = `to` НЕ аномалія: виключність межі й дробові секунди не виміряно, повтори відкидає `id`).
            # Читання неповне, «повторити»; ЦЯ сторінка в конверт не береться, раніше прочитані лишаються.
            _fail(out, CLS_RETRY, {'Банк': BANK_NAMES[bank], 'Вид': 'out-of-bounds', 'Статус': 200, 'ОписаниеБанка': ''},
                  'out-of-bounds')
            out.rules.add('rule_response_out_of_bounds')
            break
        for tx in page:
            n += 1
            items.append(Item(n, tx, ex['seq']))
            try:
                tu = int(tx.get('time'))
            except (TypeError, ValueError):
                continue                                       # час не читається: рядок скаже bad-date у _mono_items, на курсор не впливає
            earliest_unix = tu if earliest_unix is None or tu < earliest_unix else earliest_unix
        pages += 1
        limit = requested_limit(ex) if corp else C.fop_page_limit(p)
        if len(page) < limit:                       # D36 п. 11: коротша за запитаний ліміт -- остання (ФОП: гіпотеза документації)
            if corp:
                break
            seg += 1                                # кінець відрізка ФОП: далі наступний відрізок
            if seg < len(windows) and stop_at_ceiling(windows[seg][1]):
                break
            continue
        # D36 п. 11 (44d22a1): продовження за часом знову охоплює секунду найранішої операції (`to` = time + 1; банк `to` не
        # включає); повтори відкидає дедуплікація за id. Запит продовження, що збігся б із поточним (вся повна сторінка в одній
        # секунді), -- застряглий курсор: «дія людини», читання йде далі з `to` = ця секунда (операцію з `time = to` банк не повертає). Для ФОП -- всередині відрізка.
        if earliest_unix is None:
            _fail(out, CLS_RETRY, {'Банк': BANK_NAMES[bank], 'Вид': 'page-without-time', 'Статус': 200, 'ОписаниеБанка': ''},
                  'page-without-time')
            out.rules.add('rule_end_of_read')
            break
        # межа продовження = Мин(найраніша time + 1, поточна `to`): межа ніколи не зростає, і застрягання (наступна межа = поточна)
        # визначається за будь-якої семантики `to`
        nxt = min(earliest_unix + 1, to)
        if nxt >= to:
            # застрягання: межа продовження = поточна (E >= U - 1). Крок після нього -- Мин(E, U - 1), строго менша за U за будь-якої
            # семантики `to`; неповними лишаються секунди між новою й поточною межею (одна, якщо межа виключна, до двох, якщо включна)
            rule_cursor_stuck(out, to, len(page))
            nxt = min(earliest_unix, to - 1)
        if nxt <= frm:
            if corp:
                break                                # читати нічого (межа дійшла до початку), без відмови
            seg += 1                                 # відрізок ФОП вичерпано, далі наступний
            if seg < len(windows) and stop_at_ceiling(windows[seg][1]):
                break
            continue
        if i < len(stmts) and R.statement_window(stmts[i])[2] != nxt:
            raise RecordingMismatch('запит продовження запису (to = %d) не збігається з правилом D36 п. 11 (to = %d)'
                                    % (R.statement_window(stmts[i])[2], nxt))
        if stop_at_ceiling(nxt):
            break
        continuing = True                            # запис кінчається до ознаки кінця -- скаже перевірка після циклу
    else:
        if continuing:
            # запис кінчається повною сторінкою, яку можна було продовжити: наступного обміну в записі немає, а ознаки кінця не було --
            # читання оракулом не закінчується, мовчки вважати його повним не можна
            raise RecordingMismatch('запис %s кінчається повною сторінкою без ознаки кінця й без наступного обміну' % bank)
        if not corp and seg < len(windows):
            raise RecordingMismatch('запис ФОП кінчається до останнього відрізка читання (%d з %d)' % (seg, len(windows)))
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
    use(out, ex)
    if ex['response'] and ex['response']['status'] == 429 and len(exs) > 1:
        ex = exs[1]                                         # один повтор після 429
        use(out, ex)
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

    # D36 п. 11 (71b3771, a90f7ea): `НачалоПериода` і `КонецПериода` -- включні моменти; операції поза ними, але в межах запиту, відкидаються
    # мовчки (без рядка діагностики), `ПорядковыйНомер` решти не змінюється. Час, що не читається, лишається (скаже bad-date).
    start_unix, end_unix = kyiv.local_to_unix(p.period_start), kyiv.local_to_unix(p.period_end)

    def in_period(it):
        t = it.raw.get('time') if isinstance(it.raw, dict) else None
        return p.reading_moment is None or not isinstance(t, int) or start_unix <= t <= end_unix

    out.out_of_period = [it.n for it in items if not in_period(it)]
    items = [it for it in items if in_period(it)]
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


# ====================================================================== ПУМБ (VegaNet), задача 2a Step 2
# Відступи від попередника (план 05б-2, «Відступи від попередника», ПУМБ 1-8) -- окремий реєстр: наявний тест вимагає, щоб кожен відступ 5а (`DEVIATIONS`) спрацьовував на синтетиці.
# Вимкнений відступ -- поведінка попередника (ПУМБ:342-385). Формат `operationDate` -- гіпотеза `dd.MM.yyyy HH:mm:ss`, інший -- явна відмова (`C.PumbDateFormat`).
PUMB_DEVIATIONS = {
    'pumb1': 'чужий рахунок (D30; фільтр конектора за рахунком: IBAN запитаного серед сторін або його number/altNumber серед номерів сторін) і чужа валюта -- діагностика, не операція й не мовчазний пропуск (валюта рахунку -- зі списку /account); `direction`, що не збігся з боком за запитаним рахунком, -- Ошибка рядка',
    'pumb3': 'непроведені й скасовані -- Предупреждение, у Операции лише PROCESSED; запит без фільтра станів; межа довіри не пізніша за першу неостаточну',
    'pumb4': 'повернення -- до виміру (а: окремий документ свого напряму, б: рядок Ошибка); без виміру нічого не вгадується',
    'pumb5': "призначення не обрізається; від'ємна чи нульова сума -- діагностика, не операція",
    'pumb6': 'ідентифікатор операції -- docId (виміряно: присутній 595 із 595, id майже завжди null); порожній docId -- Ошибка bad-identifier; стабільність -- run2',
    'pumb7': 'усі дати -- київський час з явним поясом; формат operationDate -- гіпотеза, інший формат -- відмова',
    'pumb8': 'без пагінації (Р4): запит за весь період, відповідь на порозі ділить період навпіл до доби (D36 п. 11); запит з pagingRequest оракул відхиляє явно',
    'pumb9': 'тип документа: рух коштів -- лише UAH і CUR_ADV (білий список); відомі «не рух» (STM, CUR, CUR_C, CUR_S) -- не операція і без Предупреждение; будь-який інший тип (зокрема порожній) -- відмова всього читання, «дія людини»; попередник вантажив усе, що віддав банк',
}
# Тип документа searcher (виміряно run4, 60 днів: перебір комбінацій типів проти зміни щоденного залишку STM): рух коштів по рахунку -- UAH (гривня) і CUR_ADV (авізо валюти);
# STM -- щоденний запис залишку; CUR, CUR_C, CUR_S -- заявки/доручення, кожна має пару на гривневому рахунку під тим самим IBAN, а рух валюти банк віддає авізо CUR_ADV.
# Решта типів -- невідомі: читання зупиняється людиною (див. `rule_unknown_doc_type`), а не мовчки пропускає й не вантажить.
PUMB_MOVEMENT_TYPES = frozenset({'UAH', 'CUR_ADV'})
PUMB_NONMOVEMENT_TYPES = frozenset({'STM', 'CUR', 'CUR_C', 'CUR_S'})
PUMB_CANCELLED = frozenset({'REJECTED', 'REJECTED_BY_ACCO', 'REJECTED_BY_OPER', 'SYSTEM_ERROR'})
PUMB_NONFINAL = frozenset({'INPUT', 'ACCEPTING', 'ACCEPTED', 'READY_TO_SEND', 'SENDING', 'TAKE_IN', 'ROUTED', 'UPLOADED', 'ACCEPTED_BY_ACCO',
                           'ACCEPTED_BY_OPER', 'SENT_TO_EPS'})          # стани за swagger (enum VeganetDocumentItem.state); PROCESSED -- проведений
PUMB_PURPOSE_OLD_LIMIT = 1024                                           # ПУМБ:299 -- колонка НазначениеПлатежа (1024); з коду, не виміряно


class PaginationUnmeasured(ValueError):
    """ПУМБ: запит із `pagingRequest` -- конектор пагінації не використовує (Р4), оракул такий запис явно відхиляє, його модель не вгадується."""


def pumb1_foreign_currency(out, disabled, n, doc_code, acc_code, ident):
    """Операція валюти, відмінної від валюти рахунку (зі списку /account): Ошибка рядка, у Операции не йде. -> True, якщо відкинуто."""
    if 'pumb1' in disabled or not doc_code or not acc_code or doc_code == acc_code:
        return False
    out.diag('Ошибка', n, 'foreign-currency', 'pumb1', Ид=ident, Код=doc_code)
    out.applied.add('pumb1')
    return True


def pumb3_state(out, disabled, n, state, moment, ident):
    """Стан документа: PROCESSED -- операція; скасований (`REJECTED*`, `SYSTEM_ERROR`) і неостаточний -- рядок Предупреждение (неостаточний утримує межу довіри);
    невідомий -- Ошибка. Вимкнено -- попередник фільтрував PROCESSED на боці банку: решта зникає без сліду. -> 'emit' | 'handled' | 'silent'."""
    if state == 'PROCESSED':
        return 'emit'
    if 'pumb3' in disabled:
        out.silent += 1
        return 'silent'
    if state in PUMB_CANCELLED:
        out.diag('Предупреждение', n, 'cancelled', 'pumb3', Состояние=state, Ид=ident, Момент=C.iso(moment))
    elif state in PUMB_NONFINAL:
        out.diag('Предупреждение', n, 'nonfinal', 'pumb3', Состояние=state, Ид=ident, Момент=C.iso(moment))
        out.nonfinal.append(moment)
    else:
        rule_unknown_state(out, n, state, ident)
        out.applied.add('pumb3')                                 # невідомий стан -- теж слід відступу (вимкнений: мовчазне відкидання попередника)
        return 'handled'
    out.applied.add('pumb3')
    return 'handled'


def pumb4_returns(out, disabled, n, doc, ident):
    """Повернення: ДО ВИМІРУ (випадок (а) окремий документ свого напряму з ключем != ключ оригіналу; випадок (б) -- рядок Ошибка до правила 5б). Ознак повернення в
    полях swagger немає, тож оракул нічого не вгадує: документ іде як звичайний, еталон несе залежність `ВозвратПУМБ`. -> 'emit'."""
    return 'emit'


def pumb5_amount(out, disabled, n, raw, ident):
    """Сума документа: від'ємна, нульова чи нерозбірна -- Ошибка `bad-amount`, не операція (D28). Вимкнено -- попередник брав модуль (КБ). -> Decimal | None."""
    try:
        amount = C.number(raw)
    except ValueError:
        out.diag('Ошибка', n, 'bad-amount', None, Ид=ident)
        return None
    if amount <= 0 and 'pumb5' not in disabled:
        out.diag('Ошибка', n, 'bad-amount', 'pumb5', Ид=ident)
        out.applied.add('pumb5')
        return None
    return abs(amount)


def pumb5_purpose(out, disabled, text):
    """Призначення не обрізається (довжину перевіряє платформа). Вимкнено -- як колонка попередника (1024)."""
    if 'pumb5' in disabled and len(text) > PUMB_PURPOSE_OLD_LIMIT:
        return text[:PUMB_PURPOSE_OLD_LIMIT]
    if len(text) > PUMB_PURPOSE_OLD_LIMIT:
        out.applied.add('pumb5')
    return text


def pumb6_identifier(out, disabled, doc):
    """Ідентифікатор: `docId` (виміряно, run1b: присутній 595 із 595 входжень; `id` -- null у 593, непорожній у 2 і != `docId`, тож основним не є). Порожній `docId` (null, відсутній, '')
    -> порожній ідентифікатор -> `rule_identifier_length` дає Ошибка bad-identifier. Стабільність між прогонами -- run2. -> (НомерДокумента, ИдентификаторОперации);
    вимкнено -- попередник СМП_ИДТранзакцииБанка не писав: ідентифікатор операції порожній."""
    num = C.to_str(doc.get('docId'))
    if 'pumb6' in disabled:
        return num, ''
    if num:
        out.applied.add('pumb6')
    return num, num


def pumb7_local_time(text):
    """Київський місцевий час з явним поясом (платформа подає зсув сама); формат лише `dd.MM.yyyy HH:mm:ss`, інший -- `PumbDateFormat`."""
    return C.pumb_date(text)


def pumb8_pagination(searches):
    """Без пагінації (Р4): оракул моделює читання з кількома запитами `searcher` (ділення навпіл), але явно відхиляє запит із `pagingRequest` -- конектор його не шле
    (`readings.pumb_refusal` відсіює такі читання заздалегідь)."""
    from . import readings as RD
    why = RD.pumb_refusal(searches)
    if 'pagingRequest' in why:
        raise PaginationUnmeasured(why)


PUMB_IDENTIFIER_MAX = 50           # D28: довжина ідентифікатора операції


def rule_identifier_length(out, n, ident):
    """Контрактне правило D28 (не відступ): ідентифікатор операції -- від 1 до 50 символів; порожній чи довший -- операція не подається, рядок `Ошибка` `bad-identifier`
    (довжина без значення: ідентифікатор довгого значення в діагностику не йде). Вимкнений відступ pumb6 дає порожній ідентифікатор за побудовою, правило тоді не діє. -> True, якщо відхилено."""
    if 1 <= len(ident) <= PUMB_IDENTIFIER_MAX:
        return False
    out.diag('Ошибка', n, 'bad-identifier', None, Количество=len(ident))
    out.rules.add('rule_identifier_length')
    return True


def rule_no_iban(out, n, ident):
    """Контрактне правило (Р-д, не відступ): документ без IBAN ОБОХ сторін -- чий це рух, не встановити (рахунок із `accountId` запиту не виводиться): операція не подається,
    рядок `Ошибка` `no-iban`; діагностика несе лише ідентифікатор. -> True (завжди відхилено)."""
    out.diag('Ошибка', n, 'no-iban', None, Ид=ident)
    out.rules.add('rule_no_iban')
    return True


def pumb_out_of_bounds(search, docs):
    """Аномалія меж (D36 п. 11): `operationDate` документа раніше за `fromDate` або пізніше за `toDate` ЗАПИТУ (межі -- з тіла запиту searcher, той самий строгий формат).
    Межі запиту -- цілі доби (`C.pumb_request_bounds`: 00:00:00 першої і 23:59:59 останньої), тож аномалія -- лише документ, ДЕНЬ `operationDate` якого поза днями запиту; документ тієї ж доби, але поза
    періодом (піддобою), -- не аномалія, а мовчазне відкидання фільтром конектора (див. `_pumb`)."""
    body = json.loads(R.request_body_text(search))
    lo, hi = C.pumb_date(body.get('fromDate')), C.pumb_date(body.get('toDate'))
    return any(isinstance(r, dict) and not (lo <= C.pumb_date(r.get('operationDate')) <= hi) for r in docs)


def rule_day_at_threshold(out, day, count):
    """Контрактне правило (D36 п. 11, Р4): доба, що й сама дала відповідь не менше за поріг (`C.PUMB_RESPONSE_THRESHOLD`), -- читання неповне, «дія людини» (повтор не зменшить
    відповідь); діагностика називає добу (дата, не значення поля) і кількість документів і радить звузити період (формулювання -- текст точки читання); межа довіри -- за D36 п. 10
    (відмова -> `НачалоПериода`), прочитане раніше лишається."""
    _fail(out, CLS_HUMAN, {'Банк': BANK_NAMES['pumb'], 'Вид': 'day-at-threshold', 'Статус': 200, 'ОписаниеБанка': '', 'Сутки': day.strftime('%d.%m.%Y'), 'Документов': count,
                           'Порог': C.PUMB_RESPONSE_THRESHOLD}, 'day-at-threshold')
    out.rules.add('rule_day_at_threshold')


def rule_unknown_doc_type(out, docs, window):
    """Контрактне правило (рішення консультанта після run4): документ searcher невідомого типу (не з `PUMB_MOVEMENT_TYPES` і не з `PUMB_NONMOVEMENT_TYPES`; порожній тип -- теж невідомий) --
    відмова ВСЬОГО читання, «дія людини» (повтор не допоможе: людина вирішує, чи це рух коштів), операції цієї відповіді в конверт не йдуть. Діагностика називає ПЕРШИЙ невідомий тип у порядку документів
    відповіді, кількість документів цього типу в ній і найраніший день `operationDate` серед них (факти: `Значение` -- тип, `Документов`, `Сутки`); інші невідомі типи побачить людина після виправлення.
    Розглядаються лише документи в періоді (поза ним -- мовчазний відсів, як і для решти правил). -> True, якщо відмову записано."""
    first, count, day = None, 0, None
    for r in docs:
        if not isinstance(r, dict):
            continue
        t = C.to_str(r.get('type'))
        if t in PUMB_MOVEMENT_TYPES or t in PUMB_NONMOVEMENT_TYPES:
            continue
        moment = pumb7_local_time(r.get('operationDate'))
        if window is not None and not (window[0] <= moment <= window[1]):
            continue
        if first is None:
            first = t
        if t == first:
            count += 1
            day = moment if day is None else min(day, moment)
    if first is None:
        return False
    _fail(out, CLS_HUMAN, {'Банк': BANK_NAMES['pumb'], 'Вид': 'unknown-doc-type', 'Статус': 200, 'ОписаниеБанка': '', 'Значение': first, 'Документов': count,
                           'Сутки': day.strftime('%d.%m.%Y')}, 'unknown-doc-type')
    out.rules.add('rule_unknown_doc_type')
    return True


def pumb_direction_conflict(out, n, doc, outgoing, ident):
    """Напрям за ознакою банку проти боку, визначеного за запитаним рахунком (рішення консультанта, A9): `direction` не збігся з боком -- Ошибка `direction-mismatch` (хибний знак руху грошей), не операція;
    значення поза OUTBOUND/INBOUND -- `unknown-direction`; відсутній `direction` -- не розбіжність (бік уже визначено рахунком). Переказ між своїми рахунками: бік -- за запитаним, direction мусить збігтися. -> True, якщо відхилено."""
    d = doc.get('direction')
    if d is None or d == '':
        return False
    if d not in ('OUTBOUND', 'INBOUND'):
        rule_unknown_direction(out, n, C.to_str(d), ident)
        return True
    if (d == 'OUTBOUND') != outgoing:
        out.diag('Ошибка', n, 'direction-mismatch', None, Ид=ident)
        out.rules.add('rule_direction_mismatch')
        return True
    return False


def pumb1_account_side(own, mine, doc):
    """Фільтр конектора за рахунком (відступ pumb1/D30): чи документ нашого рахунку і з якого боку. Наш -- запитаний IBAN серед `senderIBAN`/`correspondentIBAN`, АБО номер запитаного рахунку
    (`number`/`altNumber` зі списку /account) серед `senderAccountNumber`/`correspondentAccountNumber` (виміряно run1b: 1 CUR без IBAN відправника з номером = запитаному). IBAN старший за номер.
    -> 'out' (рахунок -- відправник) | 'in' (одержувач) | None (чужий)."""
    snd, rcv = C.to_str(doc.get('senderIBAN')), C.to_str(doc.get('correspondentIBAN'))
    if snd == own:
        return 'out'
    if rcv == own:
        return 'in'
    nums = {C.trim(C.to_str(mine.get(k))) for k in ('number', 'altNumber')} - {''}
    if C.trim(C.to_str(doc.get('senderAccountNumber'))) in nums:
        return 'out'
    if C.trim(C.to_str(doc.get('correspondentAccountNumber'))) in nums:
        return 'in'
    return None


def pumb_select_account(out, accounts, p):
    """Рахунок банку за запитаним IBAN (D36 п. 2, 8 @ 21f0ab0). Під IBAN може бути кілька рахунків у різних валютах (виміряно run2: 14 рахунків, 11 IBAN). Один -- беремо його (поле
    `ВалютаСчета` не читається); кілька -- за парою (IBAN, числовий код валюти `/account`) з `Параметры.ВалютаСчета`; немає IBAN -- `account-not-found`; поле порожнє / пари немає /
    пара неоднозначна -- `account-ambiguous`, «дія людини» ДО запиту виписки. Обидва випадки -- один клас «рахунку немає в банку». -> рахунок чи None (відмова записана)."""
    same = [a for a in accounts if isinstance(a, dict) and a.get('iban') == p.account]
    if not same:
        _fail(out, CLS_HUMAN, {'Банк': BANK_NAMES['pumb'], 'Количество': 0}, 'account-not-found')       # факт `Количество` = 0: Т1 відрізняє «немає за IBAN» від «кілька під IBAN»
        return None
    if len(same) == 1:
        return same[0]
    want = C.to_str(p.account_currency_code)
    by_pair = [a for a in same if want and C.numeric_currency(C.to_str(a.get('currency'))) == want]
    if len(by_pair) == 1:
        return by_pair[0]
    facts = {'Банк': BANK_NAMES['pumb'], 'Количество': len(same)}                                       # скільки рахунків під IBAN
    if want:
        facts['Код'] = want                                                                          # числовий код валюти, який передано (порожнього не передано -- факту немає)
    _fail(out, CLS_HUMAN, facts, 'account-ambiguous')
    return None


def _pumb(rec, p, out, disabled):
    bank = 'pumb'
    exs = list(rec.exchanges)
    if p.reading_moment is not None and p.period_end < p.period_start:
        _fail(out, CLS_HUMAN, {}, 'period-reversed')             # D36 п. 11: перевернутий період відхиляє точка читання до конектора, запитів немає
        out.rules.add('rule_period_reversed')
        return
    if p.reading_moment is not None and p.period_start > kyiv.to_local(p.reading_moment):
        out.items = 0                                            # D36 п. 11: НачалоПериода пізніший за момент читання -- запитів немає, порожнє повне читання
        return
    searches = [e for e in exs if e['request']['path'].endswith('/document/searcher')]
    if not exs:
        raise RecordingMismatch('у записі ПУМБ немає обмінів')
    if searches:
        pumb8_pagination(searches)
    auth = exs[0]
    use(out, auth)
    if auth['failure'] or auth['response']['status'] != 200:
        _failure(out, auth, bank, p.credentials)                                # автентифікація: 4xx -- дія людини, 5xx/збій -- повторити; запис може кінчатися тут (searcher не потрібен)
        return
    if len(exs) < 2:
        raise RecordingMismatch('у записі ПУМБ немає списку рахунків')
    account = exs[1]
    use(out, account)
    if account['failure'] or account['response']['status'] != 200:
        _failure(out, account, bank, p.credentials)
        return
    try:
        accounts = R.body_json(account)
    except R.NotJson:
        accounts = None
    if not isinstance(accounts, list):
        _fail_not_json(out, bank)
        return
    mine = pumb_select_account(out, accounts, p)
    if mine is None:
        return
    if not searches:
        raise RecordingMismatch('у записі ПУМБ немає запиту searcher')
    acc_ccy = C.to_str(mine.get('currency'))
    moment_local = kyiv.to_local(p.reading_moment) if p.reading_moment is not None else None
    top = min(p.period_end, moment_local) if moment_local is not None else p.period_end
    filtered = p.reading_moment is not None or len(searches) > 1       # відсів за періодом (піддобу): запас меж запиту й суміжні запити дають документи поза ним
    n = 0                                                              # ПорядковыйНомер -- наскрізний за всіма прийнятими відповідями
    stack, used = [(p.period_start, top)], 0                           # обхід навпіл: спершу ранішня половина (порядок запитів у записі)
    try:
        while stack:
            lo, hi = stack.pop()
            if used >= len(searches):
                raise RecordingMismatch('у записі ПУМБ немає запиту searcher для піддобу (запис кінчається раніше за модель ділення)')
            search = searches[used]
            used += 1
            use(out, search)
            if used > 1 or p.strict_first_request:                         # КОЖЕН запит (і перший) -- межі цілими добами і форма тіла конектора; перший запит запису у формі рекордера (до run2) відхиляється
                body = json.loads(R.request_body_text(search))
                want = C.pumb_request_bounds(lo, hi)
                if (C.pumb_date(body.get('fromDate')), C.pumb_date(body.get('toDate'))) != want or set(body) != {'fromDate', 'toDate', 'documentAccounts'}:
                    raise RecordingMismatch(PUMB_RECORDER_FORM if used == 1 else 'межі запиту searcher не збігаються з половиною періоду')
            if search['failure'] or search['response']['status'] != 200:
                _failure(out, search, bank, p.credentials)                          # 429 тут -- без повтору: модель пауз зі Step 3
                return
            try:
                docs = R.body_json(search)
            except R.NotJson:
                docs = None
            if not isinstance(docs, list):
                _fail_not_json(out, bank)
                return
            if pumb_out_of_bounds(search, docs):
                _fail(out, CLS_RETRY, {'Банк': BANK_NAMES[bank], 'Вид': 'out-of-bounds', 'Статус': 200, 'ОписаниеБанка': ''}, 'out-of-bounds')
                out.rules.add('rule_response_out_of_bounds')              # D36 п. 11: аномалія меж -- «повторити», ЦЯ сторінка в конверт не береться
                out.items += len(docs)
                return
            if len(docs) >= C.PUMB_RESPONSE_THRESHOLD:                    # D36 п. 11, Р4: відповідь на порозі -- ділення навпіл (відповідь не береться, половини перечитують її)
                halves = C.pumb_halves(lo, hi)
                if halves is None:
                    rule_day_at_threshold(out, lo, len(docs))
                    return
                out.rules.add('rule_split_at_threshold')
                stack.extend(reversed(halves))
                continue
            if 'pumb9' not in disabled and rule_unknown_doc_type(out, docs, (lo, hi) if filtered else None):
                out.items += len(docs)
                out.applied.add('pumb9')
                return                                                     # відмова всього читання: операцій цієї відповіді в конверті немає
            out.items += len(docs)
            for r in docs:
                n += 1
                if not isinstance(r, dict):
                    raise ValueError("елемент відповіді ПУМБ не є об'єктом")
                _pumb_doc(out, p, disabled, n, r, mine, acc_ccy, (lo, hi) if filtered else None)
        if used < len(searches):
            raise RecordingMismatch('у записі ПУМБ більше запитів searcher, ніж робить модель читання')
    finally:                                                           # рядок на читання (з кількістю) -- і коли читання зупинилось відмовою: прочитане лишається
        if out.foreign_docs:
            out.diag('Предупреждение', 0, 'foreign-account', 'pumb1', Количество=len(out.foreign_docs))   # рахунок сторін не збігся ні з IBAN, ні з номером запитаного рахунку; текст -- точка читання


def _pumb_doc(out, p, disabled, n, r, mine, acc_ccy, window):
    moment = pumb7_local_time(r.get('operationDate'))
    if window is not None and not (window[0] <= moment <= window[1]):
        out.out_of_period.append(n)                              # D36 п. 11: поза [Начало, Конец] (піддобу), але в межах запиту -- відкидається мовчки
        return
    if C.to_str(r.get('type')) in PUMB_NONMOVEMENT_TYPES and 'pumb9' not in disabled:
        out.skipped_nonmove.append(n)                            # відомий «не рух» (STM -- щоденний запис залишку; CUR, CUR_C, CUR_S -- заявки; виміряно run4): не операція і без Предупреждение
        out.applied.add('pumb9')
        return
    number, ident = pumb6_identifier(out, disabled, r)
    if pumb3_state(out, disabled, n, C.to_str(r.get('state')), moment, number) != 'emit':
        return
    pumb4_returns(out, disabled, n, r, number)
    if 'pumb6' not in disabled and rule_identifier_length(out, n, ident):
        return
    snd, rcv = C.to_str(r.get('senderIBAN')), C.to_str(r.get('correspondentIBAN'))
    side = pumb1_account_side(p.account, mine, r)
    if side is None:
        if not snd and not rcv:
            rule_no_iban(out, n, number)                         # IBAN обох сторін немає й номер рахунку не збігся: чий це рух, не встановити
            return
        if 'pumb1' in disabled:
            side = 'out' if r.get('direction') == 'OUTBOUND' else 'in'     # попередник рахунок не звіряв: усе, що банк віддав, -- наше
        else:
            out.foreign_docs.append(n)
            out.applied.add('pumb1')
            return
    outgoing = side == 'out'
    own = p.account
    if pumb_direction_conflict(out, n, r, outgoing, number):
        return
    doc_ccy = C.numeric_currency(C.to_str(r.get('currencyCode')))
    if doc_ccy is None:                                                 # літерний код поза довідником ISO: ніколи не гривня (D4b)
        out.diag('Ошибка', n, 'unknown-currency', None, Ид=number, Код=C.to_str(r.get('currencyCode')))
        return
    if pumb1_foreign_currency(out, disabled, n, doc_ccy, C.numeric_currency(acc_ccy), number):
        return
    amount = pumb5_amount(out, disabled, n, r.get('amount'), number)
    if amount is None:
        return
    purpose = pumb5_purpose(out, disabled, C.to_str(r.get('description')))
    cside = 'correspondent' if outgoing else 'sender'
    out.ops.append({
        'ПорядковыйНомер': n, 'НомерСчета': own, 'Валюта': doc_ccy, 'ДатаОперации': C.iso(moment), 'НомерДокумента': number,
        'ДатаДокумента': C.iso_day(moment), 'Сумма': C.amount_str(amount), 'Направление': 'Списано' if outgoing else 'Поступило',
        'ИдентификаторОперации': ident, 'КонтрагентНаименование': C.to_str(r.get(cside + 'Name')),
        'КонтрагентНомерСчета': rcv if outgoing else snd, 'КонтрагентКод': C.to_str(r.get(cside + 'TaxId')),
        'КонтрагентМФО': C.to_str(r.get(cside + 'BankMfo')), 'НазначениеПлатежа': purpose})


def _mono_currency(v):
    """Числовий `currencyCode` monobank (980 / '980') -> три цифри через ту саму таблицю, що `ЧисловойКодВалюты`;
    немає поля -> '' (валюта рахунку); невідомий код -> None."""
    if v is None:
        return ''
    s = C.to_str(v).strip()
    return C.numeric_currency(s.zfill(3) if s.isdigit() else s)


def ops_equal_ignoring_order_within_moment(a, b):
    """Порівняння операцій двох читань одного періоду без залежності від порядку всередині однакового моменту.
    run1 (журнал 05а, пункт 8): склейка сторінок ПриватБанку (`limit=5`) і єдиний запит розходяться у 2 з 87 позицій -- пари
    однакового `DATE_TIME_DAT_OD_TIM_P` (до хвилини). Сам еталон одного запису ФІКСУЄ порядок записаних сторінок
    (`ПорядковыйНомер` = позиція у відповідях: відтворення дає конекторові ті самі сторінки в тому ж порядку); ця функція --
    для порівняння читань з різним розміром сторінки. `ПорядковыйНомер` при цьому не порівнюється."""
    def norm(ops):
        groups, order = {}, []
        for o in ops:
            m = o['ДатаОперации']
            if m not in groups:
                groups[m] = []
                order.append(m)
            groups[m].append(json.dumps({k: v for k, v in o.items() if k != 'ПорядковыйНомер'}, sort_keys=True, ensure_ascii=False))
        return [(m, sorted(groups[m])) for m in order]
    return norm(a) == norm(b)


# ====================================================================== перевірка запитів запису
def expected_windows(p, bank):
    """Відрізки читання, які зробив би конектор: ФОП — до 31 доби (місцевий час), юросіб — один."""
    return C.request_windows(p, bank == 'mono-fop')


def verify_requests(rec, p):
    """Чи відрізки запису збігаються з тим, що зробив би конектор: `from` першого запиту кожного відрізка й `to` першого
    відрізка (далі `to` зсувається за сторінками). -> перелік розбіжностей. Для синтетики — самоперевірка генератора;
    для справжніх записів — лише інформація (рекордер міг ходити інакше)."""
    if rec.bank == 'privat':
        return verify_privat_requests(rec, p)
    if not C.statement_exchanges(rec):
        return []
    want = expected_windows(p, rec.bank)
    starts = []
    for e in C.statement_exchanges(rec):
        w = R.statement_window(e)
        if w[1] > w[2]:                      # навмисно хибний період (помилка 400 «початок пізніше за кінець»)
            return []
        if not starts or starts[-1][0] != w[1]:
            starts.append((w[1], w[2]))
    problems = []
    if [s[0] for s in starts] != [w[0] for w in want]:
        problems.append('from відрізків: запис %r, очікувано %r' % ([s[0] for s in starts], [w[0] for w in want]))
    elif starts and starts[0][1] != want[0][1]:
        problems.append('to першого відрізка: запис %r, очікувано %r' % (starts[0][1], want[0][1]))
    return problems


def verify_privat_requests(rec, p):
    """Запити запису ПриватБанку проти правил конектора (D36 п. 11, d392bc4), незалежно від генератора: `acc` -- 14 останніх цифр рахунку; `startDate` і
    `endDate` -- дні `C.privat_days`; `limit` -- ціле від 1 до робочого (шов розміру сторінки), однаковий у всіх запитах транзакцій читання; `followId` першого
    запиту немає, наступного -- `next_page_id` попередньої сторінки (повтор після 429 -- той самий запит); `/balance` -- ті самі `acc` і дати, без `limit`;
    `/settings` -- без запиту. Період навпаки й цілком майбутній -- запитів немає. -> перелік розбіжностей."""
    days = C.privat_days(p)
    if days is None:
        return ['запити є, а період навпаки чи цілком у майбутньому: запитів бути не мусить'] if rec.exchanges else []
    problems = []
    dates = {'startDate': days[0].strftime('%d-%m-%Y'), 'endDate': days[1].strftime('%d-%m-%Y')}
    limits, follow, prev, prev_query = set(), None, None, None
    for e in rec.exchanges:
        path, q = e['request']['path'], dict(R.query_pairs(e))
        if path == C.PRIVAT_SETTINGS_PATH:
            if q:
                problems.append('/settings несе запит')
            continue
        if q.get('acc') != p.account[-14:]:
            problems.append('%s: acc запису не збігається з 14 останніми цифрами рахунку читання' % path.rsplit('/', 1)[-1])
        for k, v in dates.items():
            if q.get(k) != v:
                problems.append('%s: %s запису (%s) не збігається з днем читання (%s)' % (path.rsplit('/', 1)[-1], k, q.get(k), v))
        if path == C.PRIVAT_BALANCE_PATH:
            if set(q) != {'acc', 'startDate', 'endDate'}:
                problems.append('/balance: параметри запиту %s' % sorted(q))
            continue
        if q.get('limit', '').isdigit() and 1 <= int(q['limit']) <= C.PRIVAT_WORKING_LIMIT:
            limits.add(q['limit'])
        else:
            problems.append('транзакції: limit %r поза 1..%d' % (q.get('limit'), C.PRIVAT_WORKING_LIMIT))
        retry = e['request'] and prev_query is not None and q == prev_query and prev is not None and prev['response'] and prev['response']['status'] == 429
        if not retry and q.get('followId') != follow:
            problems.append('транзакції: followId запису (%s) не збігається з next_page_id попередньої сторінки (%s)' % (q.get('followId'), follow))
        prev, prev_query = e, q
        try:
            js = R.body_json(e)
            follow = js.get('next_page_id') if isinstance(js, dict) and e['response'] and e['response']['status'] == 200 else follow
        except R.NotJson:
            pass
    if len(limits) > 1:
        problems.append('limit змінюється посеред читання: %s' % sorted(limits))
    return problems
