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

ПУМБ (план 05б-2, задача 2a): ролі за swagger Veganet (`VeganetDocumentItem`, `VeganetClientRestAccount`, `DocumentFilter`,
`EJBPeriodTransactionsRequest/Response`) і за формою відповіді автентифікації, яку пише рекордер, -- **ГІПОТЕЗА до запису**: усе, чого
swagger не описує (форми помилок), звужено до того, що відоме, а решта -- зупинка (`UnknownField`). Числові `id` / `docId` / `accountId` /
`transactionId` / `orderedLastId` -- ID: одне значення (текст числа) = одна заміна в усіх відповідях і ТІЛАХ ЗАПИТІВ (`accountId` запиту =
`accountId` відповіді; `documentAccounts` рекордера -- рядки, у swagger -- числа, заміна та сама). `userIdentity`, `responsible`,
`firstSignature`, `secondSignature` -- NAME (не KEEP), перевіряються підрядком без нижньої межі довжини (`step2.person_tokens`).
"""

import re

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

# ---------------------------------------------------------------------- ПУМБ (Veganet): ролі за swagger, ГІПОТЕЗА до запису
# GET /account -> [VeganetClientRestAccount]
PUMB_ACCOUNT = {
    'id': 'ID', 'accountId': 'ID', 'mfo': 'KEEP', 'currency': 'KEEP', 'number': 'ACC', 'name': 'NAME', 'state': 'KEEP', 'hostId': 'KEEP',
    'branchId': 'KEEP', 'clientId': 'ID', 'clientName': 'NAME', 'clientOkpo': 'CODE', 'isDefault': 'KEEP', 'canDebit': 'KEEP',
    'isCardAccount': 'KEEP', 'canCreatePdfPropertyAccount': 'KEEP', 'iban': 'ACC', 'isOwnerHost': 'KEEP', 'balance': 'SCRAMBLE',
    'rest': 'SCRAMBLE', 'holds': 'SCRAMBLE', 'balanceUah': 'SCRAMBLE', 'restUah': 'SCRAMBLE', 'holdsUah': 'SCRAMBLE',
    'lastActivity': 'KEEP', 'forecast': 'SCRAMBLE', 'inWork': 'SCRAMBLE'}
# POST /document/searcher -> [VeganetDocumentItem]
PUMB_DOC = {
    'id': 'ID', 'hostId': 'KEEP', 'docId': 'ID', 'viewTemplateId': 'KEEP', 'signTemplateId': 'KEEP', 'date': 'KEEP', 'state': 'KEEP',
    'type': 'KEEP', 'firstSignature': 'NAME', 'secondSignature': 'NAME', 'errorReason': 'PURPOSE', 'number': 'KEEP', 'accountId': 'ID',
    'amount': 'KEEP', 'currencyCode': 'KEEP', 'description': 'PURPOSE', 'createdOn': 'KEEP', 'isImported': 'KEEP',
    'userIdentity': 'NAME', 'origin': 'KEEP', 'destinationHostId': 'KEEP', 'system': 'KEEP', 'direction': 'KEEP',
    'operationDate': 'KEEP', 'senderName': 'NAME', 'correspondentName': 'NAME', 'senderTaxId': 'CODE', 'correspondentTaxId': 'CODE',
    'senderBankMfo': 'KEEP', 'correspondentBankMfo': 'KEEP', 'senderBankName': 'BANKNAME', 'correspondentBankName': 'BANKNAME',
    'senderAccountNumber': 'ACC', 'correspondentAccountNumber': 'ACC', 'responsible': 'NAME', 'expenseItems': 'PURPOSE',
    'isRead': 'KEEP', 'senderIBAN': 'ACC', 'correspondentIBAN': 'ACC', 'pagingRowInfo': 'OBJECT'}
PUMB_ROWINFO = {'rowNumber': 'KEEP', 'rowIdentity': 'ID', 'sortedValue': 'ID'}
# POST /document/period-transactions -> EJBPeriodTransactionsResponse
PUMB_PTX = {'header': 'OBJECT', 'transactions': 'ARRAY'}
PUMB_PTX_HEADER = {'dateFrom': 'KEEP', 'dateTo': 'KEEP', 'currency': 'KEEP', 'accountName': 'NAME', 'inSaldo': 'SCRAMBLE',
                   'outSaldo': 'SCRAMBLE', 'debitTurn': 'SCRAMBLE', 'creditTurn': 'SCRAMBLE', 'iban': 'ACC'}
PUMB_PTX_TX = {
    'dcFlag': 'KEEP', 'accountName': 'NAME', 'currency': 'KEEP', 'amount': 'KEEP', 'transactionId': 'ID', 'documentDate': 'KEEP',
    'processDate': 'KEEP', 'documentNumber': 'KEEP', 'corrBankMfo': 'KEEP', 'corrBankName': 'BANKNAME', 'corrAccountNumber': 'ACC',
    'corrName': 'NAME', 'corrOkpo': 'CODE', 'narrative': 'PURPOSE', 'comissionType': 'KEEP', 'iban': 'ACC', 'corrIban': 'ACC'}
# Відповідь токен-ендпоінта в записі рекордера ЗАМАСКОВАНА (значення -- літера->a/A, цифра->9); жива форма -- Keycloak. Токени й сесія -- SCRAMBLE.
PUMB_AUTH = {'access_token': 'SCRAMBLE', 'refresh_token': 'SCRAMBLE', 'id_token': 'SCRAMBLE', 'session_state': 'SCRAMBLE',
             'expires_in': 'KEEP', 'refresh_expires_in': 'KEEP', 'not-before-policy': 'KEEP', 'token_type': 'KEEP', 'scope': 'KEEP'}
PUMB_AUTH_ERROR = {'error': 'KEEP', 'error_description': 'KEEP', 'error_uri': 'KEEP'}
# Форми помилок Veganet swagger не описує: лише відоме (Keycloak) й мінімум службових полів; решта -- зупинка до запису.
PUMB_ERROR = {'error': 'KEEP', 'error_description': 'KEEP', 'error_uri': 'KEEP', 'message': 'KEEP', 'status': 'KEEP', 'code': 'KEEP'}
# Тіла запитів (DocumentFilter, PagingRequest, EJBPeriodTransactionsRequest). Рекордер шле лише частину полів; решту swagger -- на випадок появи.
PUMB_REQ_SEARCHER = {
    'documentDirection': 'ARRAY', 'documentState': 'ARRAY', 'documentType': 'ARRAY', 'fromDate': 'KEEP', 'toDate': 'KEEP', 'documentRead': 'KEEP',
    'correspondentName': 'NAME', 'documentAmount': 'KEEP', 'amountCondition': 'KEEP', 'documentAccounts': 'ARRAY', 'pagingRequest': 'OBJECT',
    'origin': 'ARRAY', 'tax': 'CODE', 'bankName': 'BANKNAME', 'bankMfo': 'KEEP', 'accountNumber': 'ACC', 'correspondentIban': 'ACC',
    'description': 'PURPOSE'}
PUMB_REQ_PAGING = {'pageSize': 'KEEP', 'pagingSessionId': 'ID', 'orderedLastValue': 'ID', 'orderedLastId': 'ID', 'direction': 'KEEP',
                   'sortField': 'KEEP'}
PUMB_REQ_PTX = {'accountId': 'ID', 'dateFrom': 'KEEP', 'dateTo': 'KEEP', 'onlyHeader': 'KEEP', 'withoutAccountACL': 'KEEP'}

ROLES = {
    'privat': {'page': PRIVAT_PAGE, 'tx': PRIVAT_TX, 'settings': PRIVAT_SETTINGS, 'balance': PRIVAT_BALANCE},
    'mono-fop': {'tx': MONO_FOP_TX, 'client': MONO_FOP_CLIENT, 'account': MONO_FOP_ACCOUNT, 'jar': MONO_FOP_JAR,
                 'error': ERROR_BODY},
    'mono-corp': {'tx': MONO_CORP_TX, 'ultimate': MONO_CORP_ULTIMATE, 'balance': MONO_CORP_BALANCE,
                  'caccount': MONO_CORP_ACCOUNT, 'error': ERROR_BODY},
    'pumb': {'account': PUMB_ACCOUNT, 'doc': PUMB_DOC, 'rowinfo': PUMB_ROWINFO, 'ptx': PUMB_PTX, 'ptx_header': PUMB_PTX_HEADER,
             'ptx_tx': PUMB_PTX_TX, 'auth': PUMB_AUTH, 'autherror': PUMB_AUTH_ERROR, 'error': PUMB_ERROR,
             'req_searcher': PUMB_REQ_SEARCHER, 'req_paging': PUMB_REQ_PAGING, 'req_ptx': PUMB_REQ_PTX},
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
    ('pumb', 'doc', 'pagingRowInfo'): ('obj', 'rowinfo'),
    ('pumb', 'ptx', 'header'): ('obj', 'ptx_header'),
    ('pumb', 'ptx', 'transactions'): ('arr', 'ptx_tx'),
    ('pumb', 'req_searcher', 'documentDirection'): ('scalars', 'KEEP'),
    ('pumb', 'req_searcher', 'documentState'): ('scalars', 'KEEP'),
    ('pumb', 'req_searcher', 'documentType'): ('scalars', 'KEEP'),
    ('pumb', 'req_searcher', 'origin'): ('scalars', 'KEEP'),
    ('pumb', 'req_searcher', 'documentAccounts'): ('scalars', 'ID'),
    ('pumb', 'req_searcher', 'pagingRequest'): ('obj', 'req_paging'),
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
    if bank == 'pumb':
        return _pumb_response_section(path, status, kind)
    if status == 200 and kind == 'arr':
        if path == '/ext/v1/accounts':
            return 'caccount'
        if path.endswith('/balances'):
            return 'balance'
        if path.startswith('/ext/v1/statement/'):
            return 'tx'
        _bad(bank, 'path')
    return 'error' if kind == 'obj' else _bad(bank, 'error')


def _pumb_response_section(path, status, kind):
    """Розділ кореня тіла відповіді ПУМБ за кінцем шляху (перед ним -- префікс `/war_veganet_api`), статусом і видом кореня."""
    if path.endswith('/openid-connect/token'):
        return ('auth' if status == 200 else 'autherror') if kind == 'obj' else _bad('pumb', 'token')
    if status == 200:
        for tail, section, want in (('/account', 'account', 'arr'), ('/document/searcher', 'doc', 'arr'),
                                    ('/document/period-transactions', 'ptx', 'obj')):
            if path.endswith(tail):
                return section if kind == want else _bad('pumb', section)
        return _bad('pumb', 'path')
    return 'error' if kind == 'obj' else _bad('pumb', 'error')


def request_section(bank, path, kind):
    """Розділ кореня ТІЛА ЗАПИТУ (формат v2). Тіло запиту є лише в ПУМБ; решта банків його не має -- зупинка."""
    if bank != 'pumb':
        raise UnknownField('%s: тіло запиту не очікується' % bank)
    for tail, section in (('/document/searcher', 'req_searcher'), ('/document/period-transactions', 'req_ptx')):
        if path.endswith(tail):
            return section if kind == 'obj' else _bad(bank, 'тіло запиту')
    raise UnknownField('pumb: тіло запиту до невідомого шляху')


def _bad(bank, what):
    raise UnknownField('%s: неочікуваний вигляд кореня тіла (%s)' % (bank, what))


def leaves(bank, path, status, root):
    """Усі скалярні вузли тіла відповіді з ролями: [(роль, вузол, шлях_у_дереві)]. Невідоме поле -> UnknownField (ім'я, не значення).
    `root` -- вузол `jsonspan`."""
    return _walk(bank, root_section(bank, path, status, root.kind), root)


def request_leaves(bank, path, root):
    """Те саме для ТІЛА ЗАПИТУ (формат v2): ті самі ролі й та сама заміна, що й у відповіді."""
    return _walk(bank, request_section(bank, path, root.kind), root)


# Поля, роль яких залежить від ФОРМИ значення (явний виняток ролі, ЄДИНЕ місце; названо в README інструменту й у журналі).
# Курсор пагінації ПУМБ (`sortedValue` відповіді, `orderedLastValue` запиту) -- значення поля сортування: дата/час чи число (публічні за природою, KEEP) або рядок
# (ID: узгоджена заміна з мапи, однакова у відповіді й наступному запиті). ЧОМУ: роль ID для дати кидала б її в `build_sweep`, і збіжна KEEP-дата
# (`operationDate`) тихо змінювалась би, зсуваючи ключ D17 і межу довіри однаково в сирому й знеособленому записі -- жодна перевірка цього не бачить.
SHAPED_FIELDS = {'pumb': frozenset({'sortedValue', 'orderedLastValue'})}
_DATE_RX = re.compile(r'\d{2}\.\d{2}\.\d{4}(?: \d{2}:\d{2}:\d{2})?|\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}:\d{2})?')
_NUM_RX = re.compile(r'-?\d+(?:\.\d+)?')


def _by_shape(bank, key, role, nd):
    """Роль скаляра: для `SHAPED_FIELDS` -- KEEP, якщо значення ПОВНІСТЮ дата/час чи число, інакше таблична (ID)."""
    if key not in SHAPED_FIELDS.get(bank, ()) or nd.kind in ('lit',):
        return role
    if nd.kind == 'num':
        return 'KEEP'
    if nd.kind == 'str' and (_DATE_RX.fullmatch(nd.value) or _NUM_RX.fullmatch(nd.value)):
        return 'KEEP'
    return role


def _walk(bank, section, root):
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
                scalar_ok(_by_shape(bank, key, role, v), v, here)

    if root.kind == 'obj':
        obj(section, root, ())
    else:
        for i, it in enumerate(root.items):
            if it.kind != 'obj':
                raise UnknownField('%s: елемент кореня має бути об\'єктом' % bank)
            obj(section, it, (i,))
    return out
