# -*- coding: utf-8 -*-
"""Синтетичні записи відповідей API — для того, чого не запишеш безпечно (429, 5xx, HTML замість JSON, обрив, скасовані
й неостаточні операції, відсутні поля, межа доби й перехід часу, однакова секунда на межі сторінки).

Побудовані за схемою документації банків (`temp/research/2026-10-13-readers/docs/`: `privat.txt`, OpenAPI monobank
персонального API v250818 і corp-api v1.0.2), доки справжніх записів немає. Усі значення вигадані: коди — з
правильною контрольною сумою (генератори `sslib.gen`, валідатор незалежний: `python-stdnum` у тестах), назви — слова-
вигадки тієї ж форми. Ознака «синтетичний» — префікс `Синт` в ідентифікаторі (макет `СМП_ТестОтвет<Банк>Синт<Тема>`).

Генерація детермінована: той самий запис щоразу, бо еталон закомічений поруч із макетом.

Запис — рівно за `tools/api-recorder/FORMAT.md`; транспорт відтворення (задача 3) читає його так само, як справжній.
Запити, які записано, — ті, що зробив би конектор за Global Constraints (ПриватБанк: `limit=100`; monobank: відрізки
ФОП ≤ 31 доби, сторінки по 500 із зсувом верхньої межі). Генератор їх не «підглядає» в оракула: шляхи будуються тут
з тих самих правил, а `expected.verify_requests` це перевіряє.
"""
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import bankmodel, common as C, kyiv, recording as R
from .common import Params

import sslib.gen as sgen

BANK_KEYS = {'privat': 'Приват', 'mono-fop': 'МоноФОП', 'mono-corp': 'МоноЮр'}
HOSTS = {'privat': 'acp.privatbank.ua', 'mono-fop': 'api.monobank.ua', 'mono-corp': 'corp-api.monobank.ua'}
PRIVAT_LIMIT = 100
UA_PHRASES = [p for k in ('services', 'goods', 'other', 'tax') for p in sgen.PHRASES[k]]


@dataclass
class Scenario:
    bank: str
    sid: str                    # суфікс макета: Синт<Тема>
    title: str
    focus: list                 # номери рядків Review Focus, які покриває запис
    params: Params
    exchanges: list = field(default_factory=list)
    note: str = ''

    @property
    def name(self):
        return 'СМП_ТестОтвет%s%s' % (BANK_KEYS[self.bank], self.sid)

    @property
    def etalon_name(self):
        return 'СМП_ТестЭталон%s%s' % (BANK_KEYS[self.bank], self.sid)

    def recording(self):
        label = 'synth-%s-%s' % (self.bank, self.sid)
        m = R.make_manifest(self.bank, label, self.exchanges, note='synthetic: ' + self.title)
        return R.Recording(m, self.exchanges)


