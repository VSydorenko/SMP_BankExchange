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

BANKS = ('privat', 'mono-fop', 'mono-corp', 'pumb')      # банки з МОДЕЛЛЮ оракулу й синтетикою (синтетика ПУМБ -- `synth.pumb_scenarios()`, окремо від `synth.all_scenarios()` -- банків 5а); `recording.BANKS` -- усі формати
PRIVAT_PATH = '/api/statements/transactions'
PRIVAT_SETTINGS_PATH = '/api/statements/settings'
PRIVAT_BALANCE_PATH = '/api/statements/balance'
FOP_CLIENT_INFO = '/personal/client-info'
PAGE_SIZE_MONO = 500            # РазмерСтраницы() обох monobank-модулів (MF:479-481, MU:537-539); ФОП: ліміту в запиті немає,
                                # «сторінка коротша за 500 -- остання» -- ДОКУМЕНТАЛЬНА гіпотеза (у run1 насичення не досягнуто)
# Юросіб (D36 п. 11): кінець -- сторінка коротша за ЗАПИТАНИЙ ліміт, тож ліміт не більший за виміряну нижню межу максимуму
# сторінки. run1 (журнал 05а, пункт 8): limit=500 віддав 33 операції за раз -- банк повністю віддав сторінку в 33. Понад 33 --
# ризик, що банк сам обріже сторінку й коротша сторінка посеред даних обірве читання мовчки.
CORP_MEASURED_MAX_PAGE = 33
CORP_WORKING_LIMIT = 30


def corp_limit_problems(limit=None):
    """Сторож робочого ліміту юросіб: ліміт не більший за виміряну нижню межу максимуму сторінки."""
    limit = CORP_WORKING_LIMIT if limit is None else limit
    if limit > CORP_MEASURED_MAX_PAGE:
        return ['ліміт юросіб %d більший за виміряну нижню межу максимуму сторінки %d' % (limit, CORP_MEASURED_MAX_PAGE)]
    return []


def page_limit(bank):
    """Розмір сторінки, який запитує конектор: юросіб -- робочий ліміт; ФОП -- ліміту в запиті немає (документальні 500)."""
    return CORP_WORKING_LIMIT if bank == 'mono-corp' else PAGE_SIZE_MONO


def reading_unix(p):
    """Момент читання в секундах Unix (UTC)."""
    return int(((p.reading_moment or DEFAULT_READING_MOMENT) - kyiv.EPOCH).total_seconds())


def request_bounds(p):
    """Межі ПЕРШОГО запиту виписки monobank (D36 п. 11, спеки 71b3771 і a90f7ea), секунди Unix: нижня -- `НачалоПериода` - 1 с; верхня --
    Мин(`КонецПериода` + 1 с, момент читання). Обидві межі періоду включні; операції поза періодом у межах запиту відкидаються мовчки."""
    if p.reading_moment is None:
        # запис без моменту читання -- старі перевірки оракула на документальних прикладах (до 71b3771 і a90f7ea): межі запиту = межі періоду
        return kyiv.local_to_unix(p.period_start), kyiv.local_to_unix(p.period_end)
    return kyiv.local_to_unix(p.period_start) - 1, min(kyiv.local_to_unix(p.period_end) + 1, reading_unix(p))


def fop_page_limit(p):
    """Повна сторінка ФОП: поріг, з якого продовжуємо читання (D36 п. 11). ДОКУМЕНТАЛЬНА гіпотеза -- 500 (go-mono v0.5.3, спільнотна
    документація; журнал 05а, «Задача 5, до старту»), не виміряне правило. `Params.page_limit` -- шов розміру сторінки в тесті
    (лише менший або рівний 500): синтетична модель банку з меншою сторінкою читається з тим самим порогом."""
    return p.page_limit or PAGE_SIZE_MONO


