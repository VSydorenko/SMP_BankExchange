# -*- coding: utf-8 -*-
"""«Читання» з запису прогону. Запис рекордера -- це багато сценаріїв підряд (сторінки, помилки, різні періоди), а оракул
рахує ОДНЕ читання: послідовність обмінів, яку зробив би конектор. Тут запис ріжеться на читання за полем `scenario` і
доповнюється обмінами, без яких читання неповне (`/balance` ПриватБанку, `balances` юросіб, `client-info` ФОП).

Параметри читання (рахунок, період) виводяться з самого запису -- однаково для сирого й знеособленого: рахунок з відповіді
`/balance` (Приват), зі шляху виписки (юросіб), з `client-info` за ідентифікатором рахунку зі шляху (ФОП); період -- із
запиту. Жодна функція не друкує значення."""
import json
import re
from dataclasses import dataclass
from datetime import datetime

from . import bankmodel, common as C, kyiv, recording as R
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
        # номери обмінів -- підряд (читання складене з обмінів різних сценаріїв і змодельованих)
        exchanges = [dict(e, seq=k) for k, e in enumerate(self.exchanges, 1)]
        m = R.make_manifest(self.bank, 'reading-' + self.scenario, exchanges, note='reading: ' + self.scenario)
        return R.Recording(m, exchanges)

    @property
    def name(self):
        return 'СМП_ТестОтвет%s%s' % (BANK_KEYS[self.bank], self.id)

    @property
    def etalon_name(self):
        return 'СМП_ТестЭталон%s%s' % (BANK_KEYS[self.bank], self.id)


def reading_id(bank, scenario):
    # a1..a3 -- ім'я рахунку-сценарію ПУМБ (a1..a10 різні читання): без них три читання зливались в один ідентифікатор і перезаписували одне одного;
    # для банків 5а слова лишаються відкинутими (імена їхніх макетів не змінюються)
    skip = ('privat', 'corp', 'fop') + (() if bank == 'pumb' else ('a1', 'a2', 'a3'))
    words = [w for w in re.split(r'[_\W]+', scenario) if w and w.lower() not in skip]
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


def _pumb_body(ex):
    """Тіло запиту як JSON-об'єкт або None (немає / `bodyMasked` / `bodyOmitted` / не JSON)."""
    try:
        body = json.loads(R.request_body_text(ex) or '')
    except (ValueError, UnicodeDecodeError):
        return None
    return body if isinstance(body, dict) else None


def pumb_refusal(searches):
    """Чому читання ПУМБ з цими запитами `searcher` оракул НЕ моделює (або ''). Читання без пагінації моделюється з кількома запитами `searcher` (ділення періоду навпіл,
    D36 п. 11, Р4); явно відхиляються: запит із `pagingRequest` (конектор його не шле), тіло, що не розібрано, не один рахунок у `documentAccounts` чи різні рахунки в запитах
    одного читання. Формат дат запиту -- гіпотеза `dd.MM.yyyy HH:mm:ss`, інший -- відмова."""
    if not searches:
        return 'немає запиту searcher'
    accounts = set()
    for se in searches:
        body = _pumb_body(se)
        if body is None:
            return 'тіло запиту searcher не розібрано (немає, bodyMasked, bodyOmitted чи не JSON)'
        if 'pagingRequest' in body:
            return 'pagingRequest у запиті (Р4: конектор пагінації не використовує)'
        accs = body.get('documentAccounts')
        if not isinstance(accs, list) or len(accs) != 1:
            return 'documentAccounts не з одного рахунку'
        accounts.add(str(accs[0]))
        try:
            C.pumb_date(body.get('fromDate'))
            C.pumb_date(body.get('toDate'))
        except C.PumbDateFormat:
            return 'формат дати запиту не dd.MM.yyyy HH:mm:ss (гіпотеза, до виміру)'
    if len(accounts) != 1:
        return 'запити одного читання -- різні рахунки'
    return ''


