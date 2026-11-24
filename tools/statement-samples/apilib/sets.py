# -*- coding: utf-8 -*-
"""Наборы записей и еталонів для макетів тестового розширення (рішення R15: макети пакетами, а не по одному на запис).

Макетів 12 = 3 банки x {синтетика, run1} x {записи, еталони}. Запис усередині набору адресується ідентифікатором
(`СинтСтатусы`, `ЗапTxWorkLimit`), тож тест будь-якого з конекторів дістає його однією функцією-помічником
(`СМП_ТестЗаписиAPI` у тестовому розширенні).

Форми (JSON, UTF-8):
* набір записів (BinaryData, без BOM)::

    {"format": "smp-api-record-set", "formatVersion": 1|2, "bank": "privat|mono-fop|mono-corp|pumb", "kind": "synthetic|run1",
     "records": {"<Ид>": <пакет запису: smp-api-recording-pack, див. recording.py>, ...}}

* набір еталонів (TextDocument, UTF-8 з BOM, як наявні макети еталонів)::

    {"format": "smp-api-etalon-set", "formatVersion": 1|2, "bank": ..., "kind": ..., "etalons": {"<Ид>": <еталон, etalon.py>, ...}}

Імена макетів: `СМП_ТестОтветы<Банк><Вид>` і `СМП_ТестЭталоны<Банк><Вид>`; `<Банк>` -- `Приват`, `МоноФОП`, `МоноЮр`;
`<Вид>` -- `Синт` (синтетика, ознака в імені) або `Run1` (знеособлені обміни прогону). Для run1 береться лише те читання, що має
еталон, тож кількість записів дорівнює кількості еталонів у кожному наборі."""
import json
import os
from datetime import datetime

from . import common as C, etalon, readings, recording as R, synth

# Читання run1, виключені з наборів, бо конектор не відтворює їхніх запитів (`readings.replay_exclusion`): (банк, ід, причина).
EXCLUDED = []                      # (банк, ід, причина, вид набору)
RECORD_SET = 'smp-api-record-set'
ETALON_SET = 'smp-api-etalon-set'
KINDS = {'synthetic': 'Синт', 'run1': 'Run1', 'run3': 'Run3'}
BANKS = ('privat', 'mono-fop', 'mono-corp')       # банки 5а: 12 макетів; ПУМБ -- окремо (`PUMB`, `--anon-root-pumb`), щоб 12 і хеші 5а не змінились
PUMB = 'pumb'
# Правило «у кожного банку в наборі `run1` не менше однієї справжньої записи» однакове для всіх банків, ПУМБ теж (виняток «очікуємо run2» знято, коли набір ПУМБ наповнено читаннями run3 і run4).


def real_records_problem(bank, count):
    """Правило набору `run1`: справжніх записів не менше одного, без винятків. -> текст проблеми або ''."""
    if count >= 1:
        return ''
    return 'у наборі run1 банку %s немає жодного справжнього запису' % bank


def names(bank, kind):
    key = synth.BANK_KEYS[bank]
    return 'СМП_ТестОтветы%s%s' % (key, KINDS[kind]), 'СМП_ТестЭталоны%s%s' % (key, KINDS[kind])


def _dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


def synthetic_sets(bank):
    recs, ets = {}, {}
    for s in synth.every_scenario():
        if s.bank == bank:
            recs[s.sid] = json.loads(s.recording().pack())
            ets[s.sid] = etalon.build(s)[0]
    return recs, ets