FOP_WINDOW_SECONDS = 2678400    # ДлинаОтрезкаСекунд() (MF:472-476)
# Стеля паузи за заголовком банку (D36 п. 8, спека a90f7ea): не менша за документований інтервал ФОП між запитами виписки (60 с), інакше
# звичайне обмеження частоти ставало б відмовою; 120 с -- подвійний запас. Банк просить більше -- `Повторить` без очікування.
PAUSE_CEILING_SECONDS = 120
# Фіксований момент транспорту для записів (UTC, лише monobank): пізніший за кінці періодів усіх записів, крім ЗапErrorsFuturePeriod.
DEFAULT_READING_MOMENT = datetime(2026, 11, 4, 0, 0, 0)
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
    old_account_obsolete: str = ''              # НомерСчетаУстаревший (PB:427-428); порожній — не заповнений
    old_account_currency: object = None         # ВалютаДенежныхСредств.Код; None — не заповнена
    old_session_tz: str = 'Europe/Kiev'         # пояс сеансу, яким рахує `МестноеВремя` попередник monobank
    old_currency_catalog: dict = field(default_factory=lambda: {'USD': '840', 'EUR': '978'})   # довідник Валюты
    old_cached_account_id: bool = False         # ИД облікового запису заповнений: client-info не кличеться (MF:373-376)
    # --- режим «очікуване»
    # ідентифікатор ПриватБанку (D36 п. 6): тимчасово `ID` (у run1 = TECHNICAL_TRANSACTION_ID, 30 символів) до run2
    privat_id: object = 'ID'                    # 'ID' | 'TECHNICAL_TRANSACTION_ID' | 'REF+REFN' | None
    fop_pause_after_client_info: int = 0        # секунди; виміряно (run1, п. 11): виписка через 0,3 с після client-info -- 200, без 429
    # банківська межа (D36 п. 10): початок першого дня без ознаки остаточності; день без рядка балансу -- неостаточний
    absent_day_is_final: bool = False
    # шов розміру сторінки ФОП (тест): поріг «повної сторінки»; None -- робочий (документальні 500). У запиті ФОП ліміту немає
    page_limit: object = None
    # шов стелі сторінок ПриватБанку (тест): None -- робоча (`PRIVAT_PAGE_CEILING`); лише менша за робочу
    page_ceiling: object = None
    # момент читання `Транспорт.ТекущийМомент()` (UTC, naive); None -- банк без правила верхньої межі (Приват), у еталон не пишеться
    reading_moment: object = None
    # ПУМБ (Р-е): значення облікових даних, що їх знає платформа (логін тощо) і які ВИРІЗАЮТЬСЯ з тексту помилки банку (`error_description`).
    # Лише для оракула й тестів; в еталон (`to_json`) НЕ пишуться. Порожній кортеж -- нічого не вирізати.
    credentials: tuple = ()
    # ПУМБ: чи звіряти з правилом меж і формою тіла ПЕРШИЙ запит `searcher` (в еталон не пишеться). Так (типово): перший запит справжнього запису -- форма рекордера, не конектора -- відхиляється;
    # False лише у перевірці (в) знеособлення, де порівнюється розбір сирого й знеособленого запису, а не форма запиту.
    strict_first_request: bool = True
    # ПУМБ: `Параметры.ВалютаСчета` -- числовий код ISO 4217 рядком із 3 цифр, який точка читання ЗАВЖДИ кладе для API з банківського рахунку 1С (D36 п. 2, D28 @ 21f0ab0).
    # None -- поля в параметрах читання немає (банки 5а його не читають, в еталон не пишеться); '' -- поле є, але порожнє (рахунок 1С без валюти).
    account_currency_code: object = None

    def to_json(self):
        d = {'НомерСчета': self.account, 'НачалоПериода': iso(self.period_start), 'КонецПериода': iso(self.period_end)}
        if self.page_limit:
            d['РазмерСтраницы'] = self.page_limit
        if self.page_ceiling:
            d['ПотолокСтраниц'] = self.page_ceiling
        if self.reading_moment is not None:
            d['МоментЧтения'] = iso(self.reading_moment)
        if self.account_currency_code is not None:
            d['ВалютаСчета'] = self.account_currency_code
        return d


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


_PUMB_DATE_RX = re.compile(r'\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2}')


class PumbDateFormat(ValueError):
    """Дата ПУМБ не в гіпотезі `dd.MM.yyyy HH:mm:ss`: оракул ЯВНО відмовляє, формат не вгадується (значення в повідомленні немає)."""


def pumb_date(text):
    """`dd.MM.yyyy HH:mm:ss` (гіпотеза за swagger і запитами попередника, до виміру) -> naive datetime (київський час). Інший формат -- `PumbDateFormat`."""
    s = to_str(text)
    if not _PUMB_DATE_RX.fullmatch(s):
        raise PumbDateFormat('дата ПУМБ не у форматі dd.MM.yyyy HH:mm:ss (гіпотеза, не виміряно)')
    try:
        return datetime.strptime(s, '%d.%m.%Y %H:%M:%S')
    except ValueError:
        raise PumbDateFormat('дата ПУМБ не у форматі dd.MM.yyyy HH:mm:ss (гіпотеза, не виміряно)')


