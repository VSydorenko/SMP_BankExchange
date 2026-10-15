# -*- coding: utf-8 -*-
"""Еталон очікуваного конверта `СМП_ТестЭталон<Банк><Ид>` для запису відповідей API. JSON, UTF-8, версія 1.

Рахується ТІЛЬКИ Python-оракулом (`expected.run`, `oracle_old.run`) з того самого запису, що лежить у макеті
`СМП_ТестОтвет<Банк><Ид>`. Руками й BSL-кодом не рахується.

Формат (поля — російською, як у конверті D28; рядки дат — `ГГГГ-ММ-ДДTгг:хх:сс`, суми — рядки з двома знаками):

```
{ "format": "smp-api-etalon", "formatVersion": 1,
  "bank": "privat" | "mono-fop" | "mono-corp", "id": "Синт…", "synthetic": true,
  "title": "...", "reviewFocus": [1, 2],
  "recording": {"макет": "СМП_ТестОтвет…", "обменов": N},
  "parameters": {"НомерСчета": "...", "НачалоПериода": "...", "КонецПериода": "..."},
  "dependsOn": ["...", ...],                       // від чого залежить еталон (див. нижче)
  "expected": {                                    // режим «очікуване»: що мусить покласти в конверт конектор
     "ЧтениеПолное": true, "ГраницаДоверия": "…", "КлассОтказа": "" | "Повторить" | "ДействиеЧеловека",
     "Операции": [ {колонки конверта D28 без СырыеДанные}, … ],
     "Диагностика": [ {"Уровень","ПорядковыйНомер","Суть","Отступ","Факты":{…}}, … ],
     "ЧужиеСчета": [ {"НомерСчета","НомераСтрок":[…]} ],
     "Запросы": [ {"Метод","Хост","Путь","Запрос":[[ім'я,значення],…]} ],   // у порядку обмінів запису
     "Паузы": [ {"ПослеЗапроса": k, "Секунд": s, "Причина": "…"} ],
     "ОтступыПрименены": ["dev2", …] },
  "oldProcessing": {                               // режим «стара обробка»: лише поля ключа D17
     "Параметры": {...}, "ПоляКлюча": [ {"ПорядковыйНомер","ДатаДокумента","НомерДокумента","КонтрагентНомерСчета","Сумма"} ],
     "ПоФорматуСчета": {"14": [...], "iban": [...]},     // лише ПриватБанк: ключі при двох форматах НомерСчета в базі
     "Исключение": null | {"kind","text"}, "Полная": …,
     "ПропущеноБезСледа": [ {"Причина","Ид","ПорядковыйНомер"} ], "Допущения": ["PB-REGL", …] } }
```

* **`Диагностика.Суть`** — стабільний код, а не текст: тест не прив'язується до формулювання, яке ще не визначено.
  Коди: `nonfinal`, `cancelled` (Предупреждение); `reversal-state-change`, `unknown-state`, `unknown-direction`,
  `bad-amount`, `bad-date`, `unknown-currency`, `conflicting-duplicate` (Ошибка); `account-not-found`, `read-failed`, `work-balance` —
  збій читання з непорожнім класом (Предупреждение: неповне читання, курсор утримується).
  `Факты` — те, що текст для людини мусить назвати (банк, статус, опис банку) і чого в ньому не мусить бути (токена).
* **`dependsOn`** — що з зафіксованого ще не виміряно й може змінити еталон: `НомерСчетаВБазе` (формат `НомерСчета`
  рахунку ПриватБанку в базі — питання власнику), `ИдентификаторПриват` (вибір D36 п. 6), `РеверсСлучай` (випадок
  а/б D36 п. 5 — вимір задачі 1), `ПаузаПослеClientInfo` (D36 п. 9), `РазмерСтраницыMono` (500 документація не
  підтверджує), `ФильтрВалютыПриват` (відступ 1 для валюти), `ТлумачениеГраницы` (як тлумачити `date_final_statement` і день без `isFinal`; береться раніша межа).
* **`ЧужиеСчета`** — як у еталоні зразків: операції, чий власний рахунок не збігається з `Параметры.НомерСчета`;
  рівень діагностики для них пише точка читання (D30), конектор лише віддає операцію.
* `Запросы` — КОПІЯ запитів запису (метод, хост, шлях, пари запиту), а не обчислення з параметрів: для синтетики це
  самоперевірка генератора (`expected.verify_requests`), для справжніх записів — те, що зробив рекордер.
* `ПорядковыйНомер` — номер запису в порядку читання, з одиниці, усі записи всіх сторінок (зокрема пропущені).
* `СырыеДанные` колонки конверта в еталоні немає: це вихідний запис операції, він порівнюється окремо (тест перевіряє
  лише, що не порожній).
"""
import json