def pumb_split(rec):
    """ПУМБ: -> ([Reading], [(сценарій, причина)]) -- читання, які оракул моделює, і ЯВНИЙ перелік «не змодельовано до виміру».
    Читання = автентифікація, список рахунків і запити `searcher` без `pagingRequest` (перший -- увесь період, далі половини, якщо відповідь на порозі; Р4); параметри -- з ПЕРШОГО запиту й списку рахунків."""
    token = lambda e: e['request']['path'].endswith('/openid-connect/token')
    account = lambda e: e['request']['path'].endswith('/account') and e['request']['method'] == 'GET'
    g_auth = _first(rec, token)
    g_acc = _first(rec, lambda e: account(e) and _ok(e))
    out, skipped = [], []
    for sc, exs in _groups(rec):
        se = [e for e in exs if e['request']['path'].endswith('/document/searcher')]
        if not se:
            continue
        why = pumb_refusal(se)
        own_auth, own_acc = [e for e in exs if token(e)], [e for e in exs if account(e)]
        auth = own_auth[0] if own_auth else g_auth
        acc = own_acc[0] if own_acc else g_acc
        if not why and (auth is None or acc is None):
            why = 'у записі немає обміну автентифікації чи списку рахунків'
        if why:
            skipped.append((sc, why))
            continue
        body = _pumb_body(se[0])
        accounts = (_json(acc) or []) if _ok(acc) else []
        accid = str(body['documentAccounts'][0])
        mine = next((a for a in accounts if isinstance(a, dict) and str(a.get('accountId')) == accid), {})
        iban = mine.get('iban') or ''
        # ВалютаСчета читання -- валюта того рахунку, який читали (accountId запиту): під IBAN їх може бути кілька (D36 п. 2); числовий код ISO 4217, '' -- валюта не розпізнана
        p = Params(account=iban, period_start=C.pumb_date(body['fromDate']), period_end=C.pumb_date(body['toDate']),
                   reading_moment=C.DEFAULT_READING_MOMENT, account_currency_code=C.numeric_currency(C.to_str(mine.get('currency'))) or '')
        out.append(Reading(reading_id('pumb', sc), 'pumb', sc, [auth, acc, *se], p))
    return out, skipped


def readings(rec):
    """-> [Reading]: читання, які можна дати оракулові. Сценарії, що не є читанням (баланси окремо, settings, interim/final),
    пропускаються."""
    bank = rec.bank
    out = []
    if bank == 'pumb':
        return pumb_split(rec)[0]
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
            p = Params(account=account, period_start=start, period_end=end, old_account_currency='980', reading_moment=C.DEFAULT_READING_MOMENT)
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
            p = Params(account=acct, period_start=kyiv.unix_to_local(frm), period_end=kyiv.unix_to_local(to), old_account_currency='980',
                       reading_moment=C.DEFAULT_READING_MOMENT)
            # читання під межі запиту D36 п. 11 (71b3771, a90f7ea): запити похідні, тіла відповідей ті самі
            out.append(Reading(reading_id(bank, sc), bank, sc, _rebound(st, p) + ([bal] if _ok(st[-1]) else []), p))
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
            p = Params(account=iban, period_start=start, period_end=end, old_account_currency='980', reading_moment=C.DEFAULT_READING_MOMENT)
            exchanges = ([ci] if not own_info else []) + exs
            infos = [e for e in exchanges if e['request']['path'] == C.FOP_CLIENT_INFO]
            out.append(Reading(reading_id(bank, sc), bank, sc, infos + _rebound([e for e in exchanges if R.statement_window(e)], p, fop=True), p))
    return out


def _rebound(statements, p, fop=False):
    """Запити виписки читання під межі D36 п. 11: `from` = `НачалоПериода` - 1 с, перший `to` = Мин(`КонецПериода` + 1 с, момент читання). Лише шлях
    запиту; тіла відповідей не змінюються. Читання, що потребує кількох відрізків, -- помилка (нових тіл не вигадуємо). -> нові обміни."""
    wins = C.request_windows(p, fop)
    if not wins:
        return [json.loads(json.dumps(e)) for e in statements]       # перевернутий або майбутній період: запитів немає, обміни не використовуються
    if len(wins) > 1:
        raise ValueError('читання run1 потребує кількох відрізків: похідного запису без нових тіл відповідей не побудувати')
    lo, hi = wins[0]
    orig_from = min(R.statement_window(e)[1] for e in statements) if statements else None
    out = []
    for k, e in enumerate(statements):
        acct, frm, to = R.statement_window(e)
        ne = json.loads(json.dumps(e))
        nfrm = lo if frm == orig_from else frm
        nto = wins[0][1] if k == 0 else to
        ne['request']['path'] = ne['request']['path'].rsplit('/', 3)[0] + '/%s/%d/%d' % (acct, nfrm, nto)
        out.append(ne)
    return out


def measurement_exclusion(ident):
    """Читання, що є виміром, а не запитом конектора (пари меж запиту `*_boundary_*`, день `DAT_KL` Привата `privat_*_datkl_*`): факти журналу, у Т1 не беруться.
    -> причина або ''."""
    low = ident.lower()
    if 'boundary' in low or 'datkl' in low:
        return 'вимір, не запит конектора: пари меж запиту й день DAT_KL -- факти журналу 05а, у Т1 не беруться'
    return ''


