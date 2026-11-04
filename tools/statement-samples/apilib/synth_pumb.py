# -*- coding: utf-8 -*-
"""Синтетичні записи ПУМБ (VegaNet REST, формат запису v2) -- задача 2a, Step 3 плану 05б-2.

ПОХОДЖЕННЯ. Живих записів ПУМБ ще немає (рекордер не запускався). Форма відповідей -- за swagger банку (`VeganetDocumentItem`: масив у тілі
відповіді `/document/searcher`; `/account`: масив) і за формою відповіді токена, яку пише рекордер (замаскована). Усе, що взято зі swagger, а не з
виміру, -- ГІПОТЕЗА, ЩО ЗАКРИВАЄ run1 (кожен запис несе цю позначку в назві й у `note` маніфесту, `HYPOTHESIS`). Форми помилок (429, 5xx, 401, `invalid_grant`,
HTML) swagger не описує -- вони взяті з Keycloak / загальної форми і теж гіпотеза. Усі значення вигадані (`Gen('pumb')`).

ЩО ТУТ НЕМАЄ (і чому). Модель пагінації не виміряна (`readings.pumb_split` -> «не змодельовано»): записів, що потребують сторінок (обрив на сторінці N, курсор, що не
просувається, повна сторінка без ознаки кінця, стеля сторінок) і паузи понад стелю, тут НЕМАЄ -- вони в `AWAITING_RUN1` з причиною; тест вимагає, щоб жоден запис цього модуля
не мав `pagingRequest` чи кількох запитів `searcher` (інакше «зелений» мовчки покрив би невиміряне). Запис, де оракул ЯВНО відмовляє, -- `refused_scenarios()`.

ЗАПИТ `searcher` -- за гіпотезою: `fromDate` = `НачалоПериода` - 1 с, `toDate` = Мин(`КонецПериода` + 1 с, момент читання) (запас у секунду, бо включність меж не виміряна;
рішення -- задача 3 і вимір run1); без фільтрів станів і типу (відступ 3; тип -- В4), без `pagingRequest`; `documentAccounts` -- `accountId` рядком (як у рекордері).
"""
from datetime import datetime, timedelta

from . import common as C, kyiv, recording as R
from .common import Params

HYPOTHESIS = 'гіпотеза, swagger, закриває run1'
ACCOUNT_ID = 3300                      # accountId вигаданого рахунку (короткий: серії з 5+ цифр збігаються з лексемами сторожа)
PORT = 4103
AUTH_HOST, AUTH_PATH = 'auth.fuib.com', '/auth/realms/VegaNet/protocol/openid-connect/token'
API = '/war_veganet_api'
MASK = 'aaaaaaaaaaaaaaaaaaaa.aaaaaaaaaaaaaaaaaaaa.aaaaaaaaaaaaaaaaaaaa'      # маркер тієї ж форми, що пише рекордер (кожне рядкове значення відповіді токена)

# Перелік випадків плану (Step 3) -> запис синтетики (або «чекає виміру run1»). Тест звіряє: кожен випадок має або наявний запис, або причину.
CASES = [
    ('429', 'СинтПУМБ429'), ('5xx', 'СинтПУМБ5xx'), ('HTML', 'СинтПУМБHTML'), ('invalid_grant', 'СинтПУМБInvalidGrant'),
    ('401 на запиті', 'СинтПУМБ401Запрос'), ('обрив', 'СинтПУМБОбрыв'),
    ('обрив на сторінці N', None), ('курсор, що не просувається', None), ('повна сторінка без ознаки кінця', None), ('стеля сторінок', None),
    ('аномалія меж', 'СинтПУМБАномалияПосле'),
    ('стани', 'СинтПУМБНеокончательные'), ('скасовані', 'СинтПУМБОтменённые'),
    ('відсутні поля', 'СинтПУМБПоляОтсутствуют'), ('межа доби', 'СинтПУМБГраницаСуток'), ('перехід часу', 'СинтПУМБВремяВесна'),
    ('від\'ємна/нульова сума', 'СинтПУМБСумма'), ('довгий ідентифікатор', 'СинтПУМБДлинныйИд'),
    ('чужий рахунок', 'СинтПУМБЧужойСчет'), ('чужа валюта', 'СинтПУМБЧужаяВалюта'),
    ('майбутній період', 'СинтПУМБПериодВБудущем'), ('порожній період', 'СинтПУМБПусто'),
    ('межа довіри: відмова -> початок періоду', 'СинтПУМБ401Запрос'), ('межа довіри: межа не раніша за початок', 'СинтПУМБГраницаНаНачале'),
]
# Випадки, що потребують сторінок / невиміряного -- ЧЕКАЮТЬ run1 (оракул їх не моделює: `readings.pumb_split` -> «не змодельовано»); записів тут немає навмисно.
AWAITING_RUN1 = {
    'обрив на сторінці N': 'потрібні ≥ 2 запити searcher з pagingRequest; форма продовження (pagingSessionId, orderedLastId, orderedLastValue, direction, sortField) і ознака кінця не виміряні -- оракул відмовляє (PaginationUnmeasured)',
    'курсор, що не просувається': 'курсор -- поле pagingRequest; що вважати «не просунувся» залежить від виміряної форми курсора (A1c: роль за формою значення) -- без виміру не відтворюється',
    'повна сторінка без ознаки кінця': 'ознака кінця (коротша за pageSize чи явне поле) і максимальний pageSize не виміряні (задача 1, Step 3)',
    'стеля сторінок': 'стеля -- константа задачі 3 від виміряного обсягу; сторінки не змодельовані',
    'пауза понад стелю': 'банк 429 у swagger не описує; модель пауз ПУМБ і стеля -- задача 3 (константи -- гіпотеза); оракул для ПУМБ паузу не моделює',
    'повернення (D36 п. 5)': 'ознак повернення у полях swagger немає (відступ pumb4); запис (а) -- лише з виміру',
}


