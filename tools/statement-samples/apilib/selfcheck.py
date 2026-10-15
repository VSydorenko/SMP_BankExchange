# -*- coding: utf-8 -*-
"""Самоперевірка оракула на прикладах з документації банків (`doc_examples.py`).

Стверджується лише те, що з документації випливає: значення полів прикладу -> очікуваний розбір (суми в копійках,
напрям за знаком / `TRANTYPE`, час `Unix` -> київський місцевий із фіксованим зсувом літнього часу, склад призначення
з полів прикладу, обмеження банку на період, сторінку й частоту). Очікування тут — літерали й проста арифметика, які
не користуються оракулом (зокрема власним `kyiv`): оракул і самоперевірка помиляються незалежно.

Контроль уміє впасти: `tests/test_api_selfcheck.py` ламає оракул (відступ, правило часу, склад призначення) і вимагає
червоного рівно від відповідної перевірки. Зелений на справжньому оракулі нічого не доводить сам по собі.

Запуск: `python -P tools/statement-samples/apisamples.py selfcheck` (код 1, якщо хоч одна перевірка не пройшла).
"""
from datetime import datetime, timedelta
from decimal import Decimal

from . import common as C, doc_examples as D, expected as E, kyiv, oracle_old as O, synth as S
from .common import Params

OWN14 = D.PRIVAT_TX['AUT_MY_ACC']


def _privat_iban(acc14):
    import sslib.gen as sg
    bban = '305299' + acc14.rjust(19, '0')
    return 'UA' + sg.iban_check_digits('UA', bban) + bban


def _utc_plus3(sec):
    """Незалежна від kyiv арифметика: Unix -> UTC -> +3 год (дати прикладів — літній час: 2019-04-05, 2024-06-27/28)."""
    return datetime(1970, 1, 1) + timedelta(seconds=sec) + timedelta(hours=3)


def _privat_rec(tx, next_id=None):
    p = Params(account=_privat_iban(OWN14), period_start=datetime(2020, 1, 7), period_end=datetime(2020, 1, 7, 23, 59, 59),
               old_account_currency='980')
    b = S.Builder('privat', 'doc', p)
    b.privat(S.resp_json(200, S.privat_page([tx], nxt=next_id)))
    if next_id:
        b.privat(S.resp_json(200, S.privat_page([], exist=False)), follow=next_id)
    m = S.R.make_manifest('privat', 'doc-privat', b.ex)
    return S.R.Recording(m, b.ex), p


def _mono_rec(bank, txs, iban):
    p = Params(account=iban, period_start=datetime(2019, 4, 5), period_end=datetime(2019, 4, 5, 23, 59, 59), old_account_currency='980')
    if bank == 'mono-corp':
        p.period_start, p.period_end = datetime(2024, 6, 27), datetime(2024, 6, 28, 23, 59, 59)
    b = S.Builder(bank, 'doc', p)
    b.p_acct = 'doc-account-id'
    if bank == 'mono-fop':
        b.client_info(S.resp_json(200, {'clientId': '1', 'accounts': [{'id': 'doc-account-id', 'iban': iban}]}))
    b.statement(S.to_unix(p.period_start), S.to_unix(p.period_end), S.resp_json(200, txs))
    m = S.R.make_manifest(bank, 'doc-' + bank, b.ex)
    return S.R.Recording(m, b.ex), p


def _expect(cond, msg):
    if not cond:
        raise AssertionError(msg)


# ---------------------------------------------------------------------- ПриватБанк
def check_privat_example_expected():
    rec, p = _privat_rec(D.PRIVAT_TX, D.PRIVAT_NEXT_PAGE_ID)
    e = E.run(rec, p)
    _expect(len(e.ops) == 1 and not e.diags, 'приклад ПриватБанку: одна операція без діагностики')
    o = e.ops[0]
    want = {'НомерСчета': p.account, 'Валюта': '980', 'ДатаОперации': '2020-01-07T02:58:00', 'НомерДокумента': 'K0108B1WKX',
            'ДатаДокумента': '2020-01-07', 'Сумма': '0.01', 'Направление': 'Поступило',
            'ИдентификаторОперации': 'DNCHK0108B1WKX1',                      # документація: REF+REFN
            'КонтрагентНаименование': 'ПРОЦ ВИТР ЗА СТРОК КОШТ СУБ(UAH)', 'КонтрагентНомерСчета': '70214924104032',
            'КонтрагентКод': '41234569', 'КонтрагентМФО': '305299',
            'НазначениеПлатежа': 'Нарахування вiдсоткiв згiдно з депозитним договором N...'}
    for k, v in want.items():
        _expect(o[k] == v, 'приклад ПриватБанку, поле %s' % k)
    _expect(e.complete and e.failure_class == '' and e.trust == p.period_end, 'приклад ПриватБанку: повнота й межа довіри')