def replay_exclusion(bank, rec, params):
    """Чи може конектор відтворити читання запису запит у запит (транспорт відтворення строгий: інший рядок запиту -- червоний).
    -> причина виключення з набору run1 або '' (читання лишається). Читання складається лише з обмінів, які конектор справді
    запитує: рекордер знімав сценарії з параметрами, яких конектор не шле, і складав читання з обмінів різних сценаріїв.
    Правило поки лише для monobank юросіб (задача 4 плану 05а); розмір сторінки (limit) причиною не є: його задає шов
    розміру сторінки в тесті, а запис з limit, відмінним від робочого, читається зі швом на його limit.
    `params` -- `parameters` еталона (`НачалоПериода`, `КонецПериода`: рядки ГГГГ-ММ-ДДTгг:хх:сс)."""
    if bank in ('mono-fop', 'mono-corp', 'privat'):
        # ISO-рядки порівнюються лексикографічно (однакова форма ГГГГ-ММ-ДДTгг:хх:сс)
        if params['КонецПериода'] < params['НачалоПериода']:
            return 'період задано навпаки: точку читання відхиляє до конектора (D36 п. 11, 0d071e2), запитів немає; відповідь банку на перевернутий запит -- факт журналу, у Т1 не потрібна'
        if params.get('МоментЧтения') and params['НачалоПериода'] > params['МоментЧтения']:
            return 'період цілком у майбутньому відносно моменту читання: за D36 п. 11 запитів немає, записана відповідь банку не використовується; покривають синтетичні записи'
    if bank == 'privat':
        return _replay_exclusion_privat(rec, params)
    if bank == 'mono-fop':
        return _replay_exclusion_fop(rec, params)
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
    stmts = [e for e in rec.exchanges if R.statement_window(e)]
    for prev, nxt in zip(stmts, stmts[1:]):
        # D36 п. 11 (44d22a1): конектор продовжує з `to` = час найранішої операції + 1; рекордер продовжував з `to` = цей час
        try:
            page = R.body_json(prev)
        except R.NotJson:
            continue
        times = [x.get('time') for x in page if isinstance(x, dict) and isinstance(x.get('time'), int)] if isinstance(page, list) else []
        # межа продовження конектора: Мин(E + 1, U); застрягання (межа = U) -- крок Мин(E, U - 1), він законний
        want = min(min(times) + 1, R.statement_window(prev)[2]) if times else None
        if want is not None and want >= R.statement_window(prev)[2]:
            want = min(min(times), R.statement_window(prev)[2] - 1)
        if times and R.statement_window(nxt)[2] == min(times) and want != min(times):
            return 'рекордер продовжував з `to` = межова секунда; конектор за D36 п. 11 (44d22a1) запитує `to` + 1'
    if stmts:
        last = stmts[-1]
        if last['response'] and last['response']['status'] == 200:
            try:
                page = R.body_json(last)
            except R.NotJson:
                page = None
            limit = next((int(v) for k, v in R.query_pairs(last) if k == 'limit' and v.isdigit()), 10)
            _, frm, to = R.statement_window(last)
            times = [x.get('time') for x in page if isinstance(x, dict) and isinstance(x.get('time'), int)] if isinstance(page, list) else []
            if isinstance(page, list) and len(page) >= limit and times and frm < min(times) < to:
                return 'запис кінчається повною сторінкою (limit %d), яку можна продовжити: наступного обміну немає, ознаки кінця немає' % limit
    for e in rec.exchanges:
        if R.statement_window(e):
            limit = next((int(v) for k, v in R.query_pairs(e) if k == 'limit' and v.isdigit()), 10)
            if limit > C.CORP_WORKING_LIMIT:
                return 'limit %d понад робочий (%d); шов розміру сторінки лише менший за робочий ліміт' % (limit, C.CORP_WORKING_LIMIT)
    return ''