def _fmt(dt):
    return dt.strftime('%d.%m.%Y %H:%M:%S')


def request_bounds(p):
    """Межі запиту `searcher` за гіпотезою: (`НачалоПериода` - 1 с, Мин(`КонецПериода` + 1 с, момент читання у київському часі)); період після моменту -- запитів немає (None)."""
    moment = kyiv.to_local(p.reading_moment)
    if p.period_end < p.period_start or p.period_start > moment:
        return None
    return p.period_start - timedelta(seconds=1), min(p.period_end + timedelta(seconds=1), moment)


class Own:
    """Вигаданий рахунок і його власник."""

    def __init__(self, g):
        self.iban = g.iban('322001', g.acc14())
        self.name = g.name()
        self.code = g.edrpou()
        self.mfo = '322001'

    def account_item(self, currency='UAH', number=None):
        return {'id': ACCOUNT_ID + 1, 'accountId': ACCOUNT_ID, 'mfo': self.mfo, 'currency': currency, 'number': self.iban[-14:], 'name': 'Поточний', 'state': 1,
                'hostId': 3, 'branchId': 'XYZ', 'clientId': 'CL%d' % (ACCOUNT_ID + 2), 'clientName': self.name, 'clientOkpo': self.code, 'isDefault': True,
                'iban': number or self.iban, 'balance': '1000.00', 'rest': '1000.00'}


def party(g):
    return {'iban': g.iban(), 'name': g.name(), 'code': g.edrpou(), 'mfo': '300001'}


def pdoc(g, own, n, *, when, out=True, state='PROCESSED', amount='100.50', ccy='UAH', cp=None, desc=None, drop=(), **over):
    """Документ за схемою `VeganetDocumentItem` (swagger). `drop` -- поля, яких немає у відповіді; `over` -- примусові значення полів."""
    cp = cp or party(g)
    mine = {'iban': own.iban, 'name': own.name, 'code': own.code, 'mfo': own.mfo}
    snd, rcv = (mine, cp) if out else (cp, mine)
    d = {'id': 1100 + n, 'hostId': 3, 'docId': 2200 + n, 'viewTemplateId': 11, 'signTemplateId': 12, 'date': _fmt(when), 'state': state, 'type': 'UAH',
         'number': '%03d' % n, 'accountId': ACCOUNT_ID, 'amount': amount, 'currencyCode': ccy, 'description': desc if desc is not None else g.phrase(),
         'createdOn': _fmt(when), 'isImported': False, 'origin': 'IMPORTED', 'system': 'ASE', 'direction': 'OUTBOUND' if out else 'INBOUND',
         'operationDate': _fmt(when), 'senderName': snd['name'], 'correspondentName': rcv['name'], 'senderTaxId': snd['code'], 'correspondentTaxId': rcv['code'],
         'senderBankMfo': snd['mfo'], 'correspondentBankMfo': rcv['mfo'], 'senderIBAN': snd['iban'], 'correspondentIBAN': rcv['iban'], 'isRead': True}
    d.update(over)
    for k in drop:
        d.pop(k, None)
    return d


