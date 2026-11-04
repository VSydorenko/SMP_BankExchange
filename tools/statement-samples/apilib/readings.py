# -*- coding: utf-8 -*-
"""«Читання» з запису прогону. Запис рекордера -- це багато сценаріїв підряд (сторінки, помилки, різні періоди), а оракул
рахує ОДНЕ читання: послідовність обмінів, яку зробив би конектор. Тут запис ріжеться на читання за полем `scenario` і
доповнюється обмінами, без яких читання неповне (`/balance` ПриватБанку, `balances` юросіб, `client-info` ФОП).

Параметри читання (рахунок, період) виводяться з самого запису -- однаково для сирого й знеособленого: рахунок з відповіді
`/balance` (Приват), зі шляху виписки (юросіб), з `client-info` за ідентифікатором рахунку зі шляху (ФОП); період -- із
запиту. Жодна функція не друкує значення."""
import re
from dataclasses import dataclass
from datetime import datetime

from . import common as C, kyiv, recording as R
from .common import Params
from .synth import BANK_KEYS


@dataclass
class Reading:
    id: str
    bank: str
    scenario: str
    exchanges: list
    params: Params

    def recording(self):
        m = R.make_manifest(self.bank, 'reading-' + self.scenario, self.exchanges, note='reading: ' + self.scenario)
        return R.Recording(m, self.exchanges)

    @property
    def name(self):
        return 'СМП_ТестОтвет%s%s' % (BANK_KEYS[self.bank], self.id)

    @property
    def etalon_name(self):
        return 'СМП_ТестЭталон%s%s' % (BANK_KEYS[self.bank], self.id)


def reading_id(bank, scenario):
    words = [w for w in re.split(r'[_\W]+', scenario) if w and w.lower() not in ('privat', 'corp', 'fop', 'a1', 'a2', 'a3')]
    return 'Зап' + ''.join(w.capitalize() for w in words)


def _ok(ex):
    return bool(ex['response']) and ex['response']['status'] == 200


def _json(ex):
    try:
        return R.body_json(ex)
    except R.NotJson:
        return None


def _groups(rec):
    out, order = {}, []
    for ex in rec.exchanges:
        sc = ex['scenario']
        if sc not in out:
            out[sc] = []
            order.append(sc)
        out[sc].append(ex)
    return [(sc, out[sc]) for sc in order]


def _first(rec, pred):
    return next((e for e in rec.exchanges if pred(e)), None)


def _qdict(ex):
    return dict(R.query_pairs(ex))


def readings(rec):
    """-> [Reading]: читання, які можна дати оракулові. Сценарії, що не є читанням (баланси окремо, settings, interim/final),
    пропускаються."""
    bank = rec.bank
    out = []
    if bank == 'privat':
        bal = _first(rec, lambda e: e['request']['path'] == C.PRIVAT_BALANCE_PATH and _ok(e))
        settings = _first(rec, lambda e: e['request']['path'] == C.PRIVAT_SETTINGS_PATH and _ok(e))
        for sc, exs in _groups(rec):
            tx = [e for e in exs if e['request']['path'] == C.PRIVAT_PATH]
            if not tx or bal is None:
                continue
            q = _qdict(tx[0])
            qb = _qdict(bal)
            start = datetime.strptime(q['startDate'], '%d-%m-%Y')
            end = datetime.strptime(q.get('endDate') or qb['endDate'], '%d-%m-%Y').replace(hour=23, minute=59, second=59)
            rows = (_json(bal) or {}).get('balances') or []
            account = rows[0]['acc'] if rows else ''
            p = Params(account=account, period_start=start, period_end=end, old_account_currency='980')
            # R14: `/settings` -- перший обмін кожного читання (той самий прогін); `/balance` -- лише коли транзакції прочитано
            # без відмови: після відмови конектор запитів більше не робить (I1)
            seq = ([settings] if settings is not None else []) + tx + ([bal] if _ok(tx[-1]) else [])
            out.append(Reading(reading_id(bank, sc), bank, sc, seq, p))
    elif bank == 'mono-corp':
        bal = _first(rec, lambda e: e['request']['path'].endswith('/balances') and _ok(e))
        for sc, exs in _groups(rec):
            st = [e for e in exs if R.statement_window(e)]
            if not st or bal is None:
                continue
            acct, frm, to = R.statement_window(st[0])
            p = Params(account=acct, period_start=kyiv.unix_to_local(frm), period_end=kyiv.unix_to_local(to), old_account_currency='980')
            out.append(Reading(reading_id(bank, sc), bank, sc, st + ([bal] if _ok(st[-1]) else []), p))
    else:
        info = _first(rec, lambda e: e['request']['path'] == C.FOP_CLIENT_INFO and _ok(e))
        for sc, exs in _groups(rec):
            own_info = [e for e in exs if e['request']['path'] == C.FOP_CLIENT_INFO]
            st = [e for e in exs if R.statement_window(e)]
            if not own_info and not st:
                continue
            ci = own_info[0] if own_info else info
            if ci is None:
                continue
            accounts = ((_json(ci) or {}).get('accounts') or []) if _ok(ci) else []
            ids = [R.statement_window(e)[0] for e in st]
            iban = next((a['iban'] for a in accounts if ids and a.get('id') == ids[0]), accounts[0]['iban'] if accounts else '')
            if st:
                start = kyiv.unix_to_local(min(R.statement_window(e)[1] for e in st))
                end = kyiv.unix_to_local(max(R.statement_window(e)[2] for e in st))
            else:
                start = end = datetime(2000, 1, 1)
            p = Params(account=iban, period_start=start, period_end=end, old_account_currency='980')
            exchanges = ([ci] if not own_info else []) + exs
            out.append(Reading(reading_id(bank, sc), bank, sc, [e for e in exchanges if e['request']['path'] == C.FOP_CLIENT_INFO
                                                                  or R.statement_window(e)], p))
    return out


def replay_exclusion(bank, rec, params):
    """Чи може конектор відтворити читання запису запит у запит (транспорт відтворення строгий: інший рядок запиту -- червоний).
    -> причина виключення з набору run1 або '' (читання лишається). Читання складається лише з обмінів, які конектор справді
    запитує: рекордер знімав сценарії з параметрами, яких конектор не шле, і складав читання з обмінів різних сценаріїв.
    Правило поки лише для monobank юросіб (задача 4 плану 05а); розмір сторінки (limit) причиною не є: його задає шов
    розміру сторінки в тесті, а запис з limit, відмінним від робочого, читається зі швом на його limit.
    `params` -- `parameters` еталона (`НачалоПериода`, `КонецПериода`: рядки ГГГГ-ММ-ДДTгг:хх:сс)."""
    if bank != 'mono-corp':
        return ''
    day = lambda text: text[:10]
    for e in rec.exchanges:
        path = e['request']['path']
        pairs = dict(R.query_pairs(e))
        if R.statement_window(e):
            extra = sorted(set(pairs) - {'limit'})
            if extra:
                return 'запит виписки несе параметр %s, якого конектор не шле (банк його ігнорує)' % ', '.join(extra)
        elif path.endswith('/balances'):
            want = {'dateFrom': day(params['НачалоПериода']), 'dateTo': day(params['КонецПериода'])}
            if pairs != want:
                return 'вікно balances запису (%s) не збігається з періодом читання (%s): обмін узято з іншого сценарію' % (
                    '%s..%s' % (pairs.get('dateFrom'), pairs.get('dateTo')), '%s..%s' % (want['dateFrom'], want['dateTo']))
    return ''
