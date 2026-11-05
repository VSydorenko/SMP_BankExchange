# -*- coding: utf-8 -*-
"""Синтетичні записи ПУМБ (VegaNet REST, формат запису v2) -- задача 2a, Step 3 плану 05б-2.

ПОХОДЖЕННЯ. Живих записів ПУМБ ще немає (рекордер не запускався). Форма відповідей -- за swagger банку (`VeganetDocumentItem`: масив у тілі
відповіді `/document/searcher`; `/account`: масив) і за формою відповіді токена, яку пише рекордер (замаскована). Усе, що взято зі swagger, а не з
виміру, -- ГІПОТЕЗА, ЩО ЗАКРИВАЄ run1 (кожен запис несе цю позначку в назві й у `note` маніфесту, `HYPOTHESIS`). Форми помилок (429, 5xx, 401, `invalid_grant`,
HTML) swagger не описує -- вони взяті з Keycloak / загальної форми і теж гіпотеза. Усі значення вигадані (`Gen('pumb')`).

ПАГІНАЦІЯ. Р4 (рішення консультанта): основа читання -- `searcher` БЕЗ пагінації; відповідь, не менша за `C.PUMB_RESPONSE_THRESHOLD` (1191, спостережений максимум run2), ділить період навпіл
(D36 п. 11); тому записи ділення (кілька запитів `searcher` без `pagingRequest`) тут Є. Випадки, що мали сенс лише для сторінок (обрив на сторінці N, курсор, повна сторінка без
ознаки кінця, стеля сторінок), -- у `NOT_APPLICABLE_NO_PAGING` з причиною; паузи понад стелю -- в `AWAITING_RUN1`. Тест вимагає, щоб жоден запис цього модуля не мав
`pagingRequest`. Запис, де оракул ЯВНО відмовляє, -- `refused_scenarios()`.

ЗАПИТ `searcher` -- цілі календарні доби, обидві межі включно (D36 п. 11, run2 70fb320): `fromDate` = доба `НачалоПериода` 00:00:00, `toDate` = доба Мин(`КонецПериода`, момент читання) 23:59:59;
точний період дає фільтр конектора за `operationDate` (мовчки); без фільтрів станів і типу (відступ 3; тип -- В4), без `pagingRequest`; `documentAccounts` -- `accountId` рядком (як у рекордері).
Відповіді на порозі й вище -- лише лічильник для ділення, у конверт не беруться, тому `filler` -- мінімальні документи (розмір запису); прийняті відповіді -- повні документи.
"""
from datetime import datetime, timedelta

from . import common as C, kyiv, recording as R
from .common import Params

HYPOTHESIS = 'гіпотеза, swagger, закриває run1'
ACCOUNT_ID = 3300                      # accountId вигаданого рахунку (короткий: серії з 5+ цифр збігаються з лексемами сторожа)
PORT = 4103
AUTH_HOST, AUTH_PATH = 'auth.fuib.com', '/auth/realms/VegaNet/protocol/openid-connect/token'
API = '/war_veganet_api'
FAKE_LOGIN = 'vymyshlenyi_login_pumb'                                            # вигаданий логін: у відповіді invalid_grant він мусить бути вирізаний (Р-е)
MASK = 'aaaaaaaaaaaaaaaaaaaa.aaaaaaaaaaaaaaaaaaaa.aaaaaaaaaaaaaaaaaaaa'      # маркер тієї ж форми, що пише рекордер (кожне рядкове значення відповіді токена)

