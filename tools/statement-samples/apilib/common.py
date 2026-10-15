# -*- coding: utf-8 -*-
"""Спільне для обох режимів оракула: параметри читання, 1С-подібні перетворення, обхід сторінок запису.

Перетворення відтворюють виміряну поведінку платформи (задача 0 плану 05а, `docs/superpowers/plans/
2026-10-15-smb-import-platform-05a-runs.md`): `Дата("07.01.2020 2:58:00")`, `Формат(x, "ЧГ=0")`, `Число("12,5")`,
`Строка(Неопределено)` = порожній рядок. Жодне значення поля тут не друкується."""
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from . import kyiv, recording as rec_mod

BANKS = ('privat', 'mono-fop', 'mono-corp')
PRIVAT_PATH = '/api/statements/transactions'
PRIVAT_SETTINGS_PATH = '/api/statements/settings'
FOP_CLIENT_INFO = '/personal/client-info'
PAGE_SIZE_MONO = 500            # РазмерСтраницы() обох monobank-модулів (MF:479-481, MU:537-539)
FOP_WINDOW_SECONDS = 2678400    # ДлинаОтрезкаСекунд() (MF:472-476)
UNICODE_SPACES = ' \t\r\n\xa0'


@dataclass
class Params:
    """Параметри читання (як у `Параметры` контракту) і режимів оракула.

    `account` — наш рахунок, як його передає платформа (IBAN). `period_*` — київський місцевий час.
    Поля `old_*` і `privat_id` стосуються лише відповідного режиму й названі в еталоні як залежності."""
    account: str
    period_start: datetime
    period_end: datetime
    # --- режим «стара обробка»
    old_account_format: str = '14'              # '14' | 'iban': як лежить НомерСчета рахунку ПриватБанку в базі
    old_account_obsolete: str = ''              # НомерСчетаУстаревший (PB:427-428); порожній — не заповнений
    old_account_currency: object = None         # ВалютаДенежныхСредств.Код; None — не заповнена
    old_session_tz: str = 'Europe/Kiev'         # пояс сеансу, яким рахує `МестноеВремя` попередник monobank
    old_currency_catalog: dict = field(default_factory=lambda: {'USD': '840', 'EUR': '978'})   # довідник Валюты
    old_cached_account_id: bool = False         # ИД облікового запису заповнений: client-info не кличеться (MF:373-376)
    # --- режим «очікуване»
    privat_id: object = 'REF+REFN'              # вибір D36 п. 6 (до виміру): 'REF+REFN' | 'TECHNICAL_TRANSACTION_ID' | 'ID' | None
    fop_pause_after_client_info: int = 60       # секунди; D36 п. 9 (до виміру: чи дає банк виписку одразу)
    # тлумачення полів банківської межі (D36 п. 10); до виміру задачі 1 — те, що дає ранішу межу
    privat_final_date_inclusive: bool = False   # чи остаточний сам день date_final_statement (False: ні)
    corp_absent_day_is_final: bool = False      # чи остаточний день, якого немає у відповіді balances (False: ні)

    def to_json(self):
        return {'НомерСчета': self.account, 'НачалоПериода': iso(self.period_start), 'КонецПериода': iso(self.period_end)}


# ---------------------------------------------------------------------- рядки / числа / дати
def iso(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%S') if dt else None


def iso_day(dt):
    return dt.strftime('%Y-%m-%d') if dt else None


def trim(s):
    """СокрЛП: незначущі символи (пробіл, TAB, переноси, нерозривний пробіл) з обох боків."""
    return s.strip(UNICODE_SPACES)


def to_str(v):
    """`Строка(x)` для значення з JSON: відсутнє / null -> порожній рядок (виміряно: не слово «Неопределено»);
    число — без розділювачів груп (ідентифікатори й коди, на відміну від `Строка(Число)`, не форматуються тут:
    читач кладе рядки, як у джерелі)."""
    if v is None:
        return ''
    if isinstance(v, bool):
        return 'Да' if v else 'Нет'
    if isinstance(v, Decimal):
        return format(v, 'f')
    return str(v)


_DATE_RX = re.compile(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})(?: (\d{1,2}):(\d{2}):(\d{2}))?$')


