# -*- coding: utf-8 -*-
"""Приклади з документації банків — вхід самоперевірки оракула (`selfcheck.py`).

Джерела (публічні, знято 2026-10-13; тексти лежать лише в гітігнорованій `temp/research/2026-10-13-readers/docs/`):
* ПриватБанк — «Опис API серверної частини Автоклієнт», версія 3.0.0, розділ «Отримання балансів і транзакцій за
  рахунками»: «Приклад відповіді з транзакціями» (одна транзакція; значення дослівно, у т. ч. латинські «i» в
  призначенні — так у документації);
* monobank персональне API — OpenAPI «Monobank open API» v250818, схема `StatementItems` (`example` кожного поля);
* monobank юросіб — OpenAPI corp-api v1.0.2 (`client-specification.yaml`), схеми `StatementItem` і
  `StatementUltimateDebit` (`example` кожного поля).

Це цитати рівно тієї довжини, яка потрібна для перевірки. Не сирі дані клієнта: усе це опубліковано банками.

Два значення замінено вигаданими, бо дослівні збігаються з лексемами сторожа (`guard`, нуль збігів — умова коміту):
`AUT_CNTR_CRF` (код з коректною контрольною сумою) і `cashbackAmount` monobank ФОП (у документації інше число)."""

PRIVAT_TX = {
    "AUT_MY_CRF": "31451288", "AUT_MY_MFO": "305299", "AUT_MY_ACC": "26184050001514",
    "AUT_MY_NAM": "Програмiсти та Ko МСБ-ТЕСТ ТОВ", "AUT_MY_MFO_NAME": "АТ КБ \"ПРИВАТБАНК\"", "AUT_MY_MFO_CITY": "Київ",
    "AUT_CNTR_CRF": "41234569", "AUT_CNTR_MFO": "305299", "AUT_CNTR_ACC": "70214924104032",
    "AUT_CNTR_NAM": "ПРОЦ ВИТР ЗА СТРОК КОШТ СУБ(UAH)", "AUT_CNTR_MFO_NAME": "АТ КБ \"ПРИВАТБАНК\"",
    "AUT_CNTR_MFO_CITY": "Київ", "CCY": "UAH", "FL_REAL": "r", "PR_PR": "r", "DOC_TYP": "m", "NUM_DOC": "K0108B1WKX",
    "DAT_KL": "07.01.2020", "DAT_OD": "07.01.2020",
    "OSND": "Нарахування вiдсоткiв згiдно з депозитним договором N...", "SUM": "0.01", "SUM_E": "0.01",
    "REF": "DNCHK0108B1WKX", "REFN": "1", "TIM_P": "02:58", "DATE_TIME_DAT_OD_TIM_P": "07.01.2020 02:58:00",
    "ID": "557091731", "TRANTYPE": "C", "DLR": "J63DNDSM0XHY5", "TECHNICAL_TRANSACTION_ID": "557091731_online"}
PRIVAT_NEXT_PAGE_ID = "620699370_online"      # з того самого прикладу: exist_next_page = true

# monobank ФОП: `example` полів StatementItems. «Список рахунків» (client-info) документація описує в UserInfo; тут лише
# те, що потрібно, щоб конектор знайшов рахунок за IBAN.
MONO_PERSONAL_TX = {
    "id": "ZuHWzqkKGVo=", "time": 1554466347, "description": "Покупка щастя", "mcc": 7997, "originalMcc": 7997,
    "hold": False, "amount": -95000, "operationAmount": -95000, "currencyCode": 980, "commissionRate": 0,
    "cashbackAmount": 18000, "balance": 10050000, "comment": "За каву", "receiptId": "XXXX-XXXX-XXXX-XXXX",
    "invoiceId": "2103.в.27", "counterEdrpou": "3096889974", "counterIban": "UA898999980000355639201001404",
    "counterName": "ТОВАРИСТВО З ОБМЕЖЕНОЮ ВІДПОВІДАЛЬНІСТЮ «ВОРОНА»"}

# monobank юросіб: `example` полів StatementItem (counterEdrpou у YAML-прикладі — число 21133352 при типі string)
MONO_CORP_TX = {
    "id": "ea4f9218-d134-431a-9169-88acab4454c9", "externalReference": "my-own-pretty-external-reference",
    "time": 1719472805, "completedTime": 1719577881, "description": "Оплата за щось цікаве \U0001F60A", "amount": 12345,
    "currencyCode": "980", "receiptId": "XXXX-XXXX-XXXX-XXXX", "counterEdrpou": "21133352",
    "counterIban": "UA293220010000026000000000001", "counterName": "ТОВАРИСТВО З ОБМЕЖЕНОЮ ВІДПОВІДАЛЬНІСТЮ ...",
    "reverse": False, "status": "DONE",
    "ultimateDebit": {"name": "ТОВАРИСТВО З ОБМЕЖЕНОЮ ВІДПОВІДАЛЬНІСТЮ ПРИКЛАД", "idCode": "3096889974"}}
CORP_STATUS_ENUM = ('DONE', 'PENDING', 'DECLINED')       # StatementItem.status
PRIVAT_PR_PR_LEGEND = {'p': 'проводиться', 't': 'сторнована', 'r': 'проведена', 'n': 'забракована'}

# Обмеження, названі в документації (використовує selfcheck)
MONO_PERSONAL_MAX_RANGE_SECONDS = 2682000      # «31 доба + 1 година»
MONO_PERSONAL_MIN_INTERVAL_SECONDS = 60        # «не частіше ніж 1 раз у 60 секунд»
MONO_CORP_LIMIT_MAX = 500                      # limit: maximum 500, default 10
PRIVAT_LIMIT_RECOMMENDED_MAX = 100             # «рекомендовано використовувати не більше ніж 100»
PRIVAT_MIN_INTERVAL_SECONDS = 1                # «не частіше 1 запиту в секунду»