def _replay_exclusion_privat(rec, params):
    """ПриватБанк (задача 6 плану 05а): конектор шле `acc` (14 останніх цифр рахунку читання), дні запиту за D36 п. 11 (d392bc4), `limit` і `followId` за правилами
    (`expected.verify_privat_requests`). Читання запису, чий запит конектор не відтворить запит у запит, -- виключення з причиною: рекордер знімав сценарії без
    `limit` чи `endDate`, з повним IBAN у `acc` чи з чужим рахунком. Запис, що кінчається сторінкою з `exist_next_page = true` без наступного обміну, відсікає
    оракул (`RecordingMismatch`)."""
    from . import expected as E
    if not params['НомерСчета']:
        return 'у записі немає рахунку читання'
    p = Params(account=params['НомерСчета'], period_start=datetime.strptime(params['НачалоПериода'], '%Y-%m-%dT%H:%M:%S'),
               period_end=datetime.strptime(params['КонецПериода'], '%Y-%m-%dT%H:%M:%S'),
               reading_moment=datetime.strptime(params['МоментЧтения'], '%Y-%m-%dT%H:%M:%S') if params.get('МоментЧтения') else None)
    problems = E.verify_privat_requests(rec, p)
    if problems:
        return 'конектор не відтворить запит запису: ' + problems[0]
    return ''


def _replay_exclusion_fop(rec, params):
    """monobank ФОП (задача 5 плану 05а): конектор бере ідентифікатор рахунку з `client-info` за IBAN читання. Запит виписки запису з
    ідентифікатором, якому не відповідає жоден рахунок із цим IBAN (рекордер питав «чужий / неіснуючий» ідентифікатор), конектор
    не відтворить. Інші розбіжності (відрізки, продовження) ловить оракул: він відмовляється рахувати запис, що кінчається не так, як
    конектор (`RecordingMismatch`), і `sets` такого читання не бачить."""
    if not params['НомерСчета']:
        return 'у записі немає рахунку читання: IBAN не виводиться (client-info відмовив), а точка читання без номера рахунку відмовляє до конектора; недійсний токен покриває синтетика'
    info = next((e for e in rec.exchanges if e['request']['path'] == C.FOP_CLIENT_INFO and e['response'] and e['response']['status'] == 200), None)
    if info is None:
        return ''
    try:
        accounts = R.body_json(info).get('accounts') or []
    except (R.NotJson, AttributeError):
        return ''
    own = next((a.get('id') for a in accounts if isinstance(a, dict) and a.get('iban') == params['НомерСчета']), None)
    for e in rec.exchanges:
        w = R.statement_window(e)
        if w and own is not None and w[0] != own:
            return 'ідентифікатор рахунку в запиті виписки запису не належить рахунку з IBAN читання (рекордер питав чужий ідентифікатор); конектор бере його з client-info за IBAN'
    return ''


def model_paged_corp(rec, limit=None):
    """Похідний запис «справжні операції, сторінки від моделі»: операції справжнього запису юросіб (одна сторінка великого `limit`),
    згруповані моделлю банку (`bankmodel.CorpBank`, лише виміряне) у сторінки на робочому `limit` на запити конектора за D36 п. 11
    (межа продовження Мин(E + 1, U)). Тіла операцій не змінюються (серіалізація тими самими байтами), модель їх лише групує; обмін
    `balances` береться зі справжнього запису як є. -> `Recording`."""
    limit = C.CORP_WORKING_LIMIT if limit is None else limit
    stmts = [e for e in rec.exchanges if R.statement_window(e)]
    bals = [e for e in rec.exchanges if e['request']['path'].endswith('/balances')]
    if len(stmts) != 1 or len(bals) != 1:
        raise ValueError('очікується один запит виписки й один balances, а в записі %d і %d' % (len(stmts), len(bals)))
    real = stmts[0]
    acct, frm, to = R.statement_window(real)
    bank = bankmodel.CorpBank(R.body_json(real))
    exchanges, upper = [], to
    while True:
        page = bank.statement(frm, upper, limit)
        body = json.dumps(page, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        exchanges.append(R.make_exchange(len(exchanges) + 1, 'model30_' + real['scenario'],
                                         {'method': 'GET', 'host': real['request']['host'],
                                          'path': '/ext/v1/statement/%s/%d/%d' % (acct, frm, upper), 'query': 'limit=%d' % limit},
                                         {'status': 200, 'headers': [tuple(h) for h in real['response']['headers']], 'body': body}))
        if len(page) < limit:
            break
        earliest = min(o['time'] for o in page)
        nxt = min(earliest + 1, upper)
        if nxt >= upper:
            nxt = min(earliest, upper - 1)
        if nxt <= frm:
            break
        upper = nxt
    balances = dict(bals[0], seq=len(exchanges) + 1)
    exchanges.append(balances)
    return R.Recording(R.make_manifest(rec.bank, 'model30', exchanges, note='real operations paged by the bank model'), exchanges)
