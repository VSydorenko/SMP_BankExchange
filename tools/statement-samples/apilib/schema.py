# -*- coding: utf-8 -*-
"""Ролі полів тіл відповідей API для знеособлення (Step 2 плану 05а). Таблиця — за документацією банків; невідоме поле
— помилка, а не мовчазне збереження (як `sslib.schema` для файлових форматів).

Ролі (ті самі, що в `sslib.gen.Fakes.apply`, плюс ідентифікатор операції):
  KEEP      сума, дата, час, валюта, статус, прапорці, МФО, номер документа, довжини — те, що вимірює оракул;
  CODE      ЄДРПОУ / ІПН (контрольна сума правильна);   ACC   рахунок (IBAN або старий номер, ядро номера спільне);
  NAME      назва / ПІБ;   BANKNAME   назва банку;   PURPOSE   призначення / коментар;
  ID        ідентифікатор операції / запису / квитанції: вигаданий тієї самої форми й довжини, зв'язки між полями
            (ID і TECHNICAL_TRANSACTION_ID -- одне значення, а значить одна заміна; ID починається з REF -- зв'язок зберігається; якщо
            TECHNICAL_TRANSACTION_ID відрізняється від ID, це окреме значення зі своєю заміною, суфікси не зберігаються);
  SCRAMBLE  решта чутливого: цифри й літери перемішуються з тією ж формою.

Шлях запиту (`request.path`, `request.query`) знеособлюється тими самими правилами: IBAN рахунку, ідентифікатор рахунку
monobank ФОП, `acc` ПриватБанку.
"""

PRIVAT_TX = {
    'AUT_MY_CRF': 'CODE', 'AUT_MY_MFO': 'KEEP', 'AUT_MY_ACC': 'ACC', 'AUT_MY_NAM': 'NAME', 'AUT_MY_MFO_NAME': 'BANKNAME',
    'AUT_MY_MFO_CITY': 'KEEP', 'AUT_CNTR_CRF': 'CODE', 'AUT_CNTR_MFO': 'KEEP', 'AUT_CNTR_ACC': 'ACC',
    'AUT_CNTR_NAM': 'NAME', 'AUT_CNTR_MFO_NAME': 'BANKNAME', 'AUT_CNTR_MFO_CITY': 'KEEP', 'CCY': 'KEEP', 'FL_REAL': 'KEEP',
    'PR_PR': 'KEEP', 'DOC_TYP': 'KEEP', 'NUM_DOC': 'KEEP', 'DAT_KL': 'KEEP', 'DAT_OD': 'KEEP', 'OSND': 'PURPOSE',
    'SUM': 'KEEP', 'SUM_E': 'KEEP', 'REF': 'ID', 'REFN': 'KEEP', 'TIM_P': 'KEEP', 'DATE_TIME_DAT_OD_TIM_P': 'KEEP',
    'ID': 'ID', 'TRANTYPE': 'KEEP', 'DLR': 'ID', 'TECHNICAL_TRANSACTION_ID': 'ID', 'UETR': 'ID', 'ULTMT': 'KEEP',
    'PAYER_ULTMT_NCEO': 'CODE', 'PAYER_ULTMT_DOCUMENT': 'SCRAMBLE', 'PAYER_ULTMT_NAME': 'NAME',
    'PAYER_ULTMT_COUNTRY_CODE': 'KEEP', 'RECIPIENT_ULTMT_NCEO': 'CODE', 'RECIPIENT_ULTMT_DOCUMENT': 'SCRAMBLE',
    'RECIPIENT_ULTMT_NAME': 'NAME', 'RECIPIENT_ULTMT_COUNTRY_CODE': 'KEEP', 'STRUCT_CODE': 'KEEP', 'STRUCT_TYPE': 'KEEP',
    'STRUCT_CATEGORY': 'PURPOSE'}
PRIVAT_SETTINGS = {'phase': 'KEEP', 'dates_without_oper_day': 'ARRAY', 'today': 'KEEP', 'lastday': 'KEEP', 'work_balance': 'KEEP',
                    'server_date_time': 'KEEP', 'date_final_statement': 'KEEP'}
PRIVAT_PAGE = {'settings': 'OBJECT', 'status': 'KEEP', 'type': 'KEEP', 'exist_next_page': 'KEEP', 'next_page_id': 'ID', 'message': 'KEEP',
               'code': 'KEEP', 'serviceCode': 'KEEP', 'appErrorCode': 'KEEP', 'requestId': 'ID',
               'transactions': 'ARRAY', 'balances': 'ARRAY'}