class Gen:
    """Вигадані значення. Один Gen на банк (seed = назва банку), тож ті самі вигадані особи повторюються між записами."""

    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.fk = sgen.Fakes(rng=self.rng, allowed_words=['ТОВ', 'ФОП', 'ПП', 'ПрАТ', 'АТ'])

    def digits(self, n, first_nonzero=True):
        s = ''.join(self.rng.choice('0123456789') for _ in range(n))
        return (self.rng.choice('123456789') + s[1:]) if first_nonzero else s

    def edrpou(self):
        p = self.digits(7)
        return p + sgen.edrpou_check_digit(p)

    def iban(self, mfo=None, core=None):
        mfo = mfo or self.digits(6)
        bban = mfo + (core or self.digits(19)).rjust(19, '0')
        return 'UA' + sgen.iban_check_digits('UA', bban) + bban

    def ipn(self):
        p = '%05d' % self.rng.randint(18000, 40000) + self.digits(4)
        return p + sgen.rnokpp_check_digit(p)

    def acc14(self):
        return '2600' + self.digits(10)

    def name(self, template='ТОВ "Вигадана Назва"'):
        return self.fk.name(template)

    def phrase(self):
        return self.rng.choice(UA_PHRASES)

    def b64id(self):
        a = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
        return ''.join(self.rng.choice(a) for _ in range(11)) + '='

    def uuid(self):
        h = '0123456789abcdef'
        g = lambda n: ''.join(self.rng.choice(h) for _ in range(n))
        return '%s-%s-4%s-a%s-%s' % (g(8), g(4), g(3), g(3), g(12))

    def receipt(self):
        a = 'ABCDEFGHJKLMNPQRSTUVWXYZ0123456789'
        return '-'.join(''.join(self.rng.choice(a) for _ in range(4)) for _ in range(4))

    def refid(self, n=12):
        return ''.join(self.rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ0123456789') for _ in range(n))

    def float_amount(self):
        """Залишок `balance` юросіб: число з плаваючою крапкою (run1: float з 1-2 знаками, не ціле)."""
        return float('%d.%02d' % (self.rng.randint(1000, 9999999), self.rng.choice((5, 25, 50, 75, 10, 99))))


def _j(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def _fmt_1c(dt):
    return dt.strftime('%d.%m.%Y %H:%M:%S')


def resp_json(status, obj, headers=(), charset='utf-8'):
    body = json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode(charset)
    return {'status': status, 'headers': [('content-type', 'application/json;charset=%s' % charset), *headers],
            'body': body}


def resp_html(status=200):
    html = ('<html><head><title>Proxy Error</title></head><body><h1>502 Bad Gateway</h1><p>The proxy server received an '
            'invalid response from an upstream server.</p></body></html>')
    return {'status': status, 'headers': [('content-type', 'text/html;charset=utf-8')], 'body': html.encode('utf-8')}


class Builder:
    """Збирає обміни запису: нумерує, називає сценарій, будує запити за правилами конектора."""

    def __init__(self, bank, sid, p):
        self.bank, self.sid, self.p = bank, sid, p
        self.ex = []

    def add(self, request, response=None, failure=None):
        seq = len(self.ex) + 1
        self.ex.append(R.make_exchange(seq, 'synth_%s_%s' % (self.bank.replace('-', '_'), self.sid),
                                       dict(request, method='GET', host=HOSTS[self.bank]), response, failure,
                                       started='2026-10-15T09:%02d:%02d.000Z' % (seq // 60, seq % 60)))

    # ---- запити
    def privat(self, resp=None, follow=None, failure=None):
        p = self.p
        q = 'acc=%s&startDate=%s&endDate=%s&limit=%d' % (p.account[-14:], p.period_start.strftime('%d-%m-%Y'),
                                                          p.period_end.strftime('%d-%m-%Y'), PRIVAT_LIMIT)
        if follow:
            q += '&followId=' + follow
        self.add({'path': C.PRIVAT_PATH, 'query': q}, resp, failure)

    def privat_pages(self, pages, charset='utf-8'):
        """Сторінки транзакцій: `exist_next_page` = true на всіх, крім останньої; `next_page_id` = ID останньої операції
        сторінки -- і на останній теж (run1, пункт 8); `followId` наступного запиту = `next_page_id` попередньої."""
        prev = None
        for i, txs in enumerate(pages):
            self.privat(resp_json(200, privat_page(txs, exist=(i < len(pages) - 1)), charset=charset), follow=prev)
            prev = txs[-1]['ID'] if txs else None

    def privat_balance(self, resp=None, failure=None):
        p = self.p
        self.add({'path': C.PRIVAT_BALANCE_PATH,
                  'query': 'acc=%s&startDate=%s&endDate=%s' % (p.account[-14:], p.period_start.strftime('%d-%m-%Y'),
                                                               p.period_end.strftime('%d-%m-%Y'))}, resp, failure)

    def settings(self, resp=None, failure=None):
        self.add({'path': C.PRIVAT_SETTINGS_PATH, 'query': ''}, resp, failure)

    def balances(self, resp=None, failure=None):
        p = self.p
        self.add({'path': '/ext/v1/accounts/%s/balances' % p.account,
                  'query': 'dateFrom=%s&dateTo=%s' % (p.period_start.strftime('%Y-%m-%d'), p.period_end.strftime('%Y-%m-%d'))},
                 resp, failure)

    def client_info(self, resp=None, failure=None):
        self.add({'path': C.FOP_CLIENT_INFO, 'query': ''}, resp, failure)

    def statement(self, frm, to, resp=None, failure=None, acct=None):
        if self.bank == 'mono-fop':
            self.add({'path': '/personal/statement/%s/%d/%d' % (acct or self.p_acct, frm, to), 'query': ''}, resp, failure)
        else:
            self.add({'path': '/ext/v1/statement/%s/%d/%d' % (self.p.account, frm, to), 'query': 'limit=%d' % C.CORP_WORKING_LIMIT},
                     resp, failure)

    p_acct = ''


SEAM_LIMIT = 30                      # поріг повної сторінки ФОП у записах із шовом розміру сторінки (≤ 500)


def seqid(prefix, i, width=4):
    """Послідовний ідентифікатор без цифрових серій (серія з 5+ цифр збіглася б із лексемами сторожа): цифри -> літери."""
    return '%s-%s' % (prefix, ''.join('abcdefghij'[int(c)] for c in '%0*d' % (width, i)))


def fid(prefix, i):
    """Ідентифікатор операції ФОП (форма справжніх: 12 символів base64 з `=`): префікс і літерний номер."""
    return seqid(prefix, i).ljust(11, '=') + '='


def privat_settings_body(final='30.10.2026 00:00:00', work_balance='N'):
    """Відповідь `/api/statements/settings` за privat.txt («Отримання серверних дат»); `final` — date_final_statement."""
    return {'status': 'SUCCESS', 'type': 'settings',
            'settings': {'phase': 'WRK', 'dates_without_oper_day': ['01.01.2026 00:00:00'], 'today': '15.10.2026 00:00:00',
                         'lastday': '14.10.2026 00:00:00', 'work_balance': work_balance, 'server_date_time': '15.10.2026 12:03:51',
                         'date_final_statement': final}}


def corp_balances_body(p, flags=None, absent=()):
    """Відповідь `balances` юросіб (corp-api): [{date, balance, isFinal}] за кожен день періоду, від старих до нових (run1:
    21 рядок на 21 добу, `balance` -- float). `flags` -- {день 'YYYY-MM-DD': isFinal}; за замовчуванням усі дні остаточні;
    `absent` -- дні, яких у відповіді немає."""
    out, day = [], datetime(p.period_start.year, p.period_start.month, p.period_start.day)
    last = datetime(p.period_end.year, p.period_end.month, p.period_end.day)
    while day <= last:
        key = day.strftime('%Y-%m-%d')
        if key not in absent:
            out.append({'date': key, 'balance': 1000050.25, 'isFinal': (flags or {}).get(key, True)})
        day += timedelta(days=1)
    return out


def privat_balance_body(p, flags=None, absent=()):
    """Відповідь `/api/statements/balance` ПриватБанку (run1, пункт 6): `balances[]` -- по рядку на добу періоду, від НОВИХ до
    старих; день рядка -- `dpd` (`DD.MM.YYYY 00:00:00`); `is_final_bal` -- bool. `flags` -- {день 'YYYY-MM-DD': is_final_bal};
    за замовчуванням усі дні остаточні; `absent` -- дні, яких у відповіді немає. Суми -- вигадані."""
    rows, day = [], datetime(p.period_start.year, p.period_start.month, p.period_start.day)
    last = datetime(p.period_end.year, p.period_end.month, p.period_end.day)
    while day <= last:
        key = day.strftime('%Y-%m-%d')
        if key not in absent:
            rows.append({'acc': p.account, 'atp': 'A', 'balanceIn': '1000.00', 'balanceInEq': '1000.00', 'balanceOut': '1000.00',
                         'balanceOutEq': '1000.00', 'bgfIBrnm': ' ', 'brnm': 'D1', 'currency': 'UAH',
                         'date_close_acc': '01.01.2100 00:00:00', 'date_open_acc_reg': '01.01.2020 00:00:00',
                         'date_open_acc_sys': '01.01.2020 00:00:00', 'dpd': day.strftime('%d.%m.%Y 00:00:00'), 'flmn': 'N1',
                         'is_final_bal': (flags or {}).get(key, True), 'nameACC': 'ТОВ "Вигадана Назва"', 'state': 'a',
                         'turnoverCred': '0.00', 'turnoverCredEq': '0.00', 'turnoverDebt': '0.00', 'turnoverDebtEq': '0.00'})
        day += timedelta(days=1)
    rows.reverse()
    return {'balances': rows, 'exist_next_page': False, 'status': 'SUCCESS', 'type': 'balances'}


def privat_error_body(code, app_code, message):
    """Тіло помилки ПриватБанку, СПОСТЕРЕЖЕНЕ в run1 (пункт 12): HTTP 4xx, `status: ERROR`, `code` -- HTTP-код рядком,
    `appErrorCode`, `requestId`; `serviceCode` немає."""
    return {'status': 'ERROR', 'code': str(code), 'message': message, 'requestId': '20261015_101010_ab12', 'appErrorCode': app_code}


def to_unix(local):
    return kyiv.local_to_unix(local)


def next_to(earliest_unix):
    """`to` наступного запиту після повної сторінки: УниверсальноеВремя(МестноеВремя(найраніший time)) (MF:456, 462)."""
    return kyiv.local_to_unix(kyiv.unix_to_local(earliest_unix))


# ====================================================================== побудова записів транзакцій
def ptx(g, own, *, when, tran, state='r', amount='100.00', ccy='UAH', ref=None, refn='1', num=None, osnd=None,
        cnt_acc=None, cnt_name='', cnt_crf='', cnt_mfo='305299', my_name='ТОВ "Вигадана Назва"', my_crf='', my_mfo='305299',
        pid=None, tech=None, drop=()):
    """Транзакція ПриватБанку за схемою `privat.txt` і run1. `own` та `cnt_acc` -- IBAN (run1: `AUT_MY_ACC` і `AUT_CNTR_ACC`
    -- IBAN у 87 з 87). `ID` = `TECHNICAL_TRANSACTION_ID` (run1: 87 з 87, 30 символів) і починається з `REF` (14 символів);
    `tech` задає ІНШЕ значення -- лише для синтетики «на випадок, не спостерігалось». `drop` -- поля, яких немає."""
    ref = ref or 'DN' + g.refid(12)
    pid = pid or ref + g.digits(30 - len(ref))
    d = {'AUT_MY_CRF': my_crf, 'AUT_MY_MFO': my_mfo, 'AUT_MY_ACC': own, 'AUT_MY_NAM': my_name,
         'AUT_MY_MFO_NAME': 'АТ КБ "ПРИВАТБАНК"', 'AUT_MY_MFO_CITY': 'Київ',
         'AUT_CNTR_CRF': cnt_crf, 'AUT_CNTR_MFO': cnt_mfo, 'AUT_CNTR_ACC': cnt_acc or g.iban(), 'AUT_CNTR_NAM': cnt_name,
         'AUT_CNTR_MFO_NAME': 'АТ КБ "ПРИВАТБАНК"', 'AUT_CNTR_MFO_CITY': 'Київ', 'CCY': ccy, 'FL_REAL': 'r',
         'PR_PR': state, 'DOC_TYP': 'm', 'NUM_DOC': num or ('K' + g.digits(9)), 'DAT_KL': when.strftime('%d.%m.%Y'),
         'DAT_OD': when.strftime('%d.%m.%Y'), 'OSND': osnd if osnd is not None else g.phrase(), 'SUM': amount,
         'SUM_E': amount, 'REF': ref, 'REFN': refn, 'TIM_P': when.strftime('%H:%M'),
         'DATE_TIME_DAT_OD_TIM_P': _fmt_1c(when), 'ID': pid, 'TRANTYPE': tran, 'DLR': 'J' + g.digits(8),
         'TECHNICAL_TRANSACTION_ID': tech or pid, 'UETR': g.uuid(), 'ULTMT': 'N'}
    for k in drop:
        d.pop(k, None)
    return d


def privat_page(txs, exist=False, with_id=True):
    """Сторінка транзакцій ПриватБанку. `next_page_id` = ID останньої операції сторінки і на ОСТАННІЙ сторінці також (run1,
    пункт 8); на порожній сторінці його немає. `with_id=False` -- лише для синтетики «є ще, а продовжити нічим»."""
    body = {'status': 'SUCCESS', 'type': 'transactions', 'exist_next_page': bool(exist)}
    if txs and with_id:
        body['next_page_id'] = txs[-1]['ID']
    body['transactions'] = txs
    return body


def ftx(g, *, t, amount, desc, hold=False, comment=None, cnt=None, fee=0, cash=0, ccy=980, tid=None):
    """Транзакція monobank ФОП (`StatementItem`, v250818). `comment` None — поля немає (документація: «поле буде
    відсутнім»); `cnt` = (iban, edrpou, name) або None."""
    d = {'id': tid or g.b64id(), 'time': t, 'description': desc, 'mcc': 7997, 'originalMcc': 7997, 'hold': hold,
         'amount': amount, 'operationAmount': amount, 'currencyCode': ccy, 'commissionRate': fee, 'cashbackAmount': cash,
         'balance': 10050000}
    if comment is not None:
        d['comment'] = comment
    if cnt:
        d['counterIban'], d['counterEdrpou'], d['counterName'] = cnt
    return d


def ctx_(g, *, t, amount, desc, status='DONE', done=None, reverse=False, cnt=None, ccy='980', tid=None, ult=None,
         drop=()):
    """Транзакція monobank юросіб (`StatementItem`, corp-api v1.0.2)."""
    d = {'id': tid or g.uuid(), 'externalReference': 'ext-' + g.digits(5), 'time': t}
    if done is not None:
        d['completedTime'] = done
    d.update({'description': desc, 'amount': amount, 'currencyCode': ccy, 'receiptId': g.receipt()})
    if cnt:
        d['counterEdrpou'], d['counterIban'], d['counterName'] = cnt
    d['reverse'] = reverse
    d['status'] = status
    if ult:
        d['ultimateDebit'] = ult
    for k in drop:
        d.pop(k, None)
    return d


def utc(y, mo, d, h=0, mi=0, s=0):
    return int((datetime(y, mo, d, h, mi, s) - kyiv.EPOCH).total_seconds())


def corp_paged(b, p, ops, limit, first_headers=(), stop_after=None):
    """Обміни виписки юросіб, які дав би банк (модель `bankmodel.CorpBank`, лише виміряне) на запити конектора за D36 п. 11
    (`44d22a1` і рішення за рев'ю): `to` наступного запиту = Мин(найраніша `time` сторінки + 1, поточна `to`) (межова секунда
    охоплюється вдруге, повтори відкидає конектор за `id`); повна сторінка, що лежить в одній секунді (продовження збіглося б із поточним), -- застряглий курсор:
    читання йде далі з `to` = ця секунда (виключна). Кінець -- сторінка, коротша за `limit`, або `to` не вище за початок."""
    bank = bankmodel.CorpBank(ops)
    frm, upper, first = to_unix(p.period_start), to_unix(p.period_end), True
    while True:
        page = bank.statement(frm, upper, limit)
        b.statement(frm, upper, resp_json(200, page, first_headers if first else ()))
        first = False
        if len(page) < limit or (stop_after is not None and len(b.ex) >= stop_after):
            return
        earliest = min(o['time'] for o in page)
        nxt = min(earliest + 1, upper)                   # межа продовження = Мин(E + 1, U)
        if nxt >= upper:                                 # запит продовження збігся б із поточним: застряг; крок -- Мин(E, U - 1)
            nxt = min(earliest, upper - 1)
        if nxt <= frm:
            return
        upper = nxt


def fop_paged(b, p, ops, limit, stop_after=None, from_inclusive=True):
    """Обміни виписки ФОП, які дав би банк (модель `bankmodel.FopBank`) на запити конектора: відрізки ≤ 31 доби, усередині кожного --
    сторінки за D36 п. 11, як у юросіб (`corp_paged`); відрізки -- від найновішого, сусідні перекриваються на секунду (`C.fop_windows`): `to` продовження = Мин(найраніша `time` + 1, поточна `to`), застрягання -- крок
    Мин(E, U - 1). У запиті ФОП ліміту немає: `limit` -- поріг повної сторінки (шов розміру сторінки, `Params.page_limit`)."""
    bank = bankmodel.FopBank(ops, from_inclusive=from_inclusive)
    for frm, upper in C.fop_windows(to_unix(p.period_start), to_unix(p.period_end)):
        while True:
            page = bank.statement(frm, upper, limit)
            b.statement(frm, upper, resp_json(200, page))
            if len(page) < limit or (stop_after is not None and len(b.ex) >= stop_after):
                break
            earliest = min(o['time'] for o in page)
            nxt = min(earliest + 1, upper)
            if nxt >= upper:
                nxt = min(earliest, upper - 1)
            if nxt <= frm:
                break
            upper = nxt


def desc_ordered(items):
    """monobank віддає від нових до старих (MU:344-347; спостереження попередника)."""
    return sorted(items, key=lambda x: -x['time'])


# ====================================================================== перелік сценаріїв
def all_scenarios():
    out = []
    out += _privat_scenarios()
    out += _fop_scenarios()
    out += _corp_scenarios()
    return out


def by_name(name):
    for s in all_scenarios():
        if s.sid == name or s.name == name:
            return s
    raise KeyError(name)


def _day(y, m, d, h=0, mi=0, s=0):
    return datetime(y, m, d, h, mi, s)


# ---------------------------------------------------------------------- ПриватБанк
PEND_REF = 'DNPENDAB2CDE1A'                         # 14 символів, як REF у run1
PEND_ID = PEND_REF + '5570010020030040'             # ID починається з REF, 30 символів (run1)
ORIG_REF = 'DNORIGAB1CDE1A'


def _privat_params(g):
    core = g.acc14()
    return Params(account=g.iban('305299', core), period_start=_day(2026, 10, 15), period_end=_day(2026, 10, 15, 23, 59, 59),
                  old_account_currency='980')


def _privat_scenarios():
    g = Gen('privat')
    base = _privat_params(g)
    acct = base.account                           # AUT_MY_ACC -- IBAN (run1: 87 з 87), у базі теж IBAN
    sc = []

    def new(sid, title, focus, settings=True, **kw):
        """R14: `/settings` -- обов'язковий перший обмін кожного читання ПриватБанку (`settings=False` -- сценарій додає свій)."""
        p = Params(**{**base.__dict__, **kw})
        b = Builder('privat', sid, p)
        if settings:
            b.settings(resp_json(200, privat_settings_body()))
        return Scenario('privat', sid, title, focus, p), b

    def done(s, b, balance=True, **kw):
        """Успішне читання закінчується обміном `/balance` (банківська межа, D36 п. 10); збій -- без нього."""
        if balance:
            b.privat_balance(resp_json(200, privat_balance_body(s.params, **kw)))
        s.exchanges = b.ex
        sc.append(s)

    day = _day(2026, 10, 15)
    cnt = lambda: dict(cnt_acc=g.iban(), cnt_name=g.name(), cnt_crf=g.edrpou())

    # --- Статусы: p, n, t (випадок а і б), чужий рахунок, напрями, 00:30
    s, b = new('СинтСтатусы', 'ПриватБанк: PR_PR r/p/n/t, реверс як окремий запис і як зміна стану, чужий рахунок '
                              '(p, n, t, чужий рахунок -- документальний, не спостерігалось)', [1, 2])
    orig = ptx(g, acct, when=day.replace(hour=0, minute=30), tran='D', amount='250.50', ref=ORIG_REF, refn='1', **cnt())
    rows1 = [ptx(g, acct, when=day.replace(hour=10, minute=15), tran='C', amount='1500.00', **cnt()),
             orig,
             ptx(g, acct, when=day.replace(hour=12), tran='C', state='p', amount='77.70', ref=PEND_REF, refn='1', pid=PEND_ID, **cnt()),
             ptx(g, acct, when=day.replace(hour=12, minute=5), tran='C', state='n', amount='19.99', **cnt()),
             ptx(g, acct, when=day.replace(hour=12, minute=30), tran='C', state='t', amount='40.00', **cnt())]
    rows2 = [ptx(g, acct, when=day.replace(hour=13), tran='C', state='t', amount='250.50', ref=ORIG_REF, refn='1',
                 pid=orig['ID'], **cnt()),                                        # (б): той самий ідентифікатор, що в оригіналу
             ptx(g, g.iban(), when=day.replace(hour=14), tran='C', amount='5.00', **cnt()),
             ptx(g, acct, when=day.replace(hour=15), tran='D', amount='8.40', **cnt())]
    b.privat_pages([rows1, rows2])
    done(s, b)

    # --- Повтор: той самий період наступного разу; p уже проведена, той самий ідентифікатор (run1: ID = TECHNICAL_TRANSACTION_ID)
    s, b = new('СинтПовтор', 'ПриватБанк: друге читання, p стала r: той самий ID (p -- документальний, не спостерігалось)', [2])
    b.privat_pages([[ptx(g, acct, when=day.replace(hour=12), tran='C', amount='77.70', ref=PEND_REF, refn='1', pid=PEND_ID, **cnt()),
                     ptx(g, acct, when=day.replace(hour=16), tran='D', amount='15.00', **cnt())]])
    done(s, b)

    s, b = new('СинтПовторТехнический', 'ПриватБанк: друге читання, ID той самий, а TECHNICAL_TRANSACTION_ID інший '
                                        '[на випадок, не спостерігалось: у run1 вони збігаються]', [2])
    b.privat_pages([[ptx(g, acct, when=day.replace(hour=12), tran='C', amount='77.70', ref=PEND_REF, refn='1', pid=PEND_ID,
                         tech=PEND_ID + '_final', **cnt()),
                     ptx(g, acct, when=day.replace(hour=16), tran='D', amount='15.00', **cnt())]])
    done(s, b)

    # --- Поля: відсутні поля, довге призначення, нульова сума, 00:30 і 23:59:59, cp1251
    s, b = new('СинтПоля', 'ПриватБанк: немає OSND/назви/ЄДРПОУ контрагента, призначення > 255, нульова сума, межі доби '
                           '(у run1 0 операцій у 00:00-02:59, секунди завжди 00), cp1251', [1, 5])
    long_text = ' '.join(['платіж за послуги згідно договору і додаткової угоди'] * 6)
    rows = [ptx(g, acct, when=day.replace(hour=0, minute=30), tran='D', amount='3.00', drop=('OSND', 'AUT_CNTR_NAM'),
                cnt_crf='', cnt_acc=g.iban()),
            ptx(g, acct, when=day.replace(hour=23, minute=59, second=59), tran='C', amount='1.00', **cnt()),
            ptx(g, acct, when=day.replace(hour=9), tran='C', amount='2500.75', osnd=long_text, **cnt()),
            ptx(g, acct, when=day.replace(hour=9, minute=1), tran='C', amount='0.00', **cnt()),
            ptx(g, acct, when=day.replace(hour=9, minute=2), tran='D', amount='12.00', cnt_acc=g.iban(),
                cnt_name=g.name('ФОП Ааааааа Бббб Ввввввв'), cnt_crf=g.ipn())]
    b.privat_pages([rows], charset='cp1251')
    done(s, b)

    # --- Страницы: рівно limit записів на сторінці, порожня друга сторінка
    s, b = new('СинтСтраницы', 'ПриватБанк: сторінка рівно в limit (100) записів, наступна сторінка порожня', [3])
    rows = [ptx(g, acct, when=day + timedelta(minutes=i), tran='C' if i % 2 else 'D', amount='%d.%02d' % (i + 1, i),
                osnd='оплата %d' % i, cnt_acc=g.iban('305299', '2600' + '%010d' % (7000000000 + i)), cnt_name='ТОВ Склад')
            for i in range(PRIVAT_LIMIT)]
    b.privat_pages([rows, []])
    done(s, b)

    s, b = new('СинтСтраницыСлед', 'ПриватБанк: кілька сторінок, остання несе next_page_id при exist_next_page = false (run1, пункт 8)', [3])
    pages = [[ptx(g, acct, when=day.replace(hour=8 + i, minute=j), tran='C', amount='%d.00' % (10 * i + j + 1), **cnt())
              for j in range(3)] for i in range(3)]
    b.privat_pages(pages)
    done(s, b)

    s, b = new('СинтБезСледующей', 'ПриватБанк: exist_next_page = true без next_page_id (продовжити нічим)', [3])
    b.privat(resp_json(200, privat_page([ptx(g, acct, when=day.replace(hour=11), tran='C', amount='9.00', **cnt())], exist=True,
                                        with_id=False)))
    done(s, b, balance=False)

    s, b = new('СинтПусто', 'ПриватБанк: порожня відповідь', [3])
    b.privat_pages([[]])
    done(s, b)

    # --- Валюта: рахунок у USD
    # У базі довідник валют без елемента «USD» (умова відступу dev6): попередник дає порожній код і відкидає рядки.
    own_usd = g.iban('305299', g.acc14())
    s, b = new('СинтВалюта', 'ПриватБанк: валютний рахунок USD (довідник валют бази без USD; у run1 рядків чужої валюти 0)', [5],
               account=own_usd, old_account_currency='840', old_currency_catalog={})
    b.privat_pages([[ptx(g, own_usd, when=day.replace(hour=10), tran='C', ccy='USD', amount='1200.00', **cnt()),
                     ptx(g, own_usd, when=day.replace(hour=11), tran='D', ccy='USD', amount='33.33', **cnt())]])
    done(s, b)

    # --- Збої посеред читання
    two = lambda: [ptx(g, acct, when=day.replace(hour=10), tran='C', amount='10.00', **cnt()),
                   ptx(g, acct, when=day.replace(hour=11), tran='D', amount='20.00', **cnt())]

    def failing_second_page(sid, title, resp=None, failure=None):
        s, b = new(sid, title, [4])
        first = two()
        b.privat(resp_json(200, privat_page(first, exist=True)))
        b.privat(resp, follow=first[-1]['ID'], failure=failure)
        done(s, b, balance=False)

    failing_second_page('СинтОбрыв500', 'ПриватБанк: HTTP 500 на другій сторінці (5xx -- документальний, не спостерігалось)',
                        resp_json(500, {'message': 'Service temporarily unavailable'}))
    failing_second_page('СинтНеJSON', 'ПриватБанк: HTML проксі замість JSON на другій сторінці', resp_html(200))
    failing_second_page('СинтТаймаут', 'ПриватБанк: таймаут на другій сторінці', None,
                        {'kind': 'timeout', 'text': 'The request was canceled due to the configured timeout of 60 seconds elapsing'})
    failing_second_page('СинтОшибкаСтатус', 'ПриватБанк: status = ERROR при HTTP 200, тимчасова помилка сервісу '
                                            '[документальний, не спостерігалось: у run1 помилки -- HTTP 4xx]',
                        resp_json(200, {'status': 'ERROR', 'type': 'transactions', 'code': '500',
                                        'message': 'Search error: temporary failure', 'requestId': '20261015_101010_abcd',
                                        'serviceCode': 'SERVICE_ERROR_LOCAL_JOURNAL'}))

    s, b = new('СинтОшибкаАвторизация', 'ПриватБанк: status = ERROR при HTTP 200, автентифікація (CLIENT_AUTH_P24_NOT_VALID) '
                                        '[документальний, не спостерігалось: у run1 помилки -- HTTP 4xx]', [4])
    b.privat(resp_json(200, {'status': 'ERROR', 'type': 'transactions', 'code': '401', 'message': 'Invalid token',
                             'requestId': '20261015_101011_abce', 'serviceCode': 'CLIENT_AUTH_P24_NOT_VALID'}))
    done(s, b, balance=False)

    s, b = new('СинтДубль', 'ПриватБанк: та сама операція на двох сторінках (однаковий запис і ID)', [3])
    x = ptx(g, acct, when=day.replace(hour=10), tran='C', amount='11.00', **cnt())
    b.privat_pages([[x, ptx(g, acct, when=day.replace(hour=11), tran='D', amount='12.00', **cnt())],
                    [x, ptx(g, acct, when=day.replace(hour=12), tran='C', amount='13.00', **cnt())]])
    done(s, b)

    # --- Помилки HTTP 4xx, СПОСТЕРЕЖЕНІ в run1: status ERROR, code = HTTP-код рядком, appErrorCode, без serviceCode
    for sid, title, code, app, msg in (
            ('СинтТокен401', 'ПриватБанк: недійсний токен -- HTTP 401, SE004 (спостережено)', 401, 'SE004', 'Invalid token'),
            ('СинтПериод400', 'ПриватБанк: початок пізніше за кінець -- HTTP 400, VE017 (спостережено)', 400, 'VE017',
             'Some request fields are not valid: startDate must not be after endDate'),
            ('СинтЧужойСчет403', 'ПриватБанк: чужий / неіснуючий рахунок -- HTTP 403, SE013 (спостережено)', 403, 'SE013',
             'Access to the account is denied')):
        s, b = new(sid, title, [4])
        b.privat(resp_json(code, privat_error_body(code, app, msg)))
        done(s, b, balance=False)

    s, b = new('СинтНастройкиСбой', 'ПриватБанк: збій обміну /settings (HTTP 500)', [4], settings=False)
    b.settings(resp_json(500, {'message': 'Service temporarily unavailable'}))
    done(s, b, balance=False)

    s, b = new('СинтРегламентБанка', 'ПриватБанк: /settings з work_balance = Y (іде регламент банку; у run1 N) -- запитів транзакцій немає', [4],
               settings=False)
    b.settings(resp_json(200, privat_settings_body(work_balance='Y')))
    done(s, b, balance=False)

    s, b = new('СинтБалансыСбой', 'ПриватБанк: транзакції прочитано, збій обміну /balance (HTTP 500)', [4])
    b.privat_pages([two()])
    b.privat_balance(resp_json(500, {'message': 'Service temporarily unavailable'}))
    done(s, b, balance=False)

    # --- Межа довіри (D36 п. 10): початок першого дня без is_final_bal = true; date_final_statement у межі не бере участі
    s, b = new('СинтГраницаПриват', 'ПриватБанк: ГраницаДоверия за /balance (13, 14 остаточні, 15 -- ні; p пізніше), '
                                    'date_final_statement далеко в минулому (як у run1) і на межу не впливає', [2],
               settings=False, period_start=_day(2026, 10, 13), period_end=_day(2026, 10, 15, 23, 59, 59))
    b.settings(resp_json(200, privat_settings_body(final='01.04.2026 00:00:00')))
    b.privat_pages([[ptx(g, acct, when=_day(2026, 10, 13, 10), tran='C', amount='100.00', **cnt()),
                     ptx(g, acct, when=_day(2026, 10, 14, 10), tran='D', amount='20.00', **cnt()),
                     ptx(g, acct, when=_day(2026, 10, 15, 12), tran='C', state='p', amount='5.00', **cnt())]])
    done(s, b, flags={'2026-10-15': False})

    s, b = new('СинтГраницаДыра', 'ПриватБанк: /balance з діркою (is_final_bal: так, ні, так, ні) -- межа на першому неостаточному дні', [2],
               period_start=_day(2026, 10, 14), period_end=_day(2026, 10, 17, 23, 59, 59))
    b.privat_pages([[ptx(g, acct, when=_day(2026, 10, 14, 8), tran='D', amount='10.00', **cnt())]])
    done(s, b, flags={'2026-10-15': False, '2026-10-17': False})

    s, b = new('СинтГраницаНетДня', 'ПриватБанк: у /balance немає рядка за 14.10 (день без рядка -- неостаточний; у run1 дірок немає)', [2],
               period_start=_day(2026, 10, 13), period_end=_day(2026, 10, 15, 23, 59, 59))
    b.privat_pages([[ptx(g, acct, when=_day(2026, 10, 13, 8), tran='D', amount='10.00', **cnt())]])
    done(s, b, absent=['2026-10-14'])
    return sc


# ---------------------------------------------------------------------- monobank ФОП
def _fop_scenarios():
    g = Gen('mono-fop')
    iban = g.iban()
    acct_id = g.b64id()[:-1]
    sc = []

    def new(sid, title, focus, start=_day(2026, 10, 14), end=_day(2026, 10, 15, 23, 59, 59), account=None, **kw):
        p = Params(account=account or iban, period_start=start, period_end=end, old_account_currency='980', **kw)
        s = Scenario('mono-fop', sid, title, focus, p)
        b = Builder('mono-fop', sid, p)
        b.p_acct = acct_id
        return s, b

    def info(b, acc_iban=None, status=200, body=None):
        accs = [{'id': acct_id, 'sendId': 'x' + g.digits(5), 'currencyCode': 980, 'cashbackType': 'None', 'balance': 10050000,
                 'creditLimit': 0, 'maskedPan': [], 'type': 'fop', 'iban': acc_iban or iban}]
        b.client_info(resp_json(status, body if body is not None else {'clientId': g.digits(10), 'name': g.name('Іван Вигаданий'),
                                                                        'webHookUrl': '', 'permissions': 'psf', 'accounts': accs,
                                                                        'jars': []}))

    t0 = utc(2026, 10, 14, 8)             # довільний ранок 14.10 за UTC
    cnt = lambda: (g.iban(), g.edrpou(), g.name())

    def one(b, items, start, end):
        b.statement(to_unix(start), to_unix(end), resp_json(200, desc_ordered(items)))

    # --- Статусы
    s, b = new('СинтСтатусы', 'monobank ФОП: hold і проведені, обидва напрями (hold і від\'ємні суми -- документальний, не спостерігалось)', [2])
    info(b)
    items = [ftx(g, t=t0 + 60, amount=-12345, desc='Оплата за послуги', cnt=cnt(), tid='ZuHWzqkKGV1='),
             ftx(g, t=t0 + 600, amount=50000, desc='Надходження від покупця', comment='За товар', cnt=cnt(), tid='ZuHWzqkKGV2='),
             ftx(g, t=t0 + 1200, amount=-4200, desc='Утримання за картковою операцією', hold=True, cnt=cnt(), tid='ZuHWzqkKGV3='),
             ftx(g, t=t0 + 1800, amount=15000, desc='Надходження очікується', hold=True, cnt=cnt(), tid='ZuHWzqkKGV4=')]
    one(b, items, s.params.period_start, s.params.period_end)
    s.exchanges = b.ex
    sc.append(s)

    s, b = new('СинтПовтор', 'monobank ФОП: друге читання, hold знято, ті самі id', [2])
    info(b)
    items = [ftx(g, t=t0 + 1200, amount=-4200, desc='Утримання за картковою операцією', hold=False, cnt=cnt(), tid='ZuHWzqkKGV3='),
             ftx(g, t=t0 + 1800, amount=15000, desc='Надходження очікується', hold=False, cnt=cnt(), tid='ZuHWzqkKGV4=')]
    one(b, items, s.params.period_start, s.params.period_end)
    s.exchanges = b.ex
    sc.append(s)

    # --- Поля
    s, b = new('СинтПоля', 'monobank ФОП: немає comment/counter*, комісія і кешбек, призначення > 255, нульова сума', [5])
    info(b)
    long_desc = ' '.join(['оплата за надані послуги згідно договору'] * 8)
    items = [ftx(g, t=t0 + 60, amount=-100, desc='Без коментаря й контрагента'),
             ftx(g, t=t0 + 120, amount=-250000, desc='Картка', comment='Коментар користувача', fee=1050, cash=2000),
             ftx(g, t=t0 + 180, amount=70000, desc=long_desc, comment=long_desc, cnt=cnt()),
             ftx(g, t=t0 + 240, amount=0, desc='Нульова сума', cnt=cnt()),
             ftx(g, t=t0 + 300, amount=-1, desc='Копійка', comment='', cnt=cnt())]
    one(b, items, s.params.period_start, s.params.period_end)
    s.exchanges = b.ex
    sc.append(s)

    # --- Окна: 40 діб, початок 06:30, кінець 14:20:07 -- межі відрізків посеред доби; відрізки йдуть від найновішого, найстаріший порожній
    start, end = _day(2026, 9, 5, 6, 30), _day(2026, 10, 15, 14, 20, 7)
    s, b = new('СинтОкна', 'monobank ФОП: період 40 діб -- два відрізки з перекриттям на секунду, межа посеред доби, старіший порожній', [3], start=start, end=end)
    info(b)
    wins = C.fop_windows(to_unix(start), to_unix(end))
    b.statement(wins[0][0], wins[0][1], resp_json(200, desc_ordered([
        ftx(g, t=utc(2026, 10, 10, 9), amount=-5000, desc='Покупка', cnt=cnt()),
        ftx(g, t=utc(2026, 10, 12, 9), amount=9000, desc='Надходження', cnt=cnt())])))
    b.statement(wins[1][0], wins[1][1], resp_json(200, []))
    s.exchanges = b.ex
    sc.append(s)

    # --- Страницы: робоча сторінка 500 (документальна гіпотеза; без шва -- продуктовий шлях), три записи в одну секунду на межі
    # сторінки: друга сторінка повертає їх вдруге (повтор за id) і дві старіші
    s, b = new('СинтСтраницы', 'monobank ФОП: сторінка 500, три записи в одну секунду на межі, дубль на другій сторінці', [3])
    info(b)
    base_t = utc(2026, 10, 14, 6)
    newer = [ftx(g, t=base_t + 10 * i, amount=-(100 + i), desc='п%d' % i, tid=fid('P', i)) for i in range(1, 498)]
    boundary = [ftx(g, t=base_t, amount=-(900 + k), desc='межа%d' % k, tid=fid('B', k)) for k in range(3)]
    older = [ftx(g, t=base_t - 5, amount=-777, desc='до межі', tid='A-aaaab====='), ftx(g, t=base_t - 60, amount=555, desc='раніше', tid='A-aaaac=====')]
    fop_paged(b, s.params, newer + boundary + older, C.PAGE_SIZE_MONO)
    s.exchanges = b.ex
    sc.append(s)

    # --- Пагінація D36 п. 11 на меншій сторінці (шов розміру сторінки, `page_limit`): ті самі випадки, що в юросіб; модель банку -- `FopBank`
    lim = SEAM_LIMIT
    paged = lambda sid, title: new(sid, title, [3], page_limit=lim)

    s, b = paged('СинтСекундаРаспалась', "monobank ФОП: секунда розпалась між сторінками (дві операції на першій, п'ять на другій з повтором) -- кожна рівно раз")
    info(b)
    split_t = utc(2026, 10, 14, 6)
    newer = [ftx(g, t=split_t + 10 * i, amount=-(200 + i), desc='н%d' % i, tid=fid('N', i)) for i in range(1, lim - 1)]
    second = [ftx(g, t=split_t, amount=-(300 + k), desc='секунда%d' % k, tid=fid('S', k)) for k in range(5)]
    older = [ftx(g, t=split_t - 10 * i, amount=-(400 + i), desc='ст%d' % i, tid=fid('O', i)) for i in range(1, 5)]
    fop_paged(b, s.params, newer + second + older, lim)
    s.exchanges = b.ex
    sc.append(s)

    s, b = paged('СинтКратнаяСтраница', 'monobank ФОП: кількість операцій рівно дорівнює порогу -- друга сторінка лише повторює межову операцію')
    info(b)
    base_t = utc(2026, 10, 14, 6)
    fop_paged(b, s.params, [ftx(g, t=base_t + 10 * i, amount=-(100 + i), desc='к%d' % i, tid=fid('K', i)) for i in range(lim)], lim)
    s.exchanges = b.ex
    sc.append(s)

    s, b = paged('СинтПолнаяНаНачале', 'monobank ФОП: повна сторінка, усі операції на секунді початку відрізка -- застряглий курсор, «дія людини» (D36 п. 11)')
    info(b)
    fop_paged(b, s.params, [ftx(g, t=to_unix(s.params.period_start), amount=-(100 + i), desc='на початку %d' % i, tid=fid('S', i))
                             for i in range(lim)], lim)
    s.exchanges = b.ex
    sc.append(s)

    # Повна сторінка, усі операції на `time` = `to` запиту: сторінка записана вручну (модель з виключним `to` таких операцій не повернула б;
    # семантика `to` для цього випадку не виміряна). Межа продовження = поточна відразу; крок Мин(E, U - 1); старіші операції читаються далі.
    s, b = paged('СинтПолнаяНаTo', 'monobank ФОП: повна сторінка, усі операції на time = to запиту -- застряглий курсор, крок Мин(E, U - 1), старіші операції в конверті (D36 п. 11)')
    info(b)
    top = to_unix(s.params.period_end)
    on_to = [ftx(g, t=top, amount=-(100 + i), desc='на to %d' % i, tid=fid('T', i)) for i in range(lim)]
    below_to = [ftx(g, t=top - 100 - 10 * i, amount=-(400 + i), desc='нижче %d' % i, tid=fid('U', i)) for i in range(3)]
    b.statement(to_unix(s.params.period_start), top, resp_json(200, on_to))
    b.statement(to_unix(s.params.period_start), top - 1, resp_json(200, bankmodel.FopBank(on_to + below_to).statement(0, top - 1, lim)))
    s.exchanges = b.ex
    sc.append(s)

    # Застрягання посеред читання: сторінки з перекриттям межової секунди, далі сторінка, вся в секунді, де операцій більше за поріг
    s, b = paged('СинтЗастряла', 'monobank ФОП: застрягання посеред читання -- секунда з понад порогом операцій; старіші операції в конверті (D36 п. 11)')
    info(b)
    stuck_t = utc(2026, 10, 14, 6)
    newest = [ftx(g, t=stuck_t + 2020 + 20 * (lim - i), amount=-(500 + i), desc='а%d' % i, tid=fid('A', i)) for i in range(1, lim + 1)]
    middle = [ftx(g, t=stuck_t + 100 + 10 * (lim - i), amount=-(600 + i), desc='б%d' % i, tid=fid('M', i)) for i in range(1, lim)]
    crowd = [ftx(g, t=stuck_t, amount=-(700 + i), desc='ті самі %d' % i, tid=fid('Z', i)) for i in range(1, lim + 2)]
    below = [ftx(g, t=stuck_t - 30 * i, amount=-(800 + i), desc='вк%d' % i, tid=fid('V', i)) for i in range(1, 6)]
    fop_paged(b, s.params, newest + middle + crowd + below, lim)
    s.exchanges = b.ex
    sc.append(s)

    # ПОЗА виміряним (запобіжник; відповідь другої сторінки записана вручну як аномалія): банк проігнорував `to` і повернув `time` > `to`
    s, b = paged('СинтБанкИгнорируетTo', 'monobank ФОП: банк ігнорує to -- на другій сторінці time > to запиту (поза виміряним, запобіжник); перша сторінка лишається')
    info(b)
    anomaly_t = utc(2026, 10, 14, 6)
    first_page = [ftx(g, t=anomaly_t + 10 * i, amount=-(100 + i), desc='ан%d' % i, tid=fid('E', i)) for i in range(lim)]
    fop_paged(b, s.params, first_page, lim, stop_after=2)
    bad_to = anomaly_t + 1
    outside = [ftx(g, t=bad_to + 1 + i, amount=-(500 + i), desc='поза to %d' % i, tid=fid('I', i)) for i in range(lim)]
    b.statement(to_unix(s.params.period_start), bad_to, resp_json(200, sorted(outside, key=lambda o: -o['time'])))
    s.exchanges = b.ex
    sc.append(s)

    # Контроль до запобіжника: операції рівно на `time` = `to` і `time` = `from` -- НЕ аномалія (звичайні дані, кожна рівно раз)
    s, b = new('СинтОперацияНаTo', 'monobank ФОП: операції на time = to і time = from запиту -- не аномалія, звичайні дані; кожна рівно раз', [3])
    info(b)
    eq_from, eq_to = to_unix(s.params.period_start), to_unix(s.params.period_end)
    edge = [ftx(g, t=eq_to, amount=-1000, desc='на to', tid=fid('Q', 1)), ftx(g, t=utc(2026, 10, 14, 8), amount=2000, desc='всередині', tid=fid('Q', 2)),
            ftx(g, t=eq_from, amount=-3000, desc='на from', tid=fid('Q', 3))]
    b.statement(eq_from, eq_to, resp_json(200, sorted(edge, key=lambda o: -o['time'])))
    s.exchanges = b.ex
    sc.append(s)

    # Повна сторінка без читаного `time` (поза виміряним; вручну як аномалія): курсора немає, хоча «є ще» -- «повторити»
    s, b = paged('СинтПолнаяБезВремени', 'monobank ФОП: повна сторінка без читаного time -- курсора немає, «повторити» (поза виміряним)')
    info(b)
    no_time = [ftx(g, t=0, amount=-(100 + i), desc='без часу %d' % i, tid=fid('X', i)) for i in range(lim)]
    for x in no_time:
        x.pop('time')
    b.statement(to_unix(s.params.period_start), to_unix(s.params.period_end), resp_json(200, no_time))
    s.exchanges = b.ex
    sc.append(s)

    # Відрізки й сторінки разом: найновіший відрізок -- повна сторінка + хвіст, старіший -- дві операції. Пауза 60 с перед кожним запитом
    # виписки, крім першого. Період 05.09 06:30 .. 15.10 14:20:07, межа відрізків посеред доби
    start, end = _day(2026, 9, 5, 6, 30), _day(2026, 10, 15, 14, 20, 7)
    s, b = new('СинтОкнаСтраницы', 'monobank ФОП: два відрізки з перекриттям, у найновішому дві сторінки', [3], start=start, end=end, page_limit=lim)
    info(b)
    newest_seg = [ftx(g, t=utc(2026, 10, 10, 8) + 100 * i, amount=-(100 + i), desc='в%d' % i, tid=fid('W', i)) for i in range(1, lim + 2)]
    older_seg = [ftx(g, t=utc(2026, 9, 8, 9), amount=555, desc='старіша операція', tid=fid('Y', 1)),
                 ftx(g, t=utc(2026, 9, 20, 9), amount=9000, desc='Надходження', tid=fid('Y', 2))]
    fop_paged(b, s.params, newest_seg + older_seg, lim)
    s.exchanges = b.ex
    sc.append(s)

    # Операція на секунді межі відрізків (`from` новішого відрізка). Модель найгіршого випадку: `from` ВИКЛЮЧНИЙ (не виміряно), тож
    # новіший відрізок цієї операції не повертає, а старіший (`to` = `from` новішого + 1) повертає -- завдяки перекриттю вона в
    # конверті рівно раз. Без перекриття вона б загубилась.
    s, b = new('СинтГраницаОтрезков', 'monobank ФОП: операція на секунді межі відрізків -- від виключного from її повертає лише старіший відрізок (перекриття на секунду)', [3], start=start, end=end)
    info(b)
    boundary_t = C.fop_windows(to_unix(start), to_unix(end))[0][0]
    on_edge = [ftx(g, t=utc(2026, 10, 12, 9), amount=-1000, desc='новіша', tid=fid('G', 1)),
               ftx(g, t=boundary_t, amount=-2000, desc='на межі відрізків', tid=fid('G', 2)),
               ftx(g, t=utc(2026, 9, 10, 9), amount=3000, desc='старіша', tid=fid('G', 3))]
    fop_paged(b, s.params, on_edge, C.PAGE_SIZE_MONO, from_inclusive=False)
    s.exchanges = b.ex
    sc.append(s)

    # Кілька рахунків у client-info: потрібний -- не перший і не останній; ідентифікатор у шляху виписки -- його
    s, b = new('СинтНесколькоСчетов', 'monobank ФОП: у client-info кілька рахунків, потрібний IBAN -- другий; виписка за його ідентифікатором', [4])
    other_id = [g.b64id()[:-1], g.b64id()[:-1]]
    accs = [{'id': other_id[0], 'sendId': 'x' + g.digits(5), 'currencyCode': 840, 'cashbackType': 'None', 'balance': 100, 'creditLimit': 0,
             'maskedPan': [], 'type': 'fop', 'iban': g.iban()},
            {'id': acct_id, 'sendId': 'x' + g.digits(5), 'currencyCode': 980, 'cashbackType': 'None', 'balance': 10050000, 'creditLimit': 0,
             'maskedPan': [], 'type': 'fop', 'iban': iban},
            {'id': other_id[1], 'sendId': 'x' + g.digits(5), 'currencyCode': 978, 'cashbackType': 'None', 'balance': 200, 'creditLimit': 0,
             'maskedPan': [], 'type': 'fop', 'iban': g.iban()}]
    info(b, body={'clientId': g.digits(10), 'name': g.name('Іван Вигаданий'), 'webHookUrl': '', 'permissions': 'psf', 'accounts': accs, 'jars': []})
    one(b, [ftx(g, t=t0 + 60, amount=-2500, desc='Оплата', cnt=cnt())], s.params.period_start, s.params.period_end)
    s.exchanges = b.ex
    sc.append(s)

    # --- Час
    _fop_time(sc, new, info, one, g, cnt)

    # --- Валюта
    s, b = new('СинтВалюта', 'monobank ФОП: валютний рахунок USD', [5])
    info(b)
    one(b, [ftx(g, t=t0 + 60, amount=-5000, desc='Card USD', ccy=840, cnt=cnt()),
            ftx(g, t=t0 + 120, amount=120000, desc='Incoming USD', ccy=840, cnt=cnt())], s.params.period_start, s.params.period_end)
    s.exchanges = b.ex
    sc.append(s)

    # --- Збої
    _mono_failures(sc, new, info, one, g, cnt, 'mono-fop', t0)
    s, b = new('СинтСчетНеНайден', 'monobank ФОП: IBAN не знайдено в client-info', [4])
    info(b, acc_iban=g.iban())
    s.exchanges = b.ex
    sc.append(s)
    return sc


def _fop_time(sc, new, info, one, g, cnt):
    tz = lambda *a: utc(*a)
    spring = [tz(2026, 3, 27, 22, 30), tz(2026, 3, 28, 21, 59, 59), tz(2026, 3, 28, 22, 0, 0), tz(2026, 3, 29, 0, 59, 59),
              tz(2026, 3, 29, 1, 0, 0), tz(2026, 3, 29, 20, 59, 59), tz(2026, 3, 29, 21, 30)]
    s, b = new('СинтВремяВесна', 'monobank ФОП: 00:30 узимку й улітку, перехід 29.03 (доба 23 год, години 03:xx немає) (синтетика: у run1 0 операцій у 00:00-02:59 за Києвом)', [1],
               start=_day(2026, 3, 28), end=_day(2026, 3, 30, 23, 59, 59))
    info(b)
    items = [ftx(g, t=t, amount=-(1000 + 10 * i), desc='час %d' % i, cnt=cnt()) for i, t in enumerate(spring)]
    one(b, items, s.params.period_start, s.params.period_end)
    s.exchanges = b.ex
    sc.append(s)
    autumn = [tz(2026, 10, 24, 21, 30), tz(2026, 10, 25, 0, 30), tz(2026, 10, 25, 1, 30), tz(2026, 10, 25, 21, 59, 59),
              tz(2026, 10, 25, 22, 30)]
    s, b = new('СинтВремяОсень', 'monobank ФОП: 00:30 на переході 25.10 (доба 25 год), повторювана година 03:30 двічі (синтетика: у run1 0 операцій у 00:00-02:59 за Києвом)', [1],
               start=_day(2026, 10, 24), end=_day(2026, 10, 26, 23, 59, 59))
    info(b)
    items = [ftx(g, t=t, amount=-(2000 + 10 * i), desc='час %d' % i, cnt=cnt()) for i, t in enumerate(autumn)]
    one(b, items, s.params.period_start, s.params.period_end)
    s.exchanges = b.ex
    sc.append(s)


def _mono_failures(sc, new, info, one, g, cnt, bank, t0):
    """Збої посеред читання для monobank (спільна форма): 500, не JSON, таймаут, недійсний токен, 429 з повтором, 429 двічі.
    Форми тіл помилок -- СПОСТЕРЕЖЕНІ в run1 (пункт 12): ФОП -- лише `errorDescription`; юросіб -- `errorCode` ВЕЛИКИМИ літерами
    (BAD_REQUEST, INTERNAL_SERVER_ERROR), недійсний токен -- 400 text/plain без `errorCode`. 429 і camelCase-коди з
    документації в run1 не траплялися -- такі сценарії мають позначку «документальний»."""
    fop = bank == 'mono-fop'
    lim = C.page_limit(bank)

    def err(code_obs, desc):
        return {'errorDescription': desc} if fop else {'errorCode': code_obs, 'errorDescription': desc}

    def start(sid, title, focus):
        s, b = new(sid, title, focus)
        if fop:
            info(b)
        return s, b

    def good_page(count=2):
        return desc_ordered([(ftx if fop else ctx_)(g, t=t0 + 100 * (i + 1), amount=-(500 + i), desc='запис %d' % i,
                                                     cnt=cnt()) for i in range(count)])

    def full_page(prefix):
        return desc_ordered([ctx_(g, t=t0 + 7 * i, amount=-(10 + i), desc='x', tid=seqid(prefix, i)) for i in range(lim)])

    def failing(sid, title, resp=None, failure=None, full=False):
        """Збій на «сторінці N». ФОП: період 40 діб, збій у другому (старішому) відрізку (повна сторінка не потрібна, запис малий);
        юросіб: одного відрізка немає -- збій на другій сторінці (повна сторінка) лише в `full`, інакше на першому запиті."""
        if fop:
            start_, end_ = _day(2026, 9, 5), _day(2026, 10, 15)
            s, b = new(sid, title, [4], start=start_, end=end_)
            info(b)
            wins = C.fop_windows(to_unix(start_), to_unix(end_))
            octo = utc(2026, 10, 10, 8)
            b.statement(wins[0][0], wins[0][1], resp_json(200, desc_ordered(
                [ftx(g, t=octo + 100 * (i + 1), amount=-(500 + i), desc='запис %d' % i, cnt=cnt()) for i in range(2)])))
            b.statement(wins[1][0], wins[1][1], resp, failure)
        else:
            s, b = new(sid, title, [4])
            if full:
                page = full_page('E')
                b.statement(to_unix(s.params.period_start), to_unix(s.params.period_end), resp_json(200, page))
                b.statement(to_unix(s.params.period_start), min(x['time'] for x in page) + 1, resp, failure)    # D36 п. 11 (44d22a1): to = time + 1
            else:
                b.statement(to_unix(s.params.period_start), to_unix(s.params.period_end), resp, failure)
        s.exchanges = b.ex
        sc.append(s)

    failing('СинтОбрыв500', '%s: HTTP 500 на %s%s' % (bank, 'другому відрізку' if fop else 'другій сторінці',
                                                      ' (5xx на даних -- документальний, не спостерігалось)'),
            resp_json(500, err('INTERNAL_SERVER_ERROR', 'Internal server error')), full=True)
    failing('СинтНеJSON', '%s: HTML проксі замість JSON на %s' % (bank, 'другому відрізку' if fop else 'першому запиті'), resp_html(200))
    failing('СинтТаймаут', '%s: таймаут на %s' % (bank, 'другому відрізку' if fop else 'першому запиті'), None,
            {'kind': 'timeout', 'text': 'The request was canceled due to the configured timeout of 30 seconds elapsing'})

    if fop:
        s, b = new('СинтТокен403', 'monobank ФОП: недійсний токен -- HTTP 403, лише errorDescription (спостережено)', [4])
        b.client_info(resp_json(403, {'errorDescription': "Unknown 'X-Token'"}, charset='utf-8'))
        s.exchanges = b.ex
        sc.append(s)
        # параметри читання з початком пізніше за кінець (як у справжньому записі): конектор шле їх як є, один відрізок
        s, b = new('СинтПериод400', 'monobank ФОП: початок пізніше за кінець -- HTTP 400, лише errorDescription (спостережено)', [4],
                   start=_day(2026, 10, 15, 23, 59, 59), end=_day(2026, 10, 14))
        info(b)
        b.statement(to_unix(s.params.period_start), to_unix(s.params.period_end),
                    resp_json(400, {'errorDescription': "Value 'to' must be greater than 'from'"}))
        s.exchanges = b.ex
        sc.append(s)
        # конектор бере ідентифікатор із client-info за IBAN, тож «чужий» ідентифікатор у запиті не з'явиться; виписку на рахунок із
        # client-info банк відхиляє тим самим тілом (спостережено у run1 для чужого / неіснуючого ідентифікатора)
        s, b = start('СинтЧужойСчет400', 'monobank ФОП: виписка на рахунок із client-info відхилена -- HTTP 400, errorDescription (форма спостережена)', [4])
        b.statement(to_unix(s.params.period_start), to_unix(s.params.period_end), resp_json(400, {'errorDescription': 'invalid account'}))
        s.exchanges = b.ex
        sc.append(s)
    else:
        s, b = new('СинтТокен400', 'monobank юросіб: недійсний токен -- HTTP 400, text/plain, без errorCode (спостережено)', [4])
        b.statement(to_unix(s.params.period_start), to_unix(s.params.period_end),
                    {'status': 400, 'headers': [('content-type', 'text/plain; charset=utf-8')],
                     'body': json.dumps({'errorDescription': 'invalid token'}, separators=(',', ':')).encode('utf-8')})
        s.exchanges = b.ex
        sc.append(s)
        s, b = new('СинтТокен403', 'monobank юросіб: недійсний токен -- HTTP 403, errorCode forbidden [документальний, не спостерігалось]', [4])
        b.statement(to_unix(s.params.period_start), to_unix(s.params.period_end),
                    resp_json(403, {'errorCode': 'forbidden', 'errorDescription': 'Invalid or expired token'}))
        s.exchanges = b.ex
        sc.append(s)
        # параметри читання з початком пізніше за кінець (як у справжньому записі): конектор шле їх як є, запит у записі збігається
        s, b = new('СинтПериод400', 'monobank юросіб: початок пізніше за кінець -- HTTP 400, BAD_REQUEST (спостережено)', [4],
                   start=_day(2026, 10, 15, 23, 59, 59), end=_day(2026, 10, 14))
        b.statement(to_unix(s.params.period_start), to_unix(s.params.period_end),
                    resp_json(400, {'errorCode': 'BAD_REQUEST', 'errorDescription': 'From date should be less than to date'}))
        s.exchanges = b.ex
        sc.append(s)

    hdr = [('x-rate-limit-retry-after-seconds', '5')] if not fop else []   # ФОП: заголовка паузи документація не описує
    body429 = {'errorDescription': 'Too many requests'} if fop else {'errorCode': 'tooManyRequests', 'errorDescription': 'Too many requests'}
    s, b = start('СинтЛимит429', '%s: 429 із заголовком паузи, повтор вдається [документальний, не спостерігалось]' % bank, [4])
    b.statement(to_unix(s.params.period_start), to_unix(s.params.period_end), resp_json(429, body429, hdr))
    one(b, good_page(), s.params.period_start, s.params.period_end)
    s.exchanges = b.ex
    sc.append(s)

    s, b = start('СинтЛимит429Дважды', '%s: 429 і після повтору -- читання неповне [документальний, не спостерігалось]' % bank, [4])
    for _ in range(2):
        b.statement(to_unix(s.params.period_start), to_unix(s.params.period_end), resp_json(429, body429, hdr))
    s.exchanges = b.ex
    sc.append(s)


# ---------------------------------------------------------------------- monobank юросіб
def _corp_scenarios():
    g = Gen('mono-corp')
    iban = g.iban()
    sc = []

    def new(sid, title, focus, start=_day(2026, 10, 14), end=_day(2026, 10, 15, 23, 59, 59), account=None, **kw):
        p = Params(account=account or iban, period_start=start, period_end=end, old_account_currency='980', **kw)
        s = Scenario('mono-corp', sid, title, focus, p)
        return s, Builder('mono-corp', sid, p)

    t0 = utc(2026, 10, 14, 8)
    cnt = lambda: (g.edrpou(), g.iban(), g.name())

    def one(b, items, start, end, hdr=()):
        b.statement(to_unix(start), to_unix(end), resp_json(200, desc_ordered(items), hdr))

    s, b = new('СинтСтатусы', 'monobank юросіб: DONE, PENDING, DECLINED, реверс окремим записом і зміною стану', [2])
    orig = ctx_(g, t=t0 + 100, amount=-46500, desc='Оплата рахунку', done=t0 + 160, cnt=cnt(), tid='ab12cd34-ef56-4a78-b9c0-d1e2f3a4b5c6')
    items = [orig,
             ctx_(g, t=t0 + 200, amount=120000, desc='Надходження', done=t0 + 230, cnt=cnt(),
                  ult={'name': g.name('ТОВ "Кінцевий Платник"'), 'idCode': g.edrpou()}),
             ctx_(g, t=t0 + 300, amount=-1000, desc='Очікує обробки', status='PENDING', cnt=cnt()),
             ctx_(g, t=t0 + 400, amount=-2000, desc='Відхилено банком', status='DECLINED', cnt=cnt()),
             ctx_(g, t=t0 + 500, amount=7000, desc='Повернення коштів (окремий запис)', done=t0 + 520, reverse=True, cnt=cnt()),
             ctx_(g, t=t0 + 100, amount=46500, desc='Реверс оригіналу', done=t0 + 600, reverse=True, cnt=cnt(),
                  tid='ab12cd34-ef56-4a78-b9c0-d1e2f3a4b5c6'),
             ctx_(g, t=t0 + 700, amount=-3000, desc='Завершено раніше за створення (run1: 7 з 33, до -168 с)', done=t0 + 700 - 120,
                  cnt=cnt())]
    one(b, items, s.params.period_start, s.params.period_end)
    s.exchanges = b.ex
    sc.append(s)

    s, b = new('СинтПовтор', 'monobank юросіб: друге читання, PENDING став DONE з тим самим id', [2])
    one(b, [ctx_(g, t=t0 + 300, amount=-1000, desc='Очікує обробки', status='DONE', done=t0 + 4000, cnt=cnt(),
                 tid='cd34ef56-ab12-4b89-a1c2-e3f4a5b6c7d8')], s.params.period_start, s.params.period_end)
    s.exchanges = b.ex
    sc.append(s)

    s, b = new('СинтПоля', 'monobank юросіб: немає counterEdrpou/counterName/idCode/description, призначення > 255, нульова сума', [5])
    long_desc = ' '.join(['призначення операції за договором'] * 10)
    items = [ctx_(g, t=t0 + 60, amount=-500, desc='Без контрагента', done=t0 + 70, drop=('externalReference',)),
             ctx_(g, t=t0 + 120, amount=900, desc=long_desc, done=t0 + 130, cnt=cnt(),
                  ult={'name': g.name('ТОВ "Кінцевий Платник"')}),
             ctx_(g, t=t0 + 180, amount=0, desc='Нульова сума', done=t0 + 190, cnt=cnt()),
             ctx_(g, t=t0 + 240, amount=-300, desc='', done=t0 + 250, drop=('description',)),
             ctx_(g, t=t0 + 300, amount=-3300, desc='Без часу проведення', cnt=cnt())]
    one(b, items, s.params.period_start, s.params.period_end)
    s.exchanges = b.ex
    sc.append(s)

    lim = C.CORP_WORKING_LIMIT
    # Пагінацію будує модель банку (`bankmodel.CorpBank`, лише виміряне: порядок за спаданням `time`, `to` не повертає операцію з
    # `time = to`, обрізання за `limit`) на запити конектора за D36 п. 11: `to` наступного запиту = найраніша `time` + 1.
    s, b = new('СинтСтраницы', 'monobank юросіб: повна сторінка (ліміт) із трьома записами в одну секунду на межі; друга сторінка повертає їх вдруге (дубль) і дві старіші; ліміт вичерпано', [3])
    base_t = utc(2026, 10, 14, 6)
    newer = [ctx_(g, t=base_t + 10 * i, amount=-(100 + i), desc='п%d' % i, tid=seqid('P', i)) for i in range(1, lim - 2)]
    boundary = [ctx_(g, t=base_t, amount=-(900 + k), desc='межа%d' % k, tid=seqid('B', k)) for k in range(3)]
    older = [ctx_(g, t=base_t - 5, amount=-777, desc='до межі', tid='A-aaaab'), ctx_(g, t=base_t - 60, amount=555, desc='раніше', tid='A-aaaac')]
    corp_paged(b, s.params, newer + boundary + older, lim, [('x-rate-limit-remaining', '0'), ('x-rate-limit-retry-after-seconds', '2')])
    s.exchanges = b.ex
    sc.append(s)

    # секунда розпалась між сторінками (D36 п. 11, 44d22a1): з п'яти операцій однієї секунди на першу сторінку влізли дві, решта -- на
    # другій разом із повтором перших двох. Кожна операція секунди в конверті рівно один раз.
    s, b = new('СинтСекундаРаспалась', "monobank юросіб: секунда розпалась між сторінками (дві операції на першій, п'ять на другій з повтором) -- кожна рівно раз", [3])
    split_t = utc(2026, 10, 14, 6)
    newer = [ctx_(g, t=split_t + 10 * i, amount=-(200 + i), desc='н%d' % i, tid=seqid('N', i)) for i in range(1, lim - 1)]
    second = [ctx_(g, t=split_t, amount=-(300 + k), desc='секунда%d' % k, tid=seqid('S', k)) for k in range(5)]
    older = [ctx_(g, t=split_t - 10 * i, amount=-(400 + i), desc='ст%d' % i, tid=seqid('O', i)) for i in range(1, 5)]
    corp_paged(b, s.params, newer + second + older, lim)
    s.exchanges = b.ex
    sc.append(s)

    # кількість операцій рівно дорівнює ліміту (D36 п. 11): друга сторінка -- лише повтор межової операції (коротша за ліміт)
    s, b = new('СинтКратнаяСтраница', 'monobank юросіб: кількість операцій рівно дорівнює ліміту -- друга сторінка лише повторює межову операцію', [3])
    base_t = utc(2026, 10, 14, 6)
    corp_paged(b, s.params, [ctx_(g, t=base_t + 10 * i, amount=-(100 + i), desc='к%d' % i, tid=seqid('K', i)) for i in range(lim)], lim)
    s.exchanges = b.ex
    sc.append(s)

    # Повна сторінка в одній секунді на початку відрізка (D36 п. 11, 44d22a1): продовження збіглося б із поточним -- «дія людини»,
    # неповне читання; читання йде далі з межею в цю секунду (тут старших операцій немає). Припущення, не виміряне: операція
    # на секунді `from` повертається (нижня межа `from` у моделі не змодельована).
    # Повна сторінка, усі операції на `time` = `to` запиту (межа продовження = поточна відразу; крок після застрягання -- Мин(E, U - 1),
    # без «- 1» читання повторювало б той самий запит). Сторінка записана вручну: модель виміряного (`to` виключний) операцій на
    # `time` = `to` не повернула б; семантика `to` для цього випадку не виміряна. Старші операції читаються далі.
    s, b = new('СинтПолнаяНаTo', 'monobank юросіб: повна сторінка, усі операції на time = to запиту -- застряглий курсор, крок Мин(E, U - 1), старіші операції в конверті (D36 п. 11)', [3])
    top = to_unix(s.params.period_end)
    on_to = [ctx_(g, t=top, amount=-(100 + i), desc='на to %d' % i, tid=seqid('T', i)) for i in range(lim)]
    below_to = [ctx_(g, t=top - 100 - 10 * i, amount=-(400 + i), desc='нижче %d' % i, tid=seqid('U', i)) for i in range(3)]
    b.statement(to_unix(s.params.period_start), top, resp_json(200, on_to))
    b.statement(to_unix(s.params.period_start), top - 1, resp_json(200, bankmodel.CorpBank(on_to + below_to).statement(0, top - 1, lim)))
    s.exchanges = b.ex
    sc.append(s)

    s, b = new('СинтПолнаяНаНачале', 'monobank юросіб: повна сторінка, усі операції на секунді початку відрізка -- застряглий курсор, «дія людини» (D36 п. 11)', [3])
    corp_paged(b, s.params, [ctx_(g, t=to_unix(s.params.period_start), amount=-(100 + i), desc='на початку %d' % i, tid=seqid('S', i))
                              for i in range(lim)], lim)
    s.exchanges = b.ex
    sc.append(s)

    # ПОЗА виміряним (запобіжник; модель банку тут не застосовується, відповідь другої сторінки записана вручну як аномалія): банк
    # проігнорував `to` і повернув сторінку, де є `time` > `to` запиту. Відповідь за межами запиту в конверт не береться, раніше
    # прочитана перша сторінка лишається; читання неповне, «повторити» (D36 п. 8 і рішення за рев'ю задачі 4).
    s, b = new('СинтБанкИгнорируетTo', 'monobank юросіб: банк ігнорує to -- на другій сторінці time > to запиту (поза виміряним, запобіжник); перша сторінка лишається', [3])
    anomaly_t = utc(2026, 10, 14, 6)
    first_page = [ctx_(g, t=anomaly_t + 10 * i, amount=-(100 + i), desc='ан%d' % i, tid=seqid('E', i)) for i in range(lim)]
    corp_paged(b, s.params, first_page, lim, stop_after=1)
    bad_to = anomaly_t + 1                                       # to другого запиту = найраніша time першої сторінки + 1
    outside = [ctx_(g, t=bad_to + 1 + i, amount=-(500 + i), desc='поза to %d' % i, tid=seqid('I', i)) for i in range(lim)]
    b.statement(to_unix(s.params.period_start), bad_to, resp_json(200, sorted(outside, key=lambda o: -o['time'])))
    s.exchanges = b.ex
    sc.append(s)

    # Контроль до запобіжника: операції рівно на `time` = `to` і `time` = `from` -- НЕ аномалія (виключність межі й дробові секунди не
    # виміряно; повтори відкидає id). Звичайні дані без відмови, кожна операція в конверті рівно один раз.
    s, b = new('СинтОперацияНаTo', 'monobank юросіб: операції на time = to і time = from запиту -- не аномалія, звичайні дані; кожна рівно раз', [3])
    eq_from, eq_to = to_unix(s.params.period_start), to_unix(s.params.period_end)
    edge = [ctx_(g, t=eq_to, amount=-1000, desc='на to', done=eq_to, tid=seqid('Q', 1)),
            ctx_(g, t=utc(2026, 10, 14, 8), amount=2000, desc='всередині', done=utc(2026, 10, 14, 8) + 5, tid=seqid('Q', 2)),
            ctx_(g, t=eq_from, amount=-3000, desc='на from', done=eq_from, tid=seqid('Q', 3))]
    b.statement(eq_from, eq_to, resp_json(200, sorted(edge, key=lambda o: -o['time'])))
    b.balances(resp_json(200, corp_balances_body(s.params)))
    s.exchanges = b.ex
    sc.append(s)

    # Повна сторінка без читаного `time` (поза виміряним; відповідь записана вручну як аномалія, модель банку не застосовується): курсора
    # немає, хоча «є ще» -- читання неповне, «повторити» (D36 п. 11); кожен рядок без часу -- Ошибка bad-date, операцій немає.
    s, b = new('СинтПолнаяБезВремени', 'monobank юросіб: повна сторінка без читаного time -- курсора немає, «повторити» (поза виміряним)', [3])
    no_time = [ctx_(g, t=0, amount=-(100 + i), desc='без часу %d' % i, tid=seqid('X', i), drop=('time',)) for i in range(lim)]
    b.statement(to_unix(s.params.period_start), to_unix(s.params.period_end), resp_json(200, no_time))
    s.exchanges = b.ex
    sc.append(s)

    # Застрягання посеред читання: дві звичайні сторінки, третя доходить до секунди, у якій більше операцій, ніж влізає на сторінку;
    # запит продовження збігся б із поточним. Операції, старші за цю секунду, -- у конверті.
    s, b = new('СинтЗастряла', 'monobank юросіб: застрягання посеред читання -- секунда з понад limit операцій; старіші операції в конверті (D36 п. 11)', [3])
    stuck_t = utc(2026, 10, 14, 6)
    newest = [ctx_(g, t=stuck_t + 2020 + 20 * (lim - i), amount=-(500 + i), desc='а%d' % i, tid=seqid('A', i)) for i in range(1, lim + 1)]
    middle = [ctx_(g, t=stuck_t + 100 + 10 * (lim - i), amount=-(600 + i), desc='б%d' % i, tid=seqid('M', i)) for i in range(1, lim)]
    crowd = [ctx_(g, t=stuck_t, amount=-(700 + i), desc='ті самі %d' % i, tid=seqid('Z', i)) for i in range(1, lim + 2)]
    below = [ctx_(g, t=stuck_t - 30 * i, amount=-(800 + i), desc='вк%d' % i, tid=seqid('V', i)) for i in range(1, 6)]
    corp_paged(b, s.params, newest + middle + crowd + below, lim)
    s.exchanges = b.ex
    sc.append(s)

    tz = lambda *a: utc(*a)
    # час: time і completedTime у різних добах (23:50 -> 00:10)
    s, b = new('СинтВремяВесна', 'monobank юросіб: 00:30 узимку й улітку, перехід 29.03, time і completedTime у різних добах (синтетика: у run1 0 операцій у 00:00-02:59 за Києвом)', [1],
               start=_day(2026, 3, 28), end=_day(2026, 3, 30, 23, 59, 59))
    spring = [(tz(2026, 3, 27, 22, 30), None), (tz(2026, 3, 28, 22, 0, 0), None), (tz(2026, 3, 29, 0, 59, 59), None),
              (tz(2026, 3, 29, 1, 0, 0), None), (tz(2026, 3, 29, 21, 30), None),
              (tz(2026, 3, 29, 20, 50), tz(2026, 3, 29, 21, 10))]
    one(b, [ctx_(g, t=t, amount=-(1000 + 10 * i), desc='час %d' % i, done=d, cnt=cnt()) for i, (t, d) in enumerate(spring)],
        s.params.period_start, s.params.period_end)
    s.exchanges = b.ex
    sc.append(s)

    s, b = new('СинтВремяОсень', 'monobank юросіб: 00:30 на переході 25.10, повторювана година 03:30, time і completedTime у різних добах (синтетика: у run1 0 операцій у 00:00-02:59 за Києвом)', [1],
               start=_day(2026, 10, 24), end=_day(2026, 10, 26, 23, 59, 59))
    autumn = [(tz(2026, 10, 24, 21, 30), None), (tz(2026, 10, 25, 0, 30), None), (tz(2026, 10, 25, 1, 30), None),
              (tz(2026, 10, 25, 22, 30), None), (tz(2026, 10, 25, 21, 50), tz(2026, 10, 25, 22, 10))]
    one(b, [ctx_(g, t=t, amount=-(2000 + 10 * i), desc='час %d' % i, done=d, cnt=cnt()) for i, (t, d) in enumerate(autumn)],
        s.params.period_start, s.params.period_end)
    s.exchanges = b.ex
    sc.append(s)

    s, b = new('СинтВалюта', 'monobank юросіб: валютний рахунок EUR', [5])
    one(b, [ctx_(g, t=t0 + 60, amount=-5000, desc='EUR out', ccy='978', done=t0 + 70, cnt=cnt()),
            ctx_(g, t=t0 + 120, amount=120000, desc='EUR in', ccy='978', done=t0 + 130, cnt=cnt())],
        s.params.period_start, s.params.period_end)
    s.exchanges = b.ex
    sc.append(s)

    s, b = new('СинтПусто', 'monobank юросіб: порожня відповідь', [3])
    one(b, [], s.params.period_start, s.params.period_end)
    s.exchanges = b.ex
    sc.append(s)

    _mono_failures(sc, new, None, one, g, cnt, 'mono-corp', t0)

    # Межа довіри: дні 14.10 final, 15.10 НЕ final (діра), 16.10 final, 17.10 не final. Межа — початок ПЕРШОГО неостаточного
    # дня (15.10 00:00), а не кінець останнього остаточного (16.10 24:00).
    s, b = new('СинтГраницаДыра', 'monobank юросіб: balances з діркою (isFinal: так, ні, так, ні) — межа на першому неостаточному дні', [2],
               start=_day(2026, 10, 14), end=_day(2026, 10, 17, 23, 59, 59))
    one(b, [ctx_(g, t=utc(2026, 10, 14, 8), amount=-1000, desc='Операція', done=utc(2026, 10, 14, 8) + 10, cnt=cnt())],
        s.params.period_start, s.params.period_end)
    b.balances(resp_json(200, corp_balances_body(s.params, {'2026-10-15': False, '2026-10-17': False})))
    s.exchanges = b.ex
    sc.append(s)

    # Межа довіри не раніше початку періоду (D36 п. 10): період починається о 10:00, а перший день без isFinal -- початок цього дня
    # (00:00) раніше за початок періоду, тож межа = НачалоПериода.
    s, b = new('СинтГраницаРаньшеНачала', 'monobank юросіб: період з 10:00, перший день неостаточний -- банківська межа (00:00) раніше за початок періоду, межа довіри = НачалоПериода', [2],
               start=_day(2026, 10, 14, 10), end=_day(2026, 10, 14, 23, 59, 59))
    one(b, [ctx_(g, t=utc(2026, 10, 14, 9), amount=-1000, desc='Операція', done=utc(2026, 10, 14, 9) + 10, cnt=cnt())],
        s.params.period_start, s.params.period_end)
    b.balances(resp_json(200, corp_balances_body(s.params, {'2026-10-14': False})))
    s.exchanges = b.ex
    sc.append(s)

    s, b = new('СинтБалансыСбой', 'monobank юросіб: виписка прочитана, збій самого обміну balances (HTTP 500)', [4])
    one(b, [ctx_(g, t=t0 + 60, amount=-500, desc='Операція', done=t0 + 70, cnt=cnt())], s.params.period_start, s.params.period_end)
    b.balances(resp_json(500, {'errorCode': 'INTERNAL_SERVER_ERROR', 'errorDescription': 'Internal server error'}))
    s.exchanges = b.ex
    sc.append(s)

    with_balances = {'СинтСтатусы', 'СинтПовтор', 'СинтПоля', 'СинтСтраницы', 'СинтКратнаяСтраница', 'СинтВремяВесна',
                     'СинтВремяОсень', 'СинтВалюта', 'СинтПусто', 'СинтЛимит429', 'СинтСекундаРаспалась'}
    for s in sc:
        if s.sid in with_balances:
            b = Builder('mono-corp', s.sid, s.params)
            b.ex = s.exchanges
            b.balances(resp_json(200, corp_balances_body(s.params)))

    s, b = new('СинтСчетНеНайден404', 'monobank юросіб: IBAN не знайдено -- 404 notFound [документальний, не спостерігалось]', [4])
    b.statement(to_unix(s.params.period_start), to_unix(s.params.period_end),
                resp_json(404, {'errorCode': 'notFound', 'errorDescription': 'Account not found'}))
    s.exchanges = b.ex
    sc.append(s)

    s, b = new('СинтЧужойСчет400', 'monobank юросіб: чужий / неіснуючий IBAN -- HTTP 400, BAD_REQUEST (спостережено)', [4])
    b.statement(to_unix(s.params.period_start), to_unix(s.params.period_end),
                resp_json(400, {'errorCode': 'BAD_REQUEST', 'errorDescription': 'Account not found'}))
    s.exchanges = b.ex
    sc.append(s)
    return sc