def check_privat_example_old():
    rec, p = _privat_rec(D.PRIVAT_TX, D.PRIVAT_NEXT_PAGE_ID)
    res = O.run(rec, p)
    _expect(res.error is None and len(res.rows) == 1, 'стара обробка: одна операція')
    f = res.rows[0].fields
    _expect(f['ДатаДокумента'] == datetime(2020, 1, 7, 2, 58, 0), 'ключ: ДатаДок')
    _expect(f['НомерДокумента'] == 'K0108B1WKX' and f['КонтрагентНомерСчета'] == '70214924104032', 'ключ: номер, рахунок контрагента')
    _expect(f['Сумма'] == Decimal('0.01'), 'ключ: сума')


def check_privat_trantype_d():
    tx = dict(D.PRIVAT_TX, TRANTYPE='D')
    rec, p = _privat_rec(tx)
    o = E.run(rec, p).ops[0]
    _expect(o['Направление'] == 'Списано' and o['КонтрагентНомерСчета'] == '70214924104032', 'TRANTYPE D: списання, контрагент AUT_CNTR')


def check_privat_pr_pr_legend():
    for state, essence, op in (('r', None, True), ('p', 'nonfinal', False), ('n', 'cancelled', False)):
        rec, p = _privat_rec(dict(D.PRIVAT_TX, PR_PR=state))
        e = E.run(rec, p)
        _expect(bool(e.ops) == op, 'PR_PR=%s: операція %s' % (state, op))
        if essence:
            _expect([d['Суть'] for d in e.diags] == [essence] and e.diags[0]['Уровень'] == 'Предупреждение',
                    'PR_PR=%s: Предупреждение %s' % (state, essence))
    rec, p = _privat_rec(dict(D.PRIVAT_TX, PR_PR='p'))
    _expect(E.run(rec, p).trust == datetime(2020, 1, 7, 2, 58, 0), 'PR_PR=p: ГраницаДоверия — момент операції')


# ---------------------------------------------------------------------- monobank
def check_mono_personal_example():
    iban = 'UA' + '0' * 27
    rec, p = _mono_rec('mono-fop', [D.MONO_PERSONAL_TX], iban)
    e = E.run(rec, p)
    _expect(len(e.ops) == 1 and not e.diags, 'приклад ФОП: одна операція без діагностики')
    o = e.ops[0]
    moment = _utc_plus3(1554466347)
    _expect(moment == datetime(2019, 4, 5, 15, 12, 27), 'арифметика прикладу')
    want = {'НомерСчета': iban, 'Валюта': '980', 'ДатаОперации': '2019-04-05T15:12:27', 'НомерДокумента': 'ZuHWzqkKGVo=',
            'ДатаДокумента': '2019-04-05', 'Сумма': '950.00', 'Направление': 'Списано', 'ИдентификаторОперации': 'ZuHWzqkKGVo=',
            'КонтрагентНаименование': 'ТОВАРИСТВО З ОБМЕЖЕНОЮ ВІДПОВІДАЛЬНІСТЮ «ВОРОНА»',
            'КонтрагентНомерСчета': 'UA898999980000355639201001404', 'КонтрагентКод': '3096889974',
            'НазначениеПлатежа': 'Покупка щастя\nЗа каву Кешбек 180'}
    for k, v in want.items():
        _expect(o[k] == v, 'приклад ФОП, поле %s' % k)
    old = O.run(rec, p).rows[0].fields
    _expect(old['ДатаДокумента'] == moment and old['НомерДокумента'] == 'ZuHWzqkKGVo=' and old['Сумма'] == Decimal('950'),
            'ФОП, стара обробка: ключ')
    rec, p = _mono_rec('mono-fop', [dict(D.MONO_PERSONAL_TX, hold=True)], iban)
    e = E.run(rec, p)
    _expect(not e.ops and [d['Суть'] for d in e.diags] == ['nonfinal'] and e.trust == moment, 'hold: не операція, межа довіри')