def _json(status, obj, headers=()):
    import json
    body = json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return {'status': status, 'headers': [('content-type', 'application/json;charset=utf-8'), *headers], 'body': body}


def _html(status):
    body = ('<html><head><title>Proxy Error</title></head><body><h1>%d</h1><p>The proxy server received an invalid response from an upstream server.</p></body></html>' % status)
    return {'status': status, 'headers': [('content-type', 'text/html;charset=utf-8')], 'body': body.encode('utf-8')}


def auth_ok():
    """Відповідь токена в записі -- замаскована (кожне рядкове значення -- маркер тієї ж форми; числа й форма лишаються)."""
    return _json(200, {'access_token': MASK, 'expires_in': 300, 'refresh_expires_in': 1800, 'refresh_token': MASK, 'token_type': 'Bearer',
                       'not-before-policy': 0, 'session_state': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'scope': 'profile email'})


class Reading:
    """Збирає обміни одного читання ПУМБ: автентифікація (тіло запиту опущено), список рахунків, ОДИН searcher."""

    def __init__(self, sid, own, p):
        self.sid, self.own, self.p = sid, own, p
        self.ex = []

    def _add(self, request, response=None, failure=None):
        seq = len(self.ex) + 1
        self.ex.append(R.make_exchange(seq, 'synth_pumb_%s' % self.sid, request, response, failure, started='2026-11-04T09:%02d:%02d.000Z' % (seq // 60, seq % 60)))

    def auth(self, response=None):
        self._add({'method': 'POST', 'host': AUTH_HOST, 'path': AUTH_PATH, 'query': '', 'bodyOmitted': 'автентифікація: у записі лише метод і шлях'}, response or auth_ok())

    def accounts(self, items=None, response=None):
        self._add({'method': 'GET', 'host': 'service.fuib.com', 'port': PORT, 'path': API + '/account', 'query': ''},
                  response or _json(200, items if items is not None else [self.own.account_item()]))

    def search_body(self):
        lo, hi = request_bounds(self.p)
        return {'fromDate': _fmt(lo), 'toDate': _fmt(hi), 'documentAccounts': [str(ACCOUNT_ID)]}

    def search(self, response=None, failure=None, body=None):
        import json
        raw = json.dumps(body if body is not None else self.search_body(), ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        self._add({'method': 'POST', 'host': 'service.fuib.com', 'port': PORT, 'path': API + '/document/searcher', 'query': '', 'body': raw}, response, failure)

    def full(self, docs, accounts=None):
        self.auth()
        self.accounts(accounts)
        self.search(_json(200, docs))
        return self


def _day(d, h=0, mi=0, s=0, month=11):
    return datetime(2026, month, d, h, mi, s)


def _scenarios(refused):
    """Усі синтетичні сценарії ПУМБ (`refused` -- лише ті, де оракул ЯВНО відмовляє, без еталона; інакше -- лише з еталоном)."""
    from .synth import Gen, Scenario
    g = Gen('pumb')
    own = Own(g)
    base = Params(account=own.iban, period_start=_day(1), period_end=_day(1, 23, 59, 59), reading_moment=C.DEFAULT_READING_MOMENT)
    sc, rf = [], []

    def new(sid, title, focus, **kw):
        p = Params(**{**base.__dict__, **kw})
        s = Scenario('pumb', sid, '%s [%s]' % (title, HYPOTHESIS), focus, p)
        return s, Reading(sid, own, p)

    def done(s, r, into=sc):
        s.exchanges = r.ex
        into.append(s)

    at = lambda h, mi=0, s=0, d=1: _day(d, h, mi, s)

    s, r = new('СинтПУМБОсновной', 'ПУМБ: вихідний і вхідний документи PROCESSED (форма VeganetDocumentItem за swagger; запит без фільтрів стану й типу, без pagingRequest)', [4, 5])
    done(s, r.full([pdoc(g, own, 1, when=at(10), out=True, amount='100.50'), pdoc(g, own, 2, when=at(11, 30), out=False, amount='2500.00')]))

    # ---- стани (відступ 3, D36 п. 5, п. 10)
    s, r = new('СинтПУМБНеокончательные', 'ПУМБ: непроведені документи (INPUT, ACCEPTED, SENT_TO_EPS) -- Предупреждение на кожен, межа довіри не пізніша за першу неостаточну', [3])
    done(s, r.full([pdoc(g, own, 1, when=at(9), amount='10.00'), pdoc(g, own, 2, when=at(12), state='INPUT', amount='20.00'),
                    pdoc(g, own, 3, when=at(13), state='ACCEPTED', amount='30.00', out=False), pdoc(g, own, 4, when=at(15), state='SENT_TO_EPS', amount='40.00')]))
    s, r = new('СинтПУМБОтменённые', 'ПУМБ: скасовані (REJECTED, REJECTED_BY_ACCO, REJECTED_BY_OPER, SYSTEM_ERROR) -- Предупреждение на кожен, межі довіри не тримають', [3])
    done(s, r.full([pdoc(g, own, 1, when=at(9), amount='10.00'), pdoc(g, own, 2, when=at(10), state='REJECTED', amount='20.00'),
                    pdoc(g, own, 3, when=at(11), state='REJECTED_BY_ACCO', amount='30.00'), pdoc(g, own, 4, when=at(12), state='REJECTED_BY_OPER', amount='40.00', out=False),
                    pdoc(g, own, 5, when=at(13), state='SYSTEM_ERROR', amount='50.00')]))
    s, r = new('СинтПУМБСтатусНеизвестен', 'ПУМБ: стан поза enum swagger -- рядок Ошибка, а не мовчазне відкидання', [3])
    done(s, r.full([pdoc(g, own, 1, when=at(9), amount='10.00'), pdoc(g, own, 2, when=at(10), state='ARCHIVED', amount='20.00')]))
    s, r = new('СинтПУМБГраницаНаНачале', 'ПУМБ: неостаточний документ рівно на початку періоду -- межа довіри = НачалоПериода (не раніше); неостаточний у запасі перед початком (не в періоді) не тримає межі', [3])
    done(s, r.full([pdoc(g, own, 1, when=at(0, 0, 0), state='ACCEPTED', amount='10.00'), pdoc(g, own, 2, when=_day(31, 23, 59, 59, month=10), state='ACCEPTED', amount='20.00'),
                    pdoc(g, own, 3, when=at(10), amount='30.00')]))

    # ---- відсутні поля (swagger не позначає обов'язкових)
    s, r = new('СинтПУМБПоляОтсутствуют', 'ПУМБ: відсутні поля -- без description; без id (docId); без реквізитів контрагента; без currencyCode; без amount; без state; без direction і чужі IBAN', [3, 5])
    miss = party(g)
    foreign = party(g)
    done(s, r.full([pdoc(g, own, 1, when=at(9), drop=('description',)), pdoc(g, own, 2, when=at(10), drop=('id',)),
                    pdoc(g, own, 3, when=at(11), drop=('correspondentName', 'correspondentTaxId', 'correspondentBankMfo')),
                    pdoc(g, own, 4, when=at(12), drop=('currencyCode',)), pdoc(g, own, 5, when=at(13), drop=('amount',)), pdoc(g, own, 6, when=at(14), drop=('state',)),
                    pdoc(g, own, 7, when=at(15), cp=miss, senderIBAN=foreign['iban'], correspondentIBAN=miss['iban'], drop=('direction',))]))

    # ---- сума (D28), ідентифікатор (D28), призначення
    s, r = new('СинтПУМБСумма', "ПУМБ: від'ємна, нульова й нерозбірна сума -- Ошибка bad-amount, не операція", [5])
    done(s, r.full([pdoc(g, own, 1, when=at(9), amount='100.00'), pdoc(g, own, 2, when=at(10), amount='-250.00'), pdoc(g, own, 3, when=at(11), amount='0.00'),
                    pdoc(g, own, 4, when=at(12), amount='abc')]))
    s, r = new('СинтПУМБДлинныйИд', 'ПУМБ: ідентифікатор 50 символів -- приймається, 51 і порожній -- Ошибка bad-identifier (id як рядок -- поза swagger, де id цілий; перевіряє межу D28)', [5])
    done(s, r.full([pdoc(g, own, 1, when=at(9), id='A' * 50), pdoc(g, own, 2, when=at(10), id='B' * 51), pdoc(g, own, 3, when=at(11), id='', docId=None),
                    pdoc(g, own, 4, when=at(12), drop=('id', 'docId'))]))
    s, r = new('СинтПУМБНазначение', 'ПУМБ: призначення платежу довше за 1024 символи не обрізається (відступ 5)', [5])
    done(s, r.full([pdoc(g, own, 1, when=at(9), desc=('Оплата за послуги за договором. ' * 40)[:1200])]))

    # ---- межі запиту: доба, запас у секунду, аномалія, час
    s, r = new('СинтПУМБГраницаСуток', 'ПУМБ: межа доби -- документи на 00:00:00 і 23:59:59 періоду беруться; рівно на межах запиту (початок - 1 с, кінець + 1 с) -- у запасі, відкидаються мовчки (не аномалія)', [2])
    done(s, r.full([pdoc(g, own, 1, when=_day(31, 23, 59, 59, month=10), amount='10.00'), pdoc(g, own, 2, when=at(0, 0, 0), amount='20.00'),
                    pdoc(g, own, 3, when=at(23, 59, 59), amount='30.00', out=False), pdoc(g, own, 4, when=_day(2, 0, 0, 0), amount='40.00')]))
    s, r = new('СинтПУМБАномалияПосле', 'ПУМБ: документ ПІСЛЯ верхньої межі запиту -- аномалія меж: Повторить, читання неповне, сторінка в конверт не береться', [2])
    done(s, r.full([pdoc(g, own, 1, when=at(10)), pdoc(g, own, 2, when=_day(2, 0, 0, 1))]))
    s, r = new('СинтПУМБАномалияДо', 'ПУМБ: документ ПЕРЕД нижньою межею запиту -- аномалія меж: Повторить, читання неповне', [2])
    done(s, r.full([pdoc(g, own, 1, when=at(10)), pdoc(g, own, 2, when=_day(31, 23, 59, 58, month=10))]))
    s, r = new('СинтПУМБВремяВесна', 'ПУМБ: перехід на літній час (29.03.2026) -- operationDate як місцевий рядок: 00:30, 02:59:59, 04:00:00, 23:59:59 (03:xx не існує)', [2],
               period_start=datetime(2026, 3, 28), period_end=datetime(2026, 3, 30, 23, 59, 59))
    done(s, r.full([pdoc(g, own, 1, when=datetime(2026, 3, 28, 0, 30), amount='10.00'), pdoc(g, own, 2, when=datetime(2026, 3, 29, 2, 59, 59), amount='20.00'),
                    pdoc(g, own, 3, when=datetime(2026, 3, 29, 4, 0, 0), amount='30.00', out=False), pdoc(g, own, 4, when=datetime(2026, 3, 29, 23, 59, 59), amount='40.00')]))
    s, r = new('СинтПУМБВремяОсень', 'ПУМБ: перехід на зимовий час (25.10.2026) -- 03:30 повторюється: дві різні операції з однаковим місцевим рядком часу, різні ідентифікатори', [2],
               period_start=datetime(2026, 10, 24), period_end=datetime(2026, 10, 26, 23, 59, 59))
    done(s, r.full([pdoc(g, own, 1, when=datetime(2026, 10, 25, 0, 30), amount='10.00'), pdoc(g, own, 2, when=datetime(2026, 10, 25, 3, 30), amount='20.00'),
                    pdoc(g, own, 3, when=datetime(2026, 10, 25, 3, 30), amount='30.00', out=False), pdoc(g, own, 4, when=datetime(2026, 10, 25, 23, 59, 59), amount='40.00')]))

    # ---- періоди: порожній, майбутній, перевернутий, момент читання всередині періоду
    s, r = new('СинтПУМБПусто', 'ПУМБ: порожня відповідь searcher -- повне читання без операцій', [2])
    done(s, r.full([]))
    s, r = new('СинтПУМБПериодВБудущем', 'ПУМБ: НачалоПериода пізніший за момент читання -- запитів немає, порожнє повне читання, межа довіри = НачалоПериода', [2],
               period_start=_day(14), period_end=_day(14, 23, 59, 59, month=12))
    done(s, r)
    s, r = new('СинтПУМБПериодНаоборот', 'ПУМБ: період задано навпаки -- запитів немає, «дія людини» (точка читання)', [2], period_start=_day(2, 23, 59, 59), period_end=_day(1))
    done(s, r)
    s, r = new('СинтПУМБМоментВнутриПериода', 'ПУМБ: момент читання всередині періоду -- toDate = момент, межа довіри = момент читання', [2],
               period_start=_day(14), period_end=_day(14, 23, 59, 59, month=12), reading_moment=datetime(2026, 11, 20, 0, 0, 0))
    done(s, r.full([pdoc(g, own, 1, when=_day(14, 10))]))

    # ---- чужий рахунок і валюта (відступи 1, 2)
    other = party(g)
    s, r = new('СинтПУМБЧужойСчет', 'ПУМБ: документ з IBAN, якого немає серед наших (D30) -- операція йде до точки читання, яка пише діагностику; рахунок рядка -- чужий', [5])
    done(s, r.full([pdoc(g, own, 1, when=at(9)), pdoc(g, own, 2, when=at(10), senderIBAN=other['iban'], correspondentIBAN=g.iban(), direction='OUTBOUND')]))
    s, r = new('СинтПУМБЧужаяВалюта', 'ПУМБ: документ у валюті, відмінній від валюти рахунку зі списку /account -- Предупреждение, у Операции не йде', [5])
    done(s, r.full([pdoc(g, own, 1, when=at(9)), pdoc(g, own, 2, when=at(10), ccy='USD', amount='33.00')]))
    s, r = new('СинтПУМБВалютныйСчет', 'ПУМБ: рахунок у USD -- без виміру: код валюти 980 і Предупреждение про невизначену валюту (відступ 2)', [5])
    done(s, r.full([pdoc(g, own, 1, when=at(9), ccy='USD', amount='33.00')], accounts=[own.account_item(currency='USD')]))
    s, r = new('СинтПУМБСчетНеНайден', 'ПУМБ: серед рахунків /account немає нашого IBAN -- «дія людини», searcher не йде', [1])
    r.auth()
    r.accounts([Own(g).account_item()])
    done(s, r)

    # ---- відмови (D36 п. 8): форма помилок swagger не описує -- Keycloak і загальна форма (гіпотеза)
    s, r = new('СинтПУМБInvalidGrant', 'ПУМБ: автентифікація відхилена (invalid_grant, HTTP 400) -- «дія людини», текст без облікових даних', [1])
    r.auth(_json(400, {'error': 'invalid_grant', 'error_description': 'Invalid user credentials'}))
    done(s, r)
    s, r = new('СинтПУМБ401Запрос', 'ПУМБ: 401 на запиті searcher -- «дія людини» (токен), межа довіри = НачалоПериода', [1])
    r.auth(); r.accounts(); r.search(_json(401, {'message': 'Unauthorized', 'status': 401}))
    done(s, r)
    s, r = new('СинтПУМБ429', 'ПУМБ: 429 на searcher з retry-after -- «повторити» (429 swagger не описує; модель пауз -- чекає run1)', [1])
    r.auth(); r.accounts(); r.search(_json(429, {'message': 'Too many requests', 'status': 429}, [('retry-after', '30')]))
    done(s, r)
    s, r = new('СинтПУМБ5xx', 'ПУМБ: 500 на searcher (swagger: 500 без схеми) -- «повторити»', [1])
    r.auth(); r.accounts(); r.search(_json(500, {'message': 'Internal error', 'status': 500}))
    done(s, r)
    s, r = new('СинтПУМБHTML', 'ПУМБ: 502 з HTML від проксі на searcher -- «повторити»', [1])
    r.auth(); r.accounts(); r.search(_html(502))
    done(s, r)
    s, r = new('СинтПУМБHTML200', 'ПУМБ: 200 з HTML замість JSON на searcher -- «повторити», not-json', [1])
    r.auth(); r.accounts(); r.search(_html(200))
    done(s, r)
    s, r = new('СинтПУМБОбрыв', 'ПУМБ: обрив з`єднання (таймаут) на searcher -- «повторити», межа довіри = НачалоПериода', [1, 2])
    r.auth(); r.accounts(); r.search(failure={'kind': 'timeout', 'text': 'The request was canceled due to the configured timeout of 100 seconds elapsing'})
    done(s, r)

    # ---- відмова оракула (формат дати -- гіпотеза: відсутня дата -- явна відмова, а не здогад)
    s, r = new('СинтПУМББезДатыОперации', 'ПУМБ: документ без operationDate -- оракул ЯВНО відмовляє (формат дати -- гіпотеза до виміру), еталона немає', [2])
    done(s, r.full([pdoc(g, own, 1, when=at(10), drop=('operationDate',))]), into=rf)
    return rf if refused else sc


def scenarios():
    """Синтетика ПУМБ з еталоном (оракул моделює)."""
    return _scenarios(False)


def refused_scenarios():
    """Записи, які оракул ЯВНО відхиляє (`PumbDateFormat`): форма є, еталона немає -- «не змодельовано до виміру», перевіряється тестом."""
    return _scenarios(True)
