# -*- coding: utf-8 -*-
"""Ролі полів тіл відповідей API для знеособлення (Step 2 плану 05а). Таблиця — за документацією банків; невідоме поле
— помилка, а не мовчазне збереження (як `sslib.schema` для файлових форматів).

Ролі (ті самі, що в `sslib.gen.Fakes.apply`, плюс ідентифікатор операції):
  KEEP      сума, дата, час, валюта, статус, прапорці, МФО, номер документа, довжини — те, що вимірює оракул;
  CODE      ЄДРПОУ / ІПН (контрольна сума правильна);   ACC   рахунок (IBAN або старий номер, ядро номера спільне);
  NAME      назва / ПІБ;   BANKNAME   назва банку;   PURPOSE   призначення / коментар;
  ID        ідентифікатор операції / запису / квитанції: вигаданий тієї самої форми й довжини, зв'язки між полями
            (ID і TECHNICAL_TRANSACTION_ID = ID + «_online»; REF) зберігаються;
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
PRIVAT_PAGE = {'status': 'KEEP', 'type': 'KEEP', 'exist_next_page': 'KEEP', 'next_page_id': 'ID', 'message': 'KEEP',
               'transactions': 'ARRAY'}

MONO_FOP_TX = {
    'id': 'ID', 'time': 'KEEP', 'description': 'PURPOSE', 'mcc': 'KEEP', 'originalMcc': 'KEEP', 'hold': 'KEEP',
    'amount': 'KEEP', 'operationAmount': 'KEEP', 'currencyCode': 'KEEP', 'commissionRate': 'KEEP', 'cashbackAmount': 'KEEP',
    'balance': 'SCRAMBLE', 'comment': 'PURPOSE', 'receiptId': 'ID', 'invoiceId': 'ID', 'counterEdrpou': 'CODE',
    'counterIban': 'ACC', 'counterName': 'NAME'}
MONO_FOP_CLIENT = {'clientId': 'ID', 'name': 'NAME', 'webHookUrl': 'SCRAMBLE', 'permissions': 'KEEP', 'accounts': 'ARRAY',
                   'jars': 'ARRAY'}
MONO_FOP_ACCOUNT = {'id': 'ID', 'sendId': 'ID', 'currencyCode': 'KEEP', 'cashbackType': 'KEEP', 'balance': 'SCRAMBLE',
                    'creditLimit': 'SCRAMBLE', 'maskedPan': 'ARRAY', 'type': 'KEEP', 'iban': 'ACC'}

MONO_CORP_TX = {
    'id': 'ID', 'externalReference': 'ID', 'time': 'KEEP', 'completedTime': 'KEEP', 'description': 'PURPOSE', 'amount': 'KEEP',
    'currencyCode': 'KEEP', 'receiptId': 'ID', 'counterEdrpou': 'CODE', 'counterIban': 'ACC', 'counterName': 'NAME',
    'reverse': 'KEEP', 'status': 'KEEP', 'ultimateDebit': 'OBJECT'}
MONO_CORP_ULTIMATE = {'name': 'NAME', 'idCode': 'CODE'}
ERROR_BODY = {'errorCode': 'KEEP', 'errorDescription': 'KEEP'}

ROLES = {
    'privat': {'page': PRIVAT_PAGE, 'tx': PRIVAT_TX},
    'mono-fop': {'tx': MONO_FOP_TX, 'client': MONO_FOP_CLIENT, 'account': MONO_FOP_ACCOUNT, 'error': ERROR_BODY},
    'mono-corp': {'tx': MONO_CORP_TX, 'ultimate': MONO_CORP_ULTIMATE, 'error': ERROR_BODY},
}


def unknown_fields(bank, section, obj):
    """Поля `obj`, яких немає в таблиці ролей розділу, — Step 2 мусить зупинитися на них, а не зберегти мовчки."""
    return sorted(set(obj) - set(ROLES[bank][section]))