def parse_1c_date(s):
    """`Дата("dd.MM.yyyy HH:mm:ss")` (виміряно: приймає і «2:58:00»); лише день без часу, порожнє й сміття — виняток."""
    m = _DATE_RX.match(s or '')
    if not m or m.group(4) is None:
        raise ValueError('Преобразование значения к типу Дата не может быть выполнено')
    d, mo, y, h, mi, se = (int(g) for g in m.groups())
    try:
        return datetime(y, mo, d, h, mi, se)
    except ValueError:
        raise ValueError('Преобразование значения к типу Дата не может быть выполнено')


def number(s):
    """`Число(строка)`: кома чи крапка як роздільник (виміряно: «12,5» і «0.01»); сміття — виняток."""
    t = trim(to_str(s)).replace(' ', '').replace(',', '.')
    try:
        return Decimal(t)
    except InvalidOperation:
        raise ValueError('Значение не может быть преобразовано в число')


def chg0(d):
    """`Формат(x, "ЧГ=0")`: без розділювачів груп, десятковий розділювач — кома, нулі справа не пишуться."""
    s = format(Decimal(d).normalize(), 'f')
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s.replace('.', ',')


def money(d):
    return '%.2f' % d if isinstance(d, Decimal) else str(d)


def amount_str(d):
    """Сума з двома знаками (колонка `Сумма` (15,2))."""
    return format(Decimal(d).quantize(Decimal('0.01')), 'f')


# ---------------------------------------------------------------------- час
def session_local(sec, tz):
    """`МестноеВремя(Дата("19700101") + sec)` попередника: пояс сеансу `tz` ('Europe/Kiev' або 'UTC')."""
    if tz == 'Europe/Kiev':
        return kyiv.unix_to_local(sec)
    if tz == 'UTC':
        return kyiv.unix_to_utc(sec)
    raise ValueError('невідомий пояс сеансу %r: оракул знає лише Europe/Kiev і UTC' % (tz,))


# ---------------------------------------------------------------------- обхід запису
def exchanges_for(rec, path):
    return [e for e in rec.exchanges if e['request']['path'] == path]


def statement_exchanges(rec):
    return [e for e in rec.exchanges if rec_mod.statement_window(e)]


def fop_windows(start, end):
    """Відрізки читання monobank ФОП: ≤ 31 доба, місцевий час (MF:273-278, 351)."""
    out, cur = [], start
    while cur < end:
        nxt = min(cur + timedelta(seconds=FOP_WINDOW_SECONDS), end)
        out.append((cur, nxt))
        cur = nxt
    return out


def error_description(ex):
    """Опис помилки від банку з тіла: `errorDescription` (monobank), `message` (ПриватБанк); немає — порожньо."""
    try:
        js = rec_mod.body_json(ex)
    except rec_mod.NotJson:
        return ''
    if isinstance(js, dict):
        for k in ('errorDescription', 'message'):
            if js.get(k) is not None:
                return to_str(js[k])
    return ''


def account_equal(a, b):
    """`СчетаРавны` (PB:206-211): збіг цілого номера або, якщо один із номерів коротший за 29 знаків, 14 останніх
    символів."""
    a, b = trim(a), trim(b)
    return a == b or ((len(a) < 29 or len(b) < 29) and a[-14:] == b[-14:])


# ---------------------------------------------------------------------- валюти
# Перелік — РІВНО той, що знає 1С-функція `СМП_ЧтениеВыписокОбщее.ЧисловойКодВалюты` (`ТаблицаКодовВалют`): джерело
# одне, оракул його відтворює, а `tests/test_api_currency.py` читає BSL-джерело й звіряє два переліки. Розширювати
# перелік тут не можна — лише в BSL-функції (за рішенням планувальника), тоді тест змусить оновити й цей.
ISO4217 = {'UAH': '980', 'USD': '840', 'EUR': '978', 'GBP': '826', 'PLN': '985', 'CHF': '756'}


def numeric_currency(code):
    """Відтворює `ЧисловойКодВалюты`: регістр і пробіли по краях не важливі; порожній вхід -> '' (валюта рахунку);
    три цифри — лише якщо такий код є в таблиці; буквений код — за таблицею; невідомий -> None (рядок `Ошибка`)."""
    c = trim(to_str(code)).upper()
    if c == '':
        return ''
    if len(c) == 3 and c.isdigit():
        return c if c in ISO4217.values() else None
    return ISO4217.get(c)