PRIVAT_BALANCE = {
    'acc': 'ACC', 'atp': 'KEEP', 'balanceIn': 'SCRAMBLE', 'balanceInEq': 'SCRAMBLE', 'balanceOut': 'SCRAMBLE',
    'balanceOutEq': 'SCRAMBLE', 'bgfIBrnm': 'KEEP', 'brnm': 'KEEP', 'currency': 'KEEP', 'date_close_acc': 'KEEP',
    'date_open_acc_reg': 'KEEP', 'date_open_acc_sys': 'KEEP', 'dpd': 'KEEP', 'flmn': 'KEEP', 'is_final_bal': 'KEEP',
    'nameACC': 'NAME', 'state': 'KEEP', 'turnoverCred': 'SCRAMBLE', 'turnoverCredEq': 'SCRAMBLE', 'turnoverDebt': 'SCRAMBLE',
    'turnoverDebtEq': 'SCRAMBLE'}

MONO_FOP_TX = {
    'id': 'ID', 'time': 'KEEP', 'description': 'PURPOSE', 'mcc': 'KEEP', 'originalMcc': 'KEEP', 'hold': 'KEEP',
    'amount': 'KEEP', 'operationAmount': 'KEEP', 'currencyCode': 'KEEP', 'commissionRate': 'KEEP', 'cashbackAmount': 'KEEP',
    'balance': 'SCRAMBLE', 'comment': 'PURPOSE', 'receiptId': 'ID', 'invoiceId': 'ID', 'counterEdrpou': 'CODE',
    'counterIban': 'ACC', 'counterName': 'NAME'}
MONO_FOP_CLIENT = {'clientId': 'ID', 'name': 'NAME', 'webHookUrl': 'SCRAMBLE', 'permissions': 'KEEP', 'accounts': 'ARRAY',
                   'jars': 'ARRAY'}
MONO_FOP_ACCOUNT = {'id': 'ID', 'sendId': 'ID', 'currencyCode': 'KEEP', 'cashbackType': 'KEEP', 'balance': 'SCRAMBLE',
                    'creditLimit': 'SCRAMBLE', 'maskedPan': 'ARRAY', 'type': 'KEEP', 'iban': 'ACC'}

MONO_FOP_JAR = {'id': 'ID', 'sendId': 'ID', 'title': 'NAME', 'description': 'PURPOSE', 'currencyCode': 'KEEP',
                'balance': 'SCRAMBLE', 'goal': 'SCRAMBLE'}

MONO_CORP_TX = {
    'id': 'ID', 'externalReference': 'ID', 'time': 'KEEP', 'completedTime': 'KEEP', 'description': 'PURPOSE', 'amount': 'KEEP',
    'currencyCode': 'KEEP', 'receiptId': 'ID', 'counterEdrpou': 'CODE', 'counterIban': 'ACC', 'counterName': 'NAME',
    'reverse': 'KEEP', 'status': 'KEEP', 'ultimateDebit': 'OBJECT'}
MONO_CORP_ULTIMATE = {'name': 'NAME', 'idCode': 'CODE'}
MONO_CORP_BALANCE = {'date': 'KEEP', 'balance': 'SCRAMBLE', 'isFinal': 'KEEP'}
MONO_CORP_ACCOUNT = {'iban': 'ACC', 'currency': 'KEEP', 'balance': 'SCRAMBLE'}
ERROR_BODY = {'errorCode': 'KEEP', 'errorDescription': 'KEEP'}

ROLES = {
    'privat': {'page': PRIVAT_PAGE, 'tx': PRIVAT_TX, 'settings': PRIVAT_SETTINGS, 'balance': PRIVAT_BALANCE},
    'mono-fop': {'tx': MONO_FOP_TX, 'client': MONO_FOP_CLIENT, 'account': MONO_FOP_ACCOUNT, 'jar': MONO_FOP_JAR,
                 'error': ERROR_BODY},
    'mono-corp': {'tx': MONO_CORP_TX, 'ultimate': MONO_CORP_ULTIMATE, 'balance': MONO_CORP_BALANCE,
                  'caccount': MONO_CORP_ACCOUNT, 'error': ERROR_BODY},
}


def unknown_fields(bank, section, obj):
    """Поля `obj`, яких немає в таблиці ролей розділу, — Step 2 мусить зупинитися на них, а не зберегти мовчки."""
    return sorted(set(obj) - set(ROLES[bank][section]))


