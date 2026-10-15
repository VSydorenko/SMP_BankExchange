# -*- coding: utf-8 -*-
"""Оракул, режим «стара обробка»: емуляція нинішніх API-модулів банків разом з їхніми фільтрами й виведенням `ДатаДок`.
Це не запуск 1С: модулі приватні й ходять у мережу без шва (D19). Кожне припущення — з посиланням на рядки модуля
(`ASSUMPTIONS`); еталон перелічує, які з них застосовано.

Скорочення: PB = `СМП_РаботаСБанкамиПриватБанкAPIСервер`, MF = `…МонобанкAPIСервер`, MU = `…МонобанкЮрAPIСервер`
(`SMP_BankExchange_SMB/cfe/src/CommonModules/<модуль>/Ext/Module.bsl`), KB = `DataProcessors/СМП_КлиентБанк/Ext/
ManagerModule.bsl` (розпізнавання `РаспознатьДанныеВСтрокеДокумента`, KB:3263).

**ПриватБанк — регламентний шлях** (рішення планувальника): `ВыполнитьРегламент` (PB:379), де розпізнавання — власна
копія в PB (PB:432 -> PB:500), а фільтр валюти — PB:425-430. Інтерактивний шлях (`Прочитать`, PB:240 -> KB:3263)
валюту рядка з валютою рахунку не порівнює; оракул його не відтворює. Якщо еталону знадобляться обидва шляхи — це
СТОП до планувальника.

Результат — поля ключа D17 для кожної операції: `ДатаДокумента`, `НомерДокумента`, `КонтрагентНомерСчета`, `Сумма`
(тест порівнює їх поле за полем). Розбір ніколи не друкує значень полів.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from . import common as C, recording as R

ASSUMPTIONS = {
    'PB-REGL': 'ПриватБанк — регламентний шлях: ВыполнитьРегламент PB:379, читання PB:3-63, розпізнавання PB:432->PB:500, '
               'фільтр валюти PB:425-430. Інтерактивний шлях не відтворюється.',
    'PB-OWN': 'Рядок не нашого рахунку відкидається в ДобавитьДокумент_v3 за СчетаРавны(НомерСчета бази, AUT_MY_ACC) '
              '(PB:89-95, PB:206-211): збіг цілого номера або 14 останніх символів, якщо один номер коротший за 29.',
    'PB-DIR': 'Напрям: TRANTYPE = "D" -> платник AUT_MY_*, одержувач AUT_CNTR_*; інакше навпаки (PB:101-120). '
              'Розпізнавач рахує Исходящий = (ПлательщикСчет = НомерСчета бази) ТОЧНО (PB:510).',
    'PB-REGL-FILTER': 'Регламентний фільтр (PB:425-430): ПлательщикСчет/ПолучательСчет = НомерСчета або НомерСчетаУстаревший '
                      '(незаповнений = порожній рядок, тож порожній рахунок рядка збігається з ним), і валюта: '
                      'ВалютаДенежныхСредств не заповнена або Код = КодВалюты рядка.',
    'PB-CCY': 'КодВалюты: UAH -> "980", інакше Справочники.Валюты.НайтиПоНаименованию(CCY).Код (PB:127-134); ненайдена '
              'валюта дає порожній код без винятку (з коду, не виміряно).',
    'PB-DATE': 'Дата = Дата(DATE_TIME_DAT_OD_TIM_P) без перетворення поясу (PB:136); ДатаСписано/ДатаПоступило — '
               'Дата(Дата) (PB:145, 163); розпізнавач бере ДатаСписано -> ДатаПоступило -> Дата (PB:568-577); '
               'ДатаВходящегоДокумента = ДатаДок з часом, у ключі — день (KB:837, 3483). Рядок "dd.MM.yyyy H:mm:ss" '
               'у ПолучитьДатуИзСтроки (PB:2466) потрапляє в резерв Дата(Источник) — результат той самий (виміряно).',
    'PB-KEY': 'НомерДок = NUM_DOC (PB:98, 138, 584); Сумма = модуль Число(SUM) (PB:99, 525-542); контрагент = '
              'ПолучательСчет, якщо Исходящий, інакше ПлательщикСчет (PB:822-837, KB:3751-3754).',
    'PB-LOOP': 'Читання сторінок (PB:39-62): status = SUCCESS — розбір і followId = next_page_id; ERROR — виняток з '
               'message; будь-який інший status (зокрема відповідь 5xx без нього) цикл не завершує — запит повторюється '
               'без кінця; HTTP-статус не перевіряється; exist_next_page без next_page_id дає followId = Неопределено '
               'і той самий запит знову. Усі три випадки — «зависання» (оракул позначає й зупиняється).',
    'PB-EXC': 'Виняток із читання (ERROR, не JSON, збій мережі, Дата() відсутнього поля) перериває ВыполнитьРегламент: '
              'жодна операція не завантажується.',
    'MONO-PAGES': 'Читання monobank (MF:275-353, MU:279-361): сторінка < 500 записів — кінець відрізка; повна сторінка — '
                  'верхня межа зсувається до найранішого `time` сторінки; найраніший <= початку відрізка чи >= верхньої '
                  'межі — відрізок обривається (MF: Полная лишається, якщо найраніший <= початку; MU: Полная = Ложь).',
    'MONO-DEDUP': 'Дедуплікація за `id` усередині читання (MF:320-324, MU:320-323); дубль мовчки відкидається.',
    'MF-HOLD': 'ФОП: hold = true пропускається й утримує курсор (MF:312-318).',
    'MU-STATUS': 'Юросіб: PENDING утримує курсор (MU:309-314); status <> DONE або reverse = true — мовчки пропускаються '
                 '(MU:315-317); відсутній status = порожній рядок = пропуск.',
    'MONO-TIME': 'Дата = МестноеВремя(Дата("19700101") + time) (MF:460-462, 542; MU:530-532); юросіб — completedTime, '
                 'якщо є (MU:571). Пояс — сеансу (`old_session_tz`); для Europe/Kiev дорівнює явному поясу (виміряно).',
    'MONO-KEY': 'НомерДок = id (MF:550, MU:579); Сумма = Формат(модуль amount/100, "ЧГ=0") -> Число() — без округлення '
                '(MF:553-566, MU:582-597); контрагент = counterIban (MF:540, 560, 567; MU:568, 590, 598); відсутній '
                'counterIban = порожній рядок (Строка(Неопределено) виміряно порожнім; присвоєння Неопределено рядковій '
                'колонці — припущення).',
    'MONO-FILTER': 'Розпізнавання monobank лишає рядок, якщо рахунок = НомерСчета бази і валюта рахунку заповнена '
                   '(MF:614-615, MU:635-636); IBAN, який передає модуль, вважається рівним НомерСчета.',
    'MF-CLIENT': 'ФОП: ідентифікатор рахунку — з client-info за IBAN (MF:371-400), якщо ИД облікового запису порожній '
                 '(MF:373-376); код <> 200 чи IBAN не знайдено — Полная = Ложь, операцій немає (MF:265-269).',
    'MONO-ERR': 'Код <> 200 чи тіло не масив: Полная = Ложь, те, що прочитано раніше, лишається (MF:291-302, MU:286-297). '
                'MU: 429 -> пауза й один повтор (MU:374-377); MF повтору не має.',
    'MONO-PURPOSE': 'Призначення ФОП: description, далі comment з нового рядка, далі « Сума комісії X», « Кешбек Y»; '
                    'юросіб: description і « Фактичний платник: <name> <idCode>»; обидва — Лев(…, 255) '
                    '(MF:514-527, 580-586; MU:545-558).',
}


@dataclass
class OldRow:
    n: int                      # номер у порядку читання (з одиниці), усі записи всіх сторінок
    fields: dict                # поля ключа D17 (+ допоміжні, не в ключі)


@dataclass
class OldResult:
    bank: str
    rows: list = field(default_factory=list)
    dropped: list = field(default_factory=list)     # (причина, ідентифікатор, n): те, що попередник відкинув без сліду
    error: dict = None                              # {'kind': ..., 'text': ...}
    complete: object = None
    used: set = field(default_factory=set)          # ідентифікатори припущень, застосованих до цього запису

    def key_fields(self):
        return [{'ПорядковыйНомер': r.n, **{k: r.fields[k] for k in KEY}} for r in self.rows]


KEY = ('ДатаДокумента', 'НомерДокумента', 'КонтрагентНомерСчета', 'Сумма')


def run(rec, p):
    return {'privat': old_privat, 'mono-fop': old_mono_fop, 'mono-corp': old_mono_corp}[rec.bank](rec, p)


# ====================================================================== ПриватБанк
def privat_base_account(p):
    """НомерСчета рахунку в базі: завжди IBAN (слова власника; у run1 AUT_MY_ACC -- IBAN у 87 з 87)."""
    return p.account


def old_privat(rec, p):
    res = OldResult('privat')
    res.used |= {'PB-REGL', 'PB-OWN', 'PB-DIR', 'PB-REGL-FILTER', 'PB-CCY', 'PB-DATE', 'PB-KEY', 'PB-LOOP', 'PB-EXC'}
    base = privat_base_account(p)
    staged = []
    n = 0
    err = None
    for ex in C.exchanges_for(rec, C.PRIVAT_PATH):
        if ex['failure']:
            err = {'kind': 'exception', 'text': 'збій мережі: ' + ex['failure']['kind']}
            break
        try:
            js = R.body_json(ex)
        except R.NotJson:
            err = {'kind': 'exception', 'text': 'тіло не JSON'}
            break
        st = js.get('status') if isinstance(js, dict) else None
        if st == 'ERROR':
            err = {'kind': 'exception', 'text': C.to_str(js.get('message'))}
            break
        if st != 'SUCCESS':
            err = {'kind': 'hang', 'text': 'status не SUCCESS і не ERROR: цикл не завершується'}
            break
        for tx in js.get('transactions') or []:
            n += 1
            try:
                row = _privat_add_document(tx, base, n, p.old_currency_catalog)
            except ValueError as e:
                err = {'kind': 'exception', 'text': str(e)}
                break
            if row is None:
                res.dropped.append(('foreign-account', C.to_str(tx.get('TECHNICAL_TRANSACTION_ID')), n))
            else:
                staged.append(row)
        if err:
            break
        if js.get('exist_next_page'):
            if js.get('next_page_id') in (None, ''):
                err = {'kind': 'hang', 'text': 'exist_next_page без next_page_id: followId = Неопределено, той самий запит'}
                break
    if err:
        res.error = err
        res.complete = False
        res.dropped.append(('exception-aborts-all', '', n))
        return res
    obsolete = p.old_account_obsolete
    for r in staged:
        pay, rcv = r['ПлательщикСчет'], r['ПолучательСчет']
        ok_acc = pay == base or rcv == base or pay == obsolete or rcv == obsolete
        ok_ccy = p.old_account_currency is None or p.old_account_currency == r['КодВалюты']
        if not (ok_acc and ok_ccy):
            res.dropped.append(('regulation-filter', r['ИД'], r['n']))
            continue
        outgoing = pay == base
        res.rows.append(OldRow(r['n'], {
            'ДатаДокумента': r['Дата'], 'НомерДокумента': r['Номер'],
            'КонтрагентНомерСчета': rcv if outgoing else pay, 'Сумма': abs(r['Сумма']),
            'Исходящий': outgoing, 'ИД': r['ИД'], 'Валюта': r['КодВалюты'], 'НазначениеПлатежа': C.trim(r['OSND'])}))
    res.complete = True
    return res


def _privat_add_document(d, base, n, catalog):
    """ДобавитьДокумент_v3 (PB:85-172) + розпізнавач (PB:500-577) для ключових полів. None — рядок не нашого рахунку."""
    if not C.account_equal(base, C.to_str(d.get('AUT_MY_ACC'))):
        return None
    deb = d.get('TRANTYPE') == 'D'
    pref_rcv, pref_pay = ('AUT_CNTR', 'AUT_MY') if deb else ('AUT_MY', 'AUT_CNTR')
    num = C.to_str(d.get('NUM_DOC'))
    amount = C.number(d.get('SUM'))                        # PB:150: Число(НовСтр.Сумма) — виняток для сміття
    ccy = C.to_str(d.get('CCY'))
    code = '980' if ccy == 'UAH' else catalog.get(ccy, '')
    date = C.parse_1c_date(C.to_str(d.get('DATE_TIME_DAT_OD_TIM_P')))
    return {'n': n, 'Номер': num, 'Сумма': amount,
            'ПолучательСчет': C.to_str(d.get(pref_rcv + '_ACC')), 'ПлательщикСчет': C.to_str(d.get(pref_pay + '_ACC')),
            'OSND': C.to_str(d.get('OSND')), 'ИД': C.to_str(d.get('TECHNICAL_TRANSACTION_ID')),
            'КодВалюты': code, 'Дата': date, 'ccy': ccy}


# ====================================================================== monobank
def _mono_tx_row(tx, n, corp, p):
    """ЗаполнитьТаблицуДаннымиТранзакций + розпізнавач для ключових полів (MF:540-575, MU:568-607)."""
    t = tx.get('completedTime') if corp and tx.get('completedTime') is not None else tx.get('time')
    date = C.session_local(int(t), p.old_session_tz)
    amount = Decimal(str(tx.get('amount'))) / 100
    outgoing = amount < 0
    parts = _mono_purpose(tx, corp)
    return OldRow(n, {
        'ДатаДокумента': date, 'НомерДокумента': C.to_str(tx.get('id')),
        'КонтрагентНомерСчета': C.to_str(tx.get('counterIban')), 'Сумма': abs(amount),
        'Исходящий': outgoing, 'ИД': C.to_str(tx.get('id')), 'Валюта': C.to_str(tx.get('currencyCode')),
        'НазначениеПлатежа': parts})


def _mono_purpose(tx, corp):
    return _mono_purpose_full(tx, corp)[:255]


def _mono_purpose_full(tx, corp):
    """Склад призначення без обрізання до 255 (обрізання попередника — Лев(…, 255); відступ dev5 його знімає)."""
    if corp:
        out = C.trim(C.to_str(tx.get('description')))
        ud = tx.get('ultimateDebit')
        if isinstance(ud, dict):
            rep = C.trim(C.trim(C.to_str(ud.get('name'))) + ' ' + C.trim(C.to_str(ud.get('idCode'))))
            if rep != '':
                out = out + ' Фактичний платник: ' + rep
        return out
    desc, com = C.trim(C.to_str(tx.get('description'))), C.trim(C.to_str(tx.get('comment')))
    out = desc if com == '' else (com if desc == '' else desc + '\n' + com)
    fee, cash = tx.get('commissionRate'), tx.get('cashbackAmount')
    if fee is not None and fee > 0:
        out += ' Сума комісії ' + C.chg0(Decimal(str(fee)) / 100)
    if cash is not None and cash > 0:
        out += ' Кешбек ' + C.chg0(Decimal(str(cash)) / 100)
    return out


def _old_mono(rec, p, corp):
    bank = 'mono-corp' if corp else 'mono-fop'
    res = OldResult(bank)
    res.used |= {'MONO-PAGES', 'MONO-DEDUP', 'MONO-TIME', 'MONO-KEY', 'MONO-FILTER', 'MONO-ERR', 'MONO-PURPOSE',
                 'MU-STATUS' if corp else 'MF-HOLD'}
    exs = list(rec.exchanges)
    pos = 0
    if not corp and not p.old_cached_account_id:
        res.used.add('MF-CLIENT')
        info = [e for e in exs if e['request']['path'] == C.FOP_CLIENT_INFO]
        if not info or info[0]['failure'] or info[0]['response']['status'] != 200:
            res.error = {'kind': 'client-info', 'text': 'client-info недоступний'}
            res.complete = False
            return res
        try:
            accounts = (R.body_json(info[0]).get('accounts')) or []
        except R.NotJson:
            accounts = []
        if not any(isinstance(a, dict) and a.get('iban') == p.account for a in accounts):
            res.error = {'kind': 'no-account', 'text': 'IBAN не знайдено серед рахунків client-info'}
            res.complete = False
            return res
    stmts = C.statement_exchanges(rec)
    seen, kept, n = set(), [], 0
    complete = True
    i = 0
    while i < len(stmts):
        ex = stmts[i]
        i += 1
        acct, frm, to = R.statement_window(ex)
        if corp and ex['response'] and ex['response']['status'] == 429 and i < len(stmts):
            ex = stmts[i]                                   # MU:374-377: пауза й один повтор
            i += 1
        if ex['failure'] or ex['response']['status'] != 200:
            complete = False
            break
        try:
            page = R.body_json(ex)
        except R.NotJson:
            complete = False
            break
        if not isinstance(page, list):
            complete = False
            break
        earliest = None
        start_local, upper_local = C.session_local(frm, p.old_session_tz), C.session_local(to, p.old_session_tz)
        for tx in page:
            n += 1
            t_create = C.session_local(int(tx.get('time')), p.old_session_tz)
            if earliest is None or t_create < earliest:
                earliest = t_create
            if corp:
                status = C.to_str(tx.get('status'))
                if status == 'PENDING':
                    res.dropped.append(('pending', C.to_str(tx.get('id')), n))
                    continue
                if status != 'DONE' or tx.get('reverse') is True:
                    res.dropped.append(('declined-or-reverse' if status == 'DECLINED' or tx.get('reverse') is True
                                        else 'status-not-done', C.to_str(tx.get('id')), n))
                    continue
            elif tx.get('hold') is True:
                res.dropped.append(('hold', C.to_str(tx.get('id')), n))
                continue
            if C.to_str(tx.get('id')) in seen:
                res.dropped.append(('duplicate-id', C.to_str(tx.get('id')), n))
                continue
            seen.add(C.to_str(tx.get('id')))
            kept.append(_mono_tx_row(tx, n, corp, p))
        if len(page) < C.PAGE_SIZE_MONO:
            if corp:
                break
            continue                                        # кінець відрізка ФОП, наступний обмін — новий відрізок
        if earliest is None or earliest <= start_local:
            if corp:
                complete = False
                break
            continue
        if earliest >= upper_local:
            complete = False
            if corp:
                break
    if p.old_account_currency is None:                         # MF:614-615, MU:635-636: валюта рахунку не заповнена — усе відкинуто
        res.dropped += [('account-currency-not-filled', r.fields['ИД'], r.n) for r in kept]
        kept = []
    res.rows = kept
    res.complete = complete
    return res


def old_mono_fop(rec, p):
    return _old_mono(rec, p, False)


def old_mono_corp(rec, p):
    return _old_mono(rec, p, True)