# Перелік випадків плану (Step 3) -> запис синтетики (або «чекає виміру run1»). Тест звіряє: кожен випадок має або наявний запис, або причину.
CASES = [
    ('429', 'СинтПУМБ429'), ('5xx', 'СинтПУМБ5xx'), ('HTML', 'СинтПУМБHTML'), ('invalid_grant', 'СинтПУМБInvalidGrant'),
    ('401 на запиті', 'СинтПУМБ401Запрос'), ('обрив', 'СинтПУМБОбрыв'),
    ('обрив на сторінці N', None), ('курсор, що не просувається', None), ('повна сторінка без ознаки кінця', None), ('стеля сторінок', None),
    ('без пагінації: відповідь нижче порога -- один запит', 'СинтПУМБНижеПорога'), ('без пагінації: відповідь на порозі -- ділення навпіл', 'СинтПУМБПорогДелит'),
    ('без пагінації: ділення рекурсивно, кілька рівнів', 'СинтПУМБДелитГлубоко'), ('без пагінації: доба на порозі -- дія людини', 'СинтПУМБСуткиНаПороге'),
    ('без пагінації: єдина доба на порозі -- дія людини', 'СинтПУМБСуткиСразуНаПороге'),
    ('без пагінації: відповідь понад спостережений максимум (імітація обрізаної стелею) -- ділиться', 'СинтПУМБОтсечёнСтеля'),
    ('direction проти боку за запитаним рахунком; переказ між своїми', 'СинтПУМБПереводМеждуСвоими'),
    ('STM у відповіді -- не операції і без Предупреждение', 'СинтПУМБSTM'),
    ('валютний рахунок: CUR_ADV -- рух, CUR / CUR_C / CUR_S / STM поруч -- не рух, мовчки', 'СинтПУМБВалютаТипыДвижения'),
    ('невідомий тип документа -- відмова всього читання, дія людини', 'СинтПУМБНеизвестныйТип'), ('порожній тип документа -- так само невідомий', 'СинтПУМБТипПустой'),
    ('кілька рахунків під IBAN: пара (IBAN, валюта) однозначна', 'СинтПУМБМультиВалюта'), ('кілька рахунків під IBAN: пари немає', 'СинтПУМБМультиВалютаНетПары'),
    ('кілька рахунків під IBAN: ВалютаСчета порожнє', 'СинтПУМБМультиВалютаПусто'), ('документ без IBAN: номер рахунку = запитаному', 'СинтПУМБНомерСчета'),
    ('документ без свого рахунку -- діагностика', 'СинтПУМБНетСвоегоСчета'),
    ('аномалія меж', 'СинтПУМБАномалияПосле'),
    ('стани', 'СинтПУМБНеокончательные'), ('скасовані', 'СинтПУМБОтменённые'),
    ('відсутні поля', 'СинтПУМБПоляОтсутствуют'), ('межа доби', 'СинтПУМБГраницаСуток'), ('перехід часу', 'СинтПУМБВремяВесна'),
    ('від\'ємна/нульова сума', 'СинтПУМБСумма'), ('довгий ідентифікатор', 'СинтПУМБДлинныйИд'),
    ('чужий рахунок', 'СинтПУМБЧужойСчет'), ('чужа валюта', 'СинтПУМБЧужаяВалюта'),
    ('майбутній період', 'СинтПУМБПериодВБудущем'), ('порожній період', 'СинтПУМБПусто'),
    ('межа довіри: відмова -> початок періоду', 'СинтПУМБ401Запрос'), ('межа довіри: межа не раніша за початок', 'СинтПУМБГраницаНаНачале'),
]
# Випадки, що чекають виміру: записів тут немає навмисно.
AWAITING_RUN1 = {
    'пауза понад стелю': 'банк 429 у swagger не описує; модель пауз ПУМБ і стеля -- задача 3 (константи -- гіпотеза); оракул для ПУМБ паузу не моделює',
    'повернення (D36 п. 5)': 'ознак повернення у полях swagger немає (відступ pumb4); запис (а) -- лише з виміру',
}
# Випадки, що мали сенс для пагінації й НЕ застосовуються після Р4 (конектор пагінації не використовує: запит без `pagingRequest`, ділення періоду навпіл). Не видалено: причина названа.
NOT_APPLICABLE_NO_PAGING = {
    'обрив на сторінці N': 'не застосовується (Р4: без пагінації): сторінок немає; обрив між запитами ділення -- збій наступного запиту searcher (клас за HTTP, межа довіри = НачалоПериода, прочитане лишається), окремого випадку не потребує',
    'курсор, що не просувається': 'не застосовується (Р4: без пагінації): курсора немає, конектор pagingRequest не шле; запит із pagingRequest оракул відхиляє явно (PaginationUnmeasured)',
    'повна сторінка без ознаки кінця': 'не застосовується (Р4: без пагінації): «повної сторінки» немає; її роль -- відповідь на порозі, що ділить період (СинтПУМБПорогДелит); поріг -- гіпотеза до run2',
    'стеля сторінок': 'не застосовується (Р4: без пагінації): сторінок немає; кількість запитів обмежує глибина ділення (до доби: доба на порозі -- «дія людини», СинтПУМБСуткиНаПороге)',
}


