# -*- coding: utf-8 -*-
"""Наборы записей и еталонів для макетів тестового розширення (рішення R15: макети пакетами, а не по одному на запис).

Макетів 12 = 3 банки x {синтетика, run1} x {записи, еталони}. Запис усередині набору адресується ідентифікатором
(`СинтСтатусы`, `ЗапTxWorkLimit`), тож тест будь-якого з конекторів дістає його однією функцією-помічником
(`СМП_ТестЗаписиAPI` у тестовому розширенні).

Форми (JSON, UTF-8):
* набір записів (BinaryData, без BOM)::

    {"format": "smp-api-record-set", "formatVersion": 1, "bank": "privat|mono-fop|mono-corp", "kind": "synthetic|run1",
     "records": {"<Ид>": <пакет запису: smp-api-recording-pack, див. recording.py>, ...}}

* набір еталонів (TextDocument, UTF-8 з BOM, як наявні макети еталонів)::

    {"format": "smp-api-etalon-set", "formatVersion": 1, "bank": ..., "kind": ..., "etalons": {"<Ид>": <еталон, etalon.py>, ...}}

Імена макетів: `СМП_ТестОтветы<Банк><Вид>` і `СМП_ТестЭталоны<Банк><Вид>`; `<Банк>` -- `Приват`, `МоноФОП`, `МоноЮр`;
`<Вид>` -- `Синт` (синтетика, ознака в імені) або `Run1` (знеособлені обміни прогону). Для run1 береться лише те читання, що має
еталон, тож кількість записів дорівнює кількості еталонів у кожному наборі."""
import json
import os

from . import etalon, recording as R, synth

RECORD_SET = 'smp-api-record-set'
ETALON_SET = 'smp-api-etalon-set'
KINDS = {'synthetic': 'Синт', 'run1': 'Run1'}
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


def run1_sets(bank, anon_root):
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
        ets[ident] = et
        recs[ident] = json.loads(R.Recording.from_dir(os.path.join(anon_root, 'readings', bank, ident)).pack())
    return recs, ets


def build(anon_root, out_dir):
    """Пише 12 файлів у `out_dir`: `<Макет>.bin` (записи) і `<Макет>.txt` (еталони). -> [(макет, тип, кількість записів, байтів)]."""
    os.makedirs(out_dir, exist_ok=True)
    report = []
    for bank in BANKS:
        for kind in KINDS:
            recs, ets = synthetic_sets(bank) if kind == 'synthetic' else run1_sets(bank, anon_root)
            if sorted(recs) != sorted(ets):
                raise ValueError('набори записів і еталонів не збігаються: %s %s' % (bank, kind))
            rname, ename = names(bank, kind)
            head = {'formatVersion': 1, 'bank': bank, 'kind': kind}
            rtext = _dumps(dict(head, format=RECORD_SET, records=recs))
            etext = _dumps(dict(head, format=ETALON_SET, etalons=ets))
            with open(os.path.join(out_dir, rname + '.bin'), 'wb') as f:
                f.write(rtext.encode('utf-8'))
            with open(os.path.join(out_dir, ename + '.txt'), 'wb') as f:
                f.write(b'\xef\xbb\xbf' + etext.encode('utf-8'))
            report.append((rname, 'BinaryData', len(recs), len(rtext.encode('utf-8'))))
            report.append((ename, 'Text', len(ets), len(etext.encode('utf-8')) + 3))
    return report