from . import common as C, expected as E, oracle_old as O
from dataclasses import replace

FORMAT = 'smp-api-etalon'
VERSION = 1


def _old_section(rec, p):
    res = O.run(rec, p)
    sec = {'Параметры': {'ФорматНомераСчета': p.old_account_format if rec.bank == 'privat' else '',
                         'НомерСчетаУстаревший': p.old_account_obsolete,
                         'ВалютаСчета': p.old_account_currency, 'ПоясСеанса': p.old_session_tz},
           'ПоляКлюча': _key(res),
           'Исключение': res.error, 'Полная': res.complete,
           'ПропущеноБезСледа': [{'Причина': a, 'Ид': b, 'ПорядковыйНомер': c} for a, b, c in res.dropped],
           'Допущения': sorted(res.used)}
    return sec, res


def _key(res):
    return [{'ПорядковыйНомер': r.n, 'ДатаДокумента': C.iso(r.fields['ДатаДокумента']), 'НомерДокумента': r.fields['НомерДокумента'],
             'КонтрагентНомерСчета': r.fields['КонтрагентНомерСчета'], 'Сумма': C.amount_str(r.fields['Сумма'])} for r in res.rows]


def build(scn, disabled=frozenset()):
    rec = scn.recording()
    p = scn.params
    exp = E.run(rec, p, disabled)
    old, old_res = _old_section(rec, p)
    depends = set()
    if rec.bank == 'privat':
        variants = {}
        for fmt in ('14', 'iban'):
            variants[fmt] = _key(O.run(rec, replace(p, old_account_format=fmt)))
        old['ПоФорматуСчета'] = variants
        if variants['14'] != variants['iban']:
            depends.add('НомерСчетаВБазе')
        if exp.ops or any(d['Суть'] == 'reversal-state-change' for d in exp.diags):
            depends.add('ИдентификаторПриват')
    if any(d['Суть'] == 'reversal-state-change' for d in exp.diags) or 'dev4' in exp.applied:
        depends.add('РеверсСлучай')
    if any(x['Причина'] == 'after-client-info' for x in exp.pauses):
        depends.add('ПаузаПослеClientInfo')
    if rec.bank != 'privat' and any(_page_len(e) >= C.PAGE_SIZE_MONO for e in C.statement_exchanges(rec)):
        depends.add('РазмерСтраницыMono')
    if exp.bank_boundary is not None and exp.bank_boundary < p.period_end:
        depends.add('ТлумачениеГраницы')
    if rec.bank == 'privat' and any(o['Валюта'] not in ('980', '') for o in exp.ops):
        depends.add('ФильтрВалютыПриват')
    d = {'format': FORMAT, 'formatVersion': VERSION, 'bank': rec.bank, 'id': scn.sid, 'synthetic': True, 'title': scn.title,
         'reviewFocus': scn.focus, 'recording': {'макет': scn.name, 'обменов': len(rec.exchanges)},
         'parameters': scn.params.to_json(), 'dependsOn': sorted(depends),
         'expected': {'ЧтениеПолное': exp.complete, 'ГраницаДоверия': C.iso(exp.trust), 'КлассОтказа': exp.failure_class,
                      'Операции': exp.ops, 'Диагностика': exp.diags,
                      'ЧужиеСчета': [{'НомерСчета': a, 'НомераСтрок': ns} for a, ns in exp.foreign.items()],
                      'Запросы': exp.requests, 'Паузы': exp.pauses, 'ОтступыПрименены': sorted(exp.applied)},
         'oldProcessing': old}
    return d, exp, old_res


def _page_len(ex):
    from . import recording as R
    try:
        js = R.body_json(ex)
    except R.NotJson:
        return 0
    return len(js) if isinstance(js, list) else 0




def dumps(d):
    """JSON з відступами; елементи великих списків (операції, ключі, запити, паузи, діагностика) — по одному на рядок,
    щоб еталон на 500 операцій лишався читабельним і не роздувався."""
    return _fmt(d, 0) + '\n'


def _fmt(v, level):
    pad = ' ' * (level + 1)
    if isinstance(v, dict):
        if not v:
            return '{}'
        body = ',\n'.join('%s%s: %s' % (pad, json.dumps(k, ensure_ascii=False), _fmt(x, level + 1)) for k, x in v.items())
        return '{\n' + body + '\n' + ' ' * level + '}'
    if isinstance(v, list):
        if not v:
            return '[]'
        if all(isinstance(x, (dict, list)) for x in v):
            body = ',\n'.join(pad + json.dumps(x, ensure_ascii=False, separators=(',', ':')) for x in v)
            return '[\n' + body + '\n' + ' ' * level + ']'
        return json.dumps(v, ensure_ascii=False)
    return json.dumps(v, ensure_ascii=False)