# ПУМБ (Р4, рішення консультанта, редакція 5 плану): основа читання -- `searcher` БЕЗ пагінації (D36 п. 11, абзац «API, що віддає період однією відповіддю», `e937fbd`).
# Відповідь із кількістю документів >= ПОРОГА ділить період навпіл (рекурсивно до доби); доба з відповіддю >= порога -- «дія людини».
# Поріг 1191 -- найбільший спостережений розмір відповіді (run2 LongestPeriod, 70fb320); стеля банку C >= спостереженого, обрізана відповідь має розмір рівно C,
# тож поріг <= спостереженого гарантує ділення; поріг понад спостережене -- мовчазна втрата. Перерахувати, якщо трапиться більша відповідь.
PUMB_RESPONSE_THRESHOLD = 1191

# Запит `searcher` форми рекордера (run1b, run2: межі рівно по періоду, фільтри `documentState`/`documentType`) конектор не відтворює (межі цілими добами, без фільтрів, відступ pumb3): оракул відхиляє такий запит; справжні записи ПУМБ -- run3 і run4 (знято у формі конектора).


def pumb_request_bounds(a, b):
    """Межі запиту `searcher` для піддобу періоду [a, b] (місцеві `datetime`; `b` вже не пізніший за момент читання): ПУМБ фільтрує цілими календарними добами, обидві межі включно
    (D36 п. 11, run2 70fb320) -- `fromDate` = доба `a` 00:00:00, `toDate` = доба `b` 23:59:59; запасу в секунду немає. Точний період дає фільтр конектора за `operationDate`."""
    return datetime(a.year, a.month, a.day), datetime(b.year, b.month, b.day, 23, 59, 59)