# ---------------------------------------------------------------------- обхід дерева тіла
class UnknownField(ValueError):
    """Поле поза таблицею ролей, неочікуваний вигляд значення: Step 2 зупиняється, а не зберігає мовчки. У повідомленні --
    лише банк, розділ і ІМ'Я поля, ніколи значення."""


# (банк, розділ, поле) -> що всередині контейнера: ('arr', розділ елементів) | ('obj', розділ) | ('scalars', роль елементів)
CHILD = {
    ('privat', 'page', 'transactions'): ('arr', 'tx'),
    ('privat', 'page', 'balances'): ('arr', 'balance'),
    ('privat', 'page', 'settings'): ('obj', 'settings'),
    ('privat', 'settings', 'dates_without_oper_day'): ('scalars', 'KEEP'),
    ('mono-fop', 'client', 'accounts'): ('arr', 'account'),
    ('mono-fop', 'client', 'jars'): ('arr', 'jar'),
    ('mono-fop', 'account', 'maskedPan'): ('scalars', 'SCRAMBLE'),
    ('mono-corp', 'tx', 'ultimateDebit'): ('obj', 'ultimate'),
}


def root_section(bank, path, status, kind):
    """Розділ кореня тіла за банком, шляхом запиту, статусом і видом кореня ('obj' | 'arr')."""
    if bank == 'privat':
        if kind != 'obj':
            raise UnknownField('privat: корінь тіла не об\'єкт')
        return 'page'
    if bank == 'mono-fop':
        if path == '/personal/client-info' and status == 200:
            return 'client' if kind == 'obj' else _bad(bank, 'client-info')
        if path.startswith('/personal/statement/') and status == 200:
            return 'tx' if kind == 'arr' else _bad(bank, 'statement')
        return 'error' if kind == 'obj' else _bad(bank, 'error')
    if status == 200 and kind == 'arr':
        if path == '/ext/v1/accounts':
            return 'caccount'
        if path.endswith('/balances'):
            return 'balance'
        if path.startswith('/ext/v1/statement/'):
            return 'tx'
        _bad(bank, 'path')
    return 'error' if kind == 'obj' else _bad(bank, 'error')


def _bad(bank, what):
    raise UnknownField('%s: неочікуваний вигляд кореня тіла (%s)' % (bank, what))


def leaves(bank, path, status, root):
    """Усі скалярні вузли тіла з ролями: [(роль, вузол, шлях_у_дереві)]. Невідоме поле -> UnknownField (ім'я, не значення).
    `root` -- вузол `jsonspan`."""
    out = []

    def scalar_ok(role, nd, where):
        if nd.kind in ('obj', 'arr'):
            raise UnknownField('%s: поле %s має бути скаляром' % (bank, where))
        out.append((role, nd, where))

    def obj(section, nd, where):
        table = ROLES[bank][section]
        for key, v in nd.items:
            if key not in table:
                raise UnknownField('%s: невідоме поле %s.%s' % (bank, section, key))
            role = table[key]
            here = where + (key,)
            if role in ('ARRAY', 'OBJECT'):
                if v.kind == 'lit' and v.value is None:
                    continue
                kind, target = CHILD[(bank, section, key)]
                if kind == 'arr':
                    if v.kind != 'arr':
                        raise UnknownField('%s: поле %s.%s має бути масивом' % (bank, section, key))
                    for i, it in enumerate(v.items):
                        if it.kind != 'obj':
                            raise UnknownField('%s: елемент %s.%s має бути об\'єктом' % (bank, section, key))
                        obj(target, it, here + (i,))
                elif kind == 'obj':
                    if v.kind != 'obj':
                        raise UnknownField('%s: поле %s.%s має бути об\'єктом' % (bank, section, key))
                    obj(target, v, here)
                else:
                    if v.kind != 'arr':
                        raise UnknownField('%s: поле %s.%s має бути масивом' % (bank, section, key))
                    for i, it in enumerate(v.items):
                        scalar_ok(target, it, here + (i,))
            else:
                scalar_ok(role, v, here)

    section = root_section(bank, path, status, root.kind)
    if root.kind == 'obj':
        obj(section, root, ())
    else:
        for i, it in enumerate(root.items):
            if it.kind != 'obj':
                raise UnknownField('%s: елемент кореня має бути об\'єктом' % bank)
            obj(section, it, (i,))
    return out
