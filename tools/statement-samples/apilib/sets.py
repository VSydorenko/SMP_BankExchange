# -*- coding: utf-8 -*-
"""Наборы записей и еталонів для макетів тестового розширення (рішення R15: макети пакетами, а не по одному на запис).

Макетів 12 = 3 банки x {синтетика, run1} x {записи, еталони}. Запис усередині набору адресується ідентифікатором
(`СинтСтатусы`, `ЗапTxWorkLimit`), тож тест будь-якого з конекторів дістає його однією функцією-помічником
(`СМП_ТестЗаписиAPI` у тестовому розширенні).

Форми (JSON, UTF-8):
* набір записів (BinaryData, без BOM)::

    {"format": "smp-api-record-set", "formatVersion": 1|2, "bank": "privat|mono-fop|mono-corp", "kind": "synthetic|run1",
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
BANKS = ('privat', 'mono-fop', 'mono-corp')


def names(bank, kind):
    key = synth.BANK_KEYS[bank]
    return 'СМП_ТестОтветы%s%s' % (key, KINDS[kind]), 'СМП_ТестЭталоны%s%s' % (key, KINDS[kind])


def _dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


def synthetic_sets(bank):
    recs, ets = {}, {}
    for s in synth.all_scenarios():
        if s.bank == bank:
            recs[s.sid] = json.loads(s.recording().pack())
            ets[s.sid] = etalon.build(s)[0]
    return recs, ets


def run1_sets(bank, anon_root, kind='run1'):
    EXCLUDED[:] = [x for x in EXCLUDED if not (x[0] == bank and x[3] == kind)]
    """Читання знеособленого запису, що мають еталон (`etalons/СМП_ТестЭталон<Банк><Ид>.json`)."""
    key = synth.BANK_KEYS[bank]
    prefix = 'СМП_ТестЭталон' + key
    recs, ets = {}, {}
    folder = os.path.join(anon_root, 'etalons')
    for fn in sorted(os.listdir(folder)):
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
            EXCLUDED.append((bank, ident, reason, kind))
            if reason.startswith('limit '):
                # справжні операції, сторінки від моделі банку на робочому limit (`ЗапStatementLimit500_Модель30`): продуктовий шлях без шва
                derived = readings.model_paged_corp(rec)
                p = C.Params(account=et['parameters']['НомерСчета'],
                             period_start=datetime.strptime(et['parameters']['НачалоПериода'], '%Y-%m-%dT%H:%M:%S'),
                             period_end=datetime.strptime(et['parameters']['КонецПериода'], '%Y-%m-%dT%H:%M:%S'), old_account_currency='980',
                             reading_moment=(datetime.strptime(et['parameters']['МоментЧтения'], '%Y-%m-%dT%H:%M:%S') if et['parameters'].get('МоментЧтения') else None))
                did = ident + '_Модель30'
                d, _, _ = etalon.build_from(derived, p, sid=did, title='справжні операції запису %s, сторінки від моделі банку (limit %d)' % (ident, C.CORP_WORKING_LIMIT),
                                            focus=et.get('reviewFocus', []), macro=et.get('recording', {}).get('макет', did), synthetic=False)
                ets[did] = d
                recs[did] = json.loads(derived.pack())
            continue
        ets[ident] = et
        recs[ident] = json.loads(rec.pack())
    return recs, ets


def build(anon_root, out_dir, anon_root3=None):
    """Пише 12 файлів у `out_dir`: `<Макет>.bin` (записи) і `<Макет>.txt` (еталони). -> [(макет, тип, кількість записів, байтів)]."""
    os.makedirs(out_dir, exist_ok=True)
    report = []
    for bank in BANKS:
        for kind in KINDS:
            if kind == 'run3' and not anon_root3:
                continue
            recs, ets = synthetic_sets(bank) if kind == 'synthetic' else run1_sets(bank, anon_root3 if kind == 'run3' else anon_root, kind)
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