def pumb_halves(a, b):
    """Ділення періоду [a, b] навпіл за ДОБАМИ (D36 п. 11): перша половина -- `n // 2` діб, друга -- решта; межа -- опівночі, половини без проміжку й без перекриття
    ([a, опівніч - 1 с] і [опівніч, b], секундна точність). Період в межах однієї доби не ділиться -> None."""
    days = (datetime(b.year, b.month, b.day) - datetime(a.year, a.month, a.day)).days + 1
    if days < 2:
        return None
    mid = datetime(a.year, a.month, a.day) + timedelta(days=days // 2)
    return (a, mid - timedelta(seconds=1)), (mid, b)


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


def fop_windows(start_unix, end_unix, moment_unix=None):
    """Запити читання monobank ФОП у СЕКУНДАХ UNIX, від найновішого до найстарішого (рішення консультанта до раунду `from`, спеки 71b3771 і
    a90f7ea). Період `[НачалоПериода, КонецПериода]` ділиться на відрізки, кожен не довший за 31 × 86400 с (документація: не більше 31 доби + 1
    година); запит КОЖНОГО відрізка бере запас у секунду з обох боків: `from` відрізка - 1 с ... `to` відрізка + 1 с, а для найновішого `to` =
    Мин(`КонецПериода` + 1 с, момент читання). Вікно запиту не довше 31 × 86400 + 2 с. Перекриття сусідніх запитів -- це і є запас: операція
    на межі відрізків потрапляє хоча б в один із запитів за будь-якої включності `from` / `to`; повтор відкидається за `id`. Кінець раніший за
    початок конектор не бачить: це відмова точки читання до конектора (D36). -> [(from, to)]. Період, що починається пізніше за момент читання,
    обробляє `request_windows` (запитів немає)."""
    top = end_unix + 1 if moment_unix is None else min(end_unix + 1, moment_unix)
    out, upper = [], min(end_unix, top - 1)         # відрізки -- від ПЕРШОЇ верхньої межі (Мин(КонецПериода, верх - 1 с)), а не від КонецПериода: інакше за кінцем періоду далі моменту читання на > 31 доби перший запит мав би from > to
    while True:
        frm = max(start_unix, upper - FOP_WINDOW_SECONDS)
        out.append((frm - 1, top if not out else upper + 1))
        if frm <= start_unix:
            return out
        upper = frm - 1


def _legacy_fop_windows(start_unix, end_unix):
    """Відрізки до рішень 71b3771 і a90f7ea (запис без моменту читання: старі перевірки оракула на документальних прикладах)."""
    if start_unix >= end_unix:
        return [(start_unix, end_unix)]
    out, upper = [], end_unix
    while True:
        frm = max(start_unix, upper - FOP_WINDOW_SECONDS)
        out.append((frm, upper))
        if frm <= start_unix:
            return out
        upper = frm + 1


def request_windows(p, fop):
    """Запити виписки, які зробить конектор для параметрів читання `p`: ФОП -- відрізки (`fop_windows`), юросіб -- один запит (`request_bounds`).
    Порядок у конекторі: 1) `НачалоПериода` пізніший за момент читання -- запитів немає (порожнє повне читання, межа довіри = `НачалоПериода`);
    2) далі звичайне читання. Перевернутий період (кінець раніший за початок) відхиляє точка читання ДО конектора (запитів немає, клас «дія
    людини»), оракул це повторює в `expected._mono`. Запис без моменту читання -- старі межі."""
    s, e = kyiv.local_to_unix(p.period_start), kyiv.local_to_unix(p.period_end)
    if p.reading_moment is None:
        return _legacy_fop_windows(s, e) if fop else [(s, e)]
    m = reading_unix(p)
    if s > e or s > m:
        return []
    return fop_windows(s, e, m) if fop else [request_bounds(p)]


PRIVAT_WORKING_LIMIT = 100       # limit запиту транзакцій ПриватБанку: «рекомендовано не більше 100» (privat.txt, параметр limit); кінець читання -- exist_next_page, тож межі виміряного максимуму сторінки немає
# Стеля сторінок читання -- ОКРЕМА константа кожного конектора і ЗАПОБІЖНИК від нескінченного циклу, а не робочий обсяг. Замала стеля дає видиму «дію людини» з пропозицією звузити період,
# а не втрату даних; після відповіді власника про реальні обсяги її замінює правка однієї константи (тут і в модулі конектора). Клас понад стелю -- «дія людини» (законний обсяг повтор не
# зменшить). Формула: діб x операцій на добу / limit + запас. Діб = 366: найдовший інтерактивний період (спекою НЕ обмежено, D18 п. 7), він більший за глибину регламенту 31 доба (D18 п. 4,
# пропозиція) + перекриття 3 доби (ГІПОТЕЗА, значення задає етап 5б). Операцій на добу -- ГІПОТЕЗА, не виміряно (журнал 05а, run1/run3: кілька на добу): 1000 для Привата й юросіб, 200 для ФОП.
# Приват: 366 x 1000 / 100 = 3660 + запас -> 4000 (1 запит/с, privat.txt:62: 67 хв). Юросіб: 366 x 1000 / 30 = 12 200 + запас -> 13 000. ФОП: 366 x 200 / 500 = 147 + по одній короткій на 12
# відрізків = 160 + запас -> 200 запитів (між запитами 60 с: 200 хв). Шов стелі в тесті -- лише менша за робочу (`Params.page_ceiling`).
PAGE_CEILING = {'privat': 4000, 'mono-corp': 13000, 'mono-fop': 200}


def page_ceiling(bank, p):
    """Стеля сторінок читання: шов тесту (менша за робочу) або робоча константа конектора."""
    return p.page_ceiling or PAGE_CEILING[bank]
PRIVAT_PAUSE_SECONDS = 1         # документація Привату, temp/research/2026-10-13-readers/docs/privat.txt, рядок 62: «Рекомендовано відправляти запити не частіше 1 запиту в секунду.»


def privat_days(p):
    """Дні запиту ПриватБанку (D36 п. 11, спека d392bc4): цілими днями від дня `НачалоПериода` до дня Мин(`КонецПериода`, момент читання); обидві
    дати банк включає (журнал 05а `f751d01`), запасу в день немає. -> (початок, кінець) -- `datetime` на початку доби -- або None, якщо запитів
    немає (`НачалоПериода` пізніший за момент читання: порожнє повне читання; перевернутий період відхиляє точка читання до конектора).
    Порівняння в одній шкалі: момент читання (UTC) переводиться в київський час. Запис без моменту читання -- межі періоду як є (старі перевірки)."""
    start, end = p.period_start, p.period_end
    if p.reading_moment is not None:
        if end < start or kyiv.local_to_unix(start) > reading_unix(p):
            return None
        end = min(end, kyiv.unix_to_local(reading_unix(p)))
    return datetime(start.year, start.month, start.day), datetime(end.year, end.month, end.day)


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
# одне, оракул його відтворює, а `tests/test_api_round1.py` (`CurrencyList`) читає BSL-джерело й звіряє два переліки. Розширювати
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