def check_mono_corp_example():
    iban = D.MONO_CORP_TX['counterIban']
    rec, p = _mono_rec('mono-corp', [D.MONO_CORP_TX], iban)
    e = E.run(rec, p)
    _expect(len(e.ops) == 1 and not e.diags, 'приклад юросіб: одна операція без діагностики')
    o = e.ops[0]
    _expect(_utc_plus3(1719577881) == datetime(2024, 6, 28, 15, 31, 21), 'арифметика прикладу')
    want = {'НомерСчета': iban, 'Валюта': '980', 'ДатаОперации': '2024-06-28T15:31:21',       # completedTime, не time
            'ДатаДокумента': '2024-06-28', 'Сумма': '123.45', 'Направление': 'Поступило',
            'НомерДокумента': D.MONO_CORP_TX['id'], 'ИдентификаторОперации': D.MONO_CORP_TX['id'],
            'КонтрагентКод': '21133352', 'КонтрагентНомерСчета': D.MONO_CORP_TX['counterIban'],
            'НазначениеПлатежа': 'Оплата за щось цікаве \U0001F60A Фактичний платник: '
                                 'ТОВАРИСТВО З ОБМЕЖЕНОЮ ВІДПОВІДАЛЬНІСТЮ ПРИКЛАД 3096889974'}
    for k, v in want.items():
        _expect(o[k] == v, 'приклад юросіб, поле %s' % k)
    old = O.run(rec, p).rows[0].fields
    _expect(old['ДатаДокумента'] == datetime(2024, 6, 28, 15, 31, 21), 'юросіб, стара обробка: ключ — completedTime')
    # YAML-приклад дає counterEdrpou числом: код лишається рядком без розділювачів груп
    rec, p = _mono_rec('mono-corp', [dict(D.MONO_CORP_TX, counterEdrpou=21133352)], iban)
    _expect(E.run(rec, p).ops[0]['КонтрагентКод'] == '21133352', 'counterEdrpou числом')


def check_mono_corp_statuses():
    iban = D.MONO_CORP_TX['counterIban']
    for status, essence in (('PENDING', 'nonfinal'), ('DECLINED', 'cancelled')):
        rec, p = _mono_rec('mono-corp', [dict(D.MONO_CORP_TX, status=status)], iban)
        e = E.run(rec, p)
        _expect(not e.ops and [d['Суть'] for d in e.diags] == [essence], 'status %s' % status)
    rec, p = _mono_rec('mono-corp', [dict(D.MONO_CORP_TX, status='PENDING')], iban)
    _expect(E.run(rec, p).trust == _utc_plus3(1719472805), 'PENDING: межа довіри — time (створення), не completedTime')
    # реверс окремим записом зі своїм id: звичайна операція (випадок а)
    rec, p = _mono_rec('mono-corp', [dict(D.MONO_CORP_TX, reverse=True, id='another-id')], iban)
    _expect(len(E.run(rec, p).ops) == 1, 'реверс зі своїм id — операція')


def check_documented_limits():
    _expect(C.FOP_WINDOW_SECONDS <= D.MONO_PERSONAL_MAX_RANGE_SECONDS, 'відрізок ФОП в межах 31 доби + 1 год')
    worst = 0
    day = datetime(2026, 1, 1)
    while day < datetime(2027, 1, 1):                 # кожен початок відрізка протягом року, зокрема через обидва переходи
        a, b = day, day + timedelta(seconds=C.FOP_WINDOW_SECONDS)
        worst = max(worst, kyiv.local_to_unix(b) - kyiv.local_to_unix(a))
        day += timedelta(days=1)
    _expect(worst <= D.MONO_PERSONAL_MAX_RANGE_SECONDS, 'довжина відрізка ФОП в UTC ≤ 2682000 с (найгірше %d)' % worst)
    _expect(C.PAGE_SIZE_MONO <= D.MONO_CORP_LIMIT_MAX, 'limit юросіб ≤ 500')
    _expect(S.PRIVAT_LIMIT <= D.PRIVAT_LIMIT_RECOMMENDED_MAX, 'limit ПриватБанку ≤ 100')
    sc = S.by_name('СинтОкна')
    pauses = E.run(sc.recording(), sc.params).pauses
    between = [x for x in pauses if x['Причина'] == 'between-statements']
    _expect(between and all(x['Секунд'] >= D.MONO_PERSONAL_MIN_INTERVAL_SECONDS for x in between), 'ФОП: ≥ 60 с між запитами виписки')
    sc = [s for s in S.all_scenarios() if s.bank == 'privat' and s.sid == 'СинтСтатусы'][0]
    pauses = E.run(sc.recording(), sc.params).pauses
    _expect(pauses and all(x['Секунд'] >= D.PRIVAT_MIN_INTERVAL_SECONDS for x in pauses), 'ПриватБанк: ≥ 1 с між сторінками')


CHECKS = [check_privat_example_expected, check_privat_example_old, check_privat_trantype_d, check_privat_pr_pr_legend,
          check_mono_personal_example, check_mono_corp_example, check_mono_corp_statuses, check_documented_limits]


def run():
    """-> [(ім'я, пройшла, деталь)]."""
    res = []
    for fn in CHECKS:
        try:
            fn()
            res.append((fn.__name__, True, ''))
        except AssertionError as e:
            res.append((fn.__name__, False, str(e)))
    return res