def _fmt(dt):
    return dt.strftime('%d.%m.%Y %H:%M:%S')


def request_bounds(p):
    """Межі запиту `searcher`: (доба `НачалоПериода` 00:00:00, доба Мин(`КонецПериода`, момент читання у київському часі) 23:59:59); період після моменту -- запитів немає (None)."""
    moment = kyiv.to_local(p.reading_moment)
    if p.period_end < p.period_start or p.period_start > moment:
        return None
    return C.pumb_request_bounds(p.period_start, min(p.period_end, moment))


class Own:
    """Вигаданий рахунок і його власник."""

    def __init__(self, g):
        self.iban = g.iban('322001', g.acc14())
        self.name = g.name()
        self.code = g.edrpou()
        self.mfo = '322001'

    def account_item(self, currency='UAH', number=None, alt='', account_id=ACCOUNT_ID):
        return {'id': account_id + 1, 'accountId': account_id, 'mfo': self.mfo, 'currency': currency, 'number': self.iban[-14:], 'name': 'Поточний', 'state': 1,
                'hostId': 3, 'branchId': 'XYZ', 'clientId': 'CL%d' % (ACCOUNT_ID + 2), 'clientName': self.name, 'clientOkpo': self.code, 'isDefault': True,
                'iban': number or self.iban, 'altNumber': alt or None, 'balance': '1000.00', 'rest': '1000.00'}


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
        self.acc_id = ACCOUNT_ID                  # accountId, що іде в documentAccounts (за парою IBAN і валюта -- не завжди перший з рахунків IBAN)

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
        return {'fromDate': _fmt(lo), 'toDate': _fmt(hi), 'documentAccounts': [str(self.acc_id)]}

    def search_for(self, lo, hi, docs):
        """Запит піддобу [lo, hi] за правилом меж (`C.pumb_request_bounds`, кінець не пізніший за момент читання) і відповідь `docs`."""
        a, b = C.pumb_request_bounds(lo, min(hi, kyiv.to_local(self.p.reading_moment)))
        self.search(_json(200, docs), body={'fromDate': _fmt(a), 'toDate': _fmt(b), 'documentAccounts': [str(self.acc_id)]})

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
    # ВалютаСчета: точка читання для API кладе її ЗАВЖДИ. Базово 980; конектор читає її лише коли під IBAN кілька рахунків (СинтПУМБВалютныйСчет: один рахунок USD, поле 980 -- не читається)
    base = Params(account=own.iban, period_start=_day(1), period_end=_day(1, 23, 59, 59), reading_moment=C.DEFAULT_READING_MOMENT, account_currency_code='980')
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
    s, r = new('СинтПУМБГраницаНаНачале', 'ПУМБ: період 09:00:00-23:59:59 доби; неостаточний документ рівно на початку періоду -- межа довіри = НачалоПериода (не раніше); неостаточний тієї ж доби, але до початку періоду (в межах доби запиту), не тримає межі', [3],
               period_start=at(9, 0, 0))
    done(s, r.full([pdoc(g, own, 1, when=at(9, 0, 0), state='ACCEPTED', amount='10.00'), pdoc(g, own, 2, when=at(8, 59, 59), state='ACCEPTED', amount='20.00'),
                    pdoc(g, own, 3, when=at(10), amount='30.00')]))

    # ---- відсутні поля (swagger не позначає обов'язкових)
    s, r = new('СинтПУМБПоляОтсутствуют', 'ПУМБ: відсутні поля -- без description; id null, ідентифікатор -- docId; без реквізитів контрагента; без currencyCode; без amount; без state; без direction і чужі IBAN; без IBAN обох сторін (Ошибка no-iban)', [3, 5])
    miss = party(g)
    foreign = party(g)
    done(s, r.full([pdoc(g, own, 1, when=at(9), drop=('description',)), pdoc(g, own, 2, when=at(10), id=None),
                    pdoc(g, own, 3, when=at(11), drop=('correspondentName', 'correspondentTaxId', 'correspondentBankMfo')),
                    pdoc(g, own, 4, when=at(12), drop=('currencyCode',)), pdoc(g, own, 5, when=at(13), drop=('amount',)), pdoc(g, own, 6, when=at(14), drop=('state',)),
                    pdoc(g, own, 7, when=at(15), cp=miss, senderIBAN=foreign['iban'], correspondentIBAN=miss['iban'], drop=('direction',)),
                    pdoc(g, own, 8, when=at(16), drop=('senderIBAN', 'correspondentIBAN'))]))                     # Р-д: без IBAN обох сторін -- Ошибка no-iban

    # ---- сума (D28), ідентифікатор (D28), призначення
    s, r = new('СинтПУМБСумма', "ПУМБ: від'ємна, нульова й нерозбірна сума -- Ошибка bad-amount, не операція", [5])
    done(s, r.full([pdoc(g, own, 1, when=at(9), amount='100.00'), pdoc(g, own, 2, when=at(10), amount='-250.00'), pdoc(g, own, 3, when=at(11), amount='0.00'),
                    pdoc(g, own, 4, when=at(12), amount='abc')]))
    s, r = new('СинтПУМБДлинныйИд', 'ПУМБ: ідентифікатор (docId) 50 символів -- приймається, 51 і порожній -- Ошибка bad-identifier (docId як рядок -- гіпотеза; перевіряє межу D28)', [5])
    done(s, r.full([pdoc(g, own, 1, when=at(9), docId='A' * 50), pdoc(g, own, 2, when=at(10), docId='B' * 51), pdoc(g, own, 3, when=at(11), id='', docId=None),
                    pdoc(g, own, 4, when=at(12), drop=('id', 'docId')), pdoc(g, own, 5, when=at(13), id='')]))      # id -- не ідентифікатор (виміряно): береться docId
    s, r = new('СинтПУМБНазначение', 'ПУМБ: призначення платежу довше за 1024 символи не обрізається (відступ 5)', [5])
    done(s, r.full([pdoc(g, own, 1, when=at(9), desc=('Оплата за послуги за договором. ' * 40)[:1200])]))

    # ---- межі запиту: доба, запас у секунду, аномалія, час
    s, r = new('СинтПУМБГраницаСуток', 'ПУМБ: період 09:00:00-17:59:59 однієї доби -- запит іде цілою добою, точний період дає фільтр конектора: документи 09:00:00 і 17:59:59 беруться, 08:59:59 і 18:00:00 тієї ж доби відкидаються мовчки (не аномалія, не діагностика)', [2],
               period_start=at(9, 0, 0), period_end=at(17, 59, 59))
    done(s, r.full([pdoc(g, own, 1, when=at(0, 0, 0), amount='5.00'), pdoc(g, own, 2, when=at(8, 59, 59), amount='10.00'), pdoc(g, own, 3, when=at(9, 0, 0), amount='20.00'),
                    pdoc(g, own, 4, when=at(17, 59, 59), amount='30.00', out=False), pdoc(g, own, 5, when=at(18, 0, 0), amount='40.00'), pdoc(g, own, 6, when=at(23, 59, 59), amount='50.00')]))
    s, r = new('СинтПУМБАномалияПосле', 'ПУМБ: документ ПІСЛЯ останньої доби запиту (02.11 00:00:00 при запиті 01.11) -- аномалія меж: Повторить, читання неповне, сторінка в конверт не береться', [2])
    done(s, r.full([pdoc(g, own, 1, when=at(10)), pdoc(g, own, 2, when=_day(2, 0, 0, 0))]))
    s, r = new('СинтПУМБАномалияДо', 'ПУМБ: документ ПЕРЕД першою добою запиту (31.10 23:59:59 при запиті 01.11) -- аномалія меж: Повторить, читання неповне', [2])
    done(s, r.full([pdoc(g, own, 1, when=at(10)), pdoc(g, own, 2, when=_day(31, 23, 59, 59, month=10))]))
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
    s, r = new('СинтПУМБInvalidGrant', 'ПУМБ: автентифікація відхилена (invalid_grant, HTTP 400) -- «дія людини»; error_description читається (Р-е), вигаданий логін у ньому вирізається', [1],
               credentials=(FAKE_LOGIN,))
    r.auth(_json(400, {'error': 'invalid_grant', 'error_description': 'Invalid user credentials for ' + FAKE_LOGIN}))
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

    # ---- без пагінації (Р4): ділення навпіл (D36 п. 11), поріг -- C.PUMB_RESPONSE_THRESHOLD (1191, спостережений максимум run2)
    T = C.PUMB_RESPONSE_THRESHOLD
    two_days = dict(period_start=_day(1), period_end=_day(2, 23, 59, 59))
    three_days = dict(period_start=_day(1), period_end=_day(3, 23, 59, 59))
    mate_lean = party(g)

    def filler(count, day):
        """`count` мінімальних документів доби `day` -- відповідь, що лише досягає порога (у конверт не береться: ділення перечитає її половинами)."""
        return [{'docId': 5000 + i, 'operationDate': _fmt(_day(day, 12))} for i in range(count)]

    def bulk(count, n0, day):
        """`count` повних, але лінійних документів PROCESSED доби `day`, по одному на хвилину від 00:00 (відповідь нижче порога -- береться в операції)."""
        return [pdoc(g, own, n0 + i, when=_day(day) + timedelta(minutes=i), out=bool(i % 2), amount='%d.00' % (1 + i % 7), cp=mate_lean, desc='Оплата %d' % i,
                     drop=('hostId', 'viewTemplateId', 'signTemplateId', 'createdOn', 'isImported', 'origin', 'system', 'isRead', 'accountId', 'number', 'date',
                           'senderName', 'correspondentName', 'senderTaxId', 'correspondentTaxId', 'senderBankMfo', 'correspondentBankMfo')) for i in range(count)]

    s, r = new('СинтПУМБНижеПорога', 'ПУМБ: відповідь на 1 менша за поріг (1190) -- один запит за весь період, без ділення; усі документи беруться в операції', [4], **two_days)
    r.auth(); r.accounts(); r.search_for(s.params.period_start, s.params.period_end, bulk(T - 1, 5000, 1))   # docId 7201..8390: не збігається з accountId (3300, 3311) -- Т2 шукає їх як окремі числа
    done(s, r)
    A = pdoc(g, own, 1, when=at(10), amount='11.00')
    B = pdoc(g, own, 2, when=_day(1, 23, 59, 59), amount='22.00')
    Cc = pdoc(g, own, 3, when=_day(2, 0, 0, 0), amount='33.00', out=False)
    D = pdoc(g, own, 4, when=_day(2, 12), amount='44.00')
    s, r = new('СинтПУМБПорогДелит', 'ПУМБ: відповідь рівно на порозі (1191) -- період ділиться навпіл (діб 2: 1 + 1); запит кожної половини -- її доба: 01.11 23:59:59 і 02.11 00:00:00 потрапляють лише в запит своєї доби, по одному разу', [4], **two_days)
    r.auth(); r.accounts()
    r.search_for(s.params.period_start, s.params.period_end, filler(T, 1))                  # увесь період: відповідь на порозі -- не береться
    r.search_for(_day(1), _day(1, 23, 59, 59), [A, B])                                       # перша половина (доба 01.11)
    r.search_for(_day(2), _day(2, 23, 59, 59), [Cc, D])                                      # друга половина (доба 02.11)
    done(s, r)
    s, r = new('СинтПУМБДелитГлубоко', 'ПУМБ: ділення рекурсивно -- 3 доби: на порозі (1 + 2), друга половина (2 доби) знову на порозі (1 + 1); запити в порядку обходу: усе, 01.11, 02-03.11, 02.11, 03.11', [4], **three_days)
    r.auth(); r.accounts()
    r.search_for(s.params.period_start, s.params.period_end, filler(T, 1))
    r.search_for(_day(1), _day(1, 23, 59, 59), [pdoc(g, own, 1, when=at(9), amount='10.00')])
    r.search_for(_day(2), _day(3, 23, 59, 59), filler(T, 2))
    r.search_for(_day(2), _day(2, 23, 59, 59), [pdoc(g, own, 2, when=_day(2, 9), amount='20.00')])
    r.search_for(_day(3), _day(3, 23, 59, 59), [pdoc(g, own, 3, when=_day(3, 9), amount='30.00')])
    done(s, r)
    s, r = new('СинтПУМБСуткиНаПороге', 'ПУМБ: після ділення друга доба (02.11) сама дає відповідь на порозі -- ДействиеЧеловека, читання неповне, діагностика називає добу й кількість; прочитане першої доби лишається', [4], **two_days)
    r.auth(); r.accounts()
    r.search_for(s.params.period_start, s.params.period_end, filler(T, 1))
    r.search_for(_day(1), _day(1, 23, 59, 59), [pdoc(g, own, 1, when=at(9), amount='10.00')])
    r.search_for(_day(2), _day(2, 23, 59, 59), filler(T, 2))
    done(s, r)
    s, r = new('СинтПУМБСуткиСразуНаПороге', 'ПУМБ: період в одну добу, відповідь на порозі -- ділити нічого: ДействиеЧеловека без жодної операції', [4])
    r.auth(); r.accounts(); r.search_for(s.params.period_start, s.params.period_end, filler(T, 1))
    done(s, r)

    s, r = new('СинтПУМБОтсечёнСтеля', 'ПУМБ: відповідь на 1500 документів -- понад спостережений максимум (1191, поріг): імітація відповіді, обрізаної невідомою стелею банку C >= 1191; ДІЛИТЬСЯ (поріг понад спостережене був би мовчазною втратою)', [4], **two_days)
    r.auth(); r.accounts()
    r.search_for(s.params.period_start, s.params.period_end, filler(1500, 1))
    r.search_for(_day(1), _day(1, 23, 59, 59), [A, B])
    r.search_for(_day(2), _day(2, 23, 59, 59), [Cc, D])
    done(s, r)

    # ---- STM (щоденний запис залишку рахунку, виміряно run1b/run2) і фільтр за рахунком
    def stm(n):
        return pdoc(g, own, n, when=at(0, 0, 0), type='STM', direction='INBOUND', amount='500.00', drop=('senderIBAN', 'correspondentIBAN'))
    s, r = new('СинтПУМБSTM', 'ПУМБ: документи STM (щоденний запис залишку рахунку, виміряно run1b/run2) -- не операції і без Предупреждение; решта документів -- як звичайно', [4])
    done(s, r.full([pdoc(g, own, 1, when=at(9), amount='10.00'), stm(2), stm(3), pdoc(g, own, 4, when=at(15), out=False, amount='40.00'), stm(5)]))
    s, r = new('СинтПУМБВалютаТипыДвижения', 'ПУМБ: валютний рахунок (USD): рух коштів -- CUR_ADV (авізо), поруч CUR, CUR_C, CUR_S (заявки, пара на гривневому рахунку) і STM (залишок) -- не операції і без Предупреждение (виміряно run4)', [4, 5])
    usd = lambda n, t, **kw: pdoc(g, own, n, when=at(8 + n), type=t, ccy='USD', amount='%d.00' % (10 * n), **kw)
    done(s, r.full([usd(1, 'CUR_ADV'), usd(2, 'CUR'), usd(3, 'CUR_C'), usd(4, 'CUR_ADV', out=False), usd(5, 'CUR_S'), usd(6, 'STM', drop=('senderIBAN', 'correspondentIBAN'))],
                   accounts=[own.account_item(currency='USD')]))
    s, r = new('СинтПУМБНеизвестныйТип', 'ПУМБ: у відповіді поруч зі звичайними документами два документи невідомого типу (різні дні) і ще один іншого невідомого типу -- відмова ВСЬОГО читання, «дія людини»; без операцій; діагностика називає перший невідомий тип, кількість його документів і найраніший день', [4],
               period_end=_day(2, 23, 59, 59))
    r.auth(); r.accounts()
    r.search_for(s.params.period_start, s.params.period_end, [pdoc(g, own, 1, when=at(9), amount='10.00'), pdoc(g, own, 2, when=at(10, d=2), type='CUR_NEW', amount='20.00'),
                                                              pdoc(g, own, 3, when=at(11), type='CUR_NEW', amount='30.00'), pdoc(g, own, 4, when=at(12), type='XFER_NEW', amount='40.00')])
    done(s, r)
    s, r = new('СинтПУМБТипПустой', 'ПУМБ: у документа порожній тип (поля type немає) -- невідомий тип: відмова ВСЬОГО читання, «дія людини», без операцій', [4])
    done(s, r.full([pdoc(g, own, 1, when=at(9), amount='10.00'), pdoc(g, own, 2, when=at(10), amount='20.00', drop=('type',))]))
    alt = '26009000000042'
    s, r = new('СинтПУМБНомерСчета', 'ПУМБ: документи без IBAN нашої сторони, але з номером рахунку = number (UAH, відправник) чи altNumber (CUR_ADV, одержувач) запитаного -- операції; номер чужий і IBAN немає (з direction і без нього) -- Ошибка no-iban, не операція', [4])
    done(s, r.full([pdoc(g, own, 1, when=at(9), type='UAH', amount='10.00', senderAccountNumber=own.iban[-14:], drop=('senderIBAN',)),
                    pdoc(g, own, 2, when=at(10), type='CUR_ADV', out=False, amount='20.00', correspondentAccountNumber=alt, drop=('senderIBAN', 'correspondentIBAN')),
                    pdoc(g, own, 3, when=at(11), type='CUR_ADV', amount='30.00', senderAccountNumber='26000000000000', drop=('senderIBAN', 'correspondentIBAN')),
                    pdoc(g, own, 4, when=at(12), type='CUR_ADV', amount='40.00', senderAccountNumber='26000000000000', drop=('senderIBAN', 'correspondentIBAN', 'direction'))],     # без direction: фільтр рахунку -- єдина перепона
                   accounts=[own.account_item(alt=alt)]))
    other_own = Own(g).iban                                            # IBAN іншого рахунку цієї ж компанії (переказ між своїми)
    s, r = new('СинтПУМБПереводМеждуСвоими', 'ПУМБ: переказ між своїми рахунками -- бік за запитаним рахунком, direction мусить збігтися: правильний (OUTBOUND / INBOUND) -- операції; хибний -- Ошибка direction-mismatch', [4])
    mate = dict(party(g), iban=other_own)
    done(s, r.full([pdoc(g, own, 1, when=at(9), out=True, cp=mate, amount='10.00'), pdoc(g, own, 2, when=at(10), out=False, cp=mate, amount='20.00'),
                    pdoc(g, own, 3, when=at(11), out=True, cp=mate, amount='30.00', direction='INBOUND'), pdoc(g, own, 4, when=at(12), out=False, cp=mate, amount='40.00', direction='OUTBOUND')]))
    s, r = new('СинтПУМБНетСвоегоСчета', 'ПУМБ: документ, у якому немає нашого IBAN і нашого номера рахунку (сторони -- чужі IBAN і чужі номери) -- Предупреждение foreign-account, не операція', [4])
    done(s, r.full([pdoc(g, own, 1, when=at(9), amount='10.00'),
                    pdoc(g, own, 2, when=at(10), amount='20.00', senderIBAN=party(g)['iban'], correspondentIBAN=party(g)['iban'], senderAccountNumber='26000000000001', correspondentAccountNumber='26000000000002'),
                    pdoc(g, own, 3, when=at(11), amount='30.00', out=False, senderIBAN=party(g)['iban'], correspondentIBAN=party(g)['iban'])]))

    # ---- кілька рахунків під одним IBAN (D36 п. 2, 8; виміряно run2: 14 рахунків, 11 IBAN): вибір за парою (IBAN, валюта) з Параметры.ВалютаСчета
    multi = [own.account_item(currency='USD', account_id=ACCOUNT_ID + 11), own.account_item(currency='UAH', account_id=ACCOUNT_ID)]      # гривневий -- ДРУГИМ: вибір «перший за IBAN» хибний
    s, r = new('СинтПУМБМультиВалюта', 'ПУМБ: під IBAN два рахунки (USD першим, UAH другим), ВалютаСчета = 980 -- пара (IBAN, валюта) однозначна: береться гривневий (accountId у documentAccounts), операції', [5])
    r.acc_id = ACCOUNT_ID
    done(s, r.full([pdoc(g, own, 1, when=at(9), amount='10.00'), pdoc(g, own, 2, when=at(10), out=False, amount='20.00')], accounts=multi))
    s, r = new('СинтПУМБМультиВалютаНетПары', 'ПУМБ: під IBAN два рахунки (USD, UAH), ВалютаСчета = 978 -- пари немає: ДействиеЧеловека до запиту виписки, searcher не йде', [5],
               account_currency_code='978')
    r.auth(); r.accounts(multi)
    done(s, r)
    s, r = new('СинтПУМБМультиВалютаПусто', 'ПУМБ: під IBAN два рахунки (USD, UAH), ВалютаСчета порожнє -- ДействиеЧеловека до запиту виписки, searcher не йде', [5],
               account_currency_code='')
    r.auth(); r.accounts(multi)
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