def run1_sets(bank, anon_root, kind='run1', suffix='', reset=True):
    """Читання знеособленого запису, що мають еталон (`etalons/СМП_ТестЭталон<Банк><Ид>.json`). `suffix` додається до ідентифікатора читання (набір з кількох коренів: однакові `ЗапPumbA1…` у run3 і run4);
    `reset=False` -- не скидати `EXCLUDED` банку й виду (другий і далі корені того самого набору)."""
    if reset:
        EXCLUDED[:] = [x for x in EXCLUDED if not (x[0] == bank and x[3] == kind)]
    key = synth.BANK_KEYS[bank]
    prefix = 'СМП_ТестЭталон' + key
    recs, ets = {}, {}
    folder = os.path.join(anon_root, 'etalons')
    for fn in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not (fn.startswith(prefix) and fn.endswith('.json')):
            continue
        ident = fn[len(prefix):-len('.json')]
        with open(os.path.join(folder, fn), encoding='utf-8') as f:
            et = json.load(f)
        if et['bank'] != bank:
            continue
        rec = R.Recording.from_dir(os.path.join(anon_root, 'readings', bank, ident))
        reason = readings.measurement_exclusion(ident) or readings.replay_exclusion(bank, rec, et['parameters'])
        if reason:
            EXCLUDED.append((bank, ident + suffix, reason, kind))
            if reason.startswith('limit '):
                # справжні операції, сторінки від моделі банку на робочому limit (`ЗапStatementLimit500_Модель30`): продуктовий шлях без шва
                derived = readings.model_paged_corp(rec)
                p = C.Params(account=et['parameters']['НомерСчета'],
                             period_start=datetime.strptime(et['parameters']['НачалоПериода'], '%Y-%m-%dT%H:%M:%S'),
                             period_end=datetime.strptime(et['parameters']['КонецПериода'], '%Y-%m-%dT%H:%M:%S'), old_account_currency='980',
                             reading_moment=(datetime.strptime(et['parameters']['МоментЧтения'], '%Y-%m-%dT%H:%M:%S') if et['parameters'].get('МоментЧтения') else None))
                did = ident + suffix + '_Модель30'
                d, _, _ = etalon.build_from(derived, p, sid=did, title='справжні операції запису %s, сторінки від моделі банку (limit %d)' % (ident, C.CORP_WORKING_LIMIT),
                                            focus=et.get('reviewFocus', []), macro=et.get('recording', {}).get('макет', did), synthetic=False)
                ets[did] = d
                recs[did] = json.loads(derived.pack())
            continue
        if suffix:
            et = dict(et, id=ident + suffix)                       # ідентифікатор еталона = ключ у наборі (перевіряє тест `ЗаписиAPI_…`)
        ets[ident + suffix] = et
        recs[ident + suffix] = json.loads(rec.pack())
    return recs, ets


def run1_sets_multi(bank, anon_roots, kind='run1'):
    """Набір з кількох коренів знеособленого виходу (ПУМБ: run3 + run4). Один корінь -- як `run1_sets`; кілька -- ідентифікатори з суфіксом `_<ТекаКореня>` (`_Run3`, `_Run4`); збіг ключів -- помилка."""
    if len(anon_roots) == 1:
        return run1_sets(bank, anon_roots[0], kind)
    recs, ets = {}, {}
    for i, root in enumerate(anon_roots):
        suffix = '_' + os.path.basename(os.path.normpath(root)).capitalize()
        r, e = run1_sets(bank, root, kind, suffix=suffix, reset=(i == 0))
        dup = (set(r) & set(recs)) | (set(e) & set(ets))
        if dup:
            raise ValueError('збіг ідентифікаторів читань між коренями: %d' % len(dup))
        recs.update(r)
        ets.update(e)
    return recs, ets


def build(anon_root, out_dir, anon_root3=None, anon_root_pumb=None):
    """Пише 12 файлів у `out_dir`: `<Макет>.bin` (записи) і `<Макет>.txt` (еталони). -> [(макет, тип, кількість записів, байтів)]."""
    os.makedirs(out_dir, exist_ok=True)
    report = []
    plan = [(bank, kind) for bank in BANKS for kind in KINDS if not (kind == 'run3' and not anon_root3)]
    if anon_root_pumb:
        # ПУМБ: синтетика і знеособлені читання run3 + run4 (кілька коренів) у макетах вигляду `Run1` -- ім'я збережено, щоб не множити метадані: run1 ПУМБ читань не мав, а run1b і run2 запиту конектора не відтворюють
        plan += [(PUMB, 'synthetic'), (PUMB, 'run1')]
    for bank, kind in plan:
        if kind == 'synthetic':
            recs, ets = synthetic_sets(bank)
        elif bank == PUMB:
            recs, ets = run1_sets_multi(bank, list(anon_root_pumb), kind)
        else:
            recs, ets = run1_sets(bank, anon_root3 if kind == 'run3' else anon_root, kind)
        if bank == PUMB and kind == 'run1':
            problem = real_records_problem(bank, len(recs))
            if problem:
                raise ValueError(problem)
        if sorted(recs) != sorted(ets):
            raise ValueError('набори записів і еталонів не збігаються: %s %s' % (bank, kind))
        rname, ename = names(bank, kind)
        # версія набору — найвища з версій записів у ньому (v1, поки жоден запис не використовує v2)
        head = {'formatVersion': max([p['formatVersion'] for p in recs.values()] + [R.VERSION]), 'bank': bank, 'kind': kind}
        rtext = _dumps(dict(head, format=RECORD_SET, records=recs))
        etext = _dumps(dict(head, format=ETALON_SET, etalons=ets))
        with open(os.path.join(out_dir, rname + '.bin'), 'wb') as f:
            f.write(rtext.encode('utf-8'))
        with open(os.path.join(out_dir, ename + '.txt'), 'wb') as f:
            f.write(b'\xef\xbb\xbf' + etext.encode('utf-8'))
        report.append((rname, 'BinaryData', len(recs), len(rtext.encode('utf-8'))))
        report.append((ename, 'Text', len(ets), len(etext.encode('utf-8')) + 3))
    return report
