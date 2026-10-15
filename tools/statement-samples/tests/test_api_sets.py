# -*- coding: utf-8 -*-
"""Наборы записей і еталонів для макетів (R15): форма, однакові ідентифікатори, запис відновлюється з набору без втрат.
Дані синтетичні; справжніх записів у тестах немає (run1 моделюється вигаданим «знеособленим виходом» з синтетики)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import etalon, recording as R, sets, synth


def fake_anon_root(root):
    """Вигаданий вихід `etalons` + `readings` з двох синтетичних сценаріїв Привата (грають роль читань run1)."""
    picked = [s for s in synth.all_scenarios() if s.bank == 'privat'][:2]
    for s, ident in zip(picked, ('ЗапПервое', 'ЗапВторое')):
        d = etalon.build(s)[0]
        path = os.path.join(root, 'etalons', 'СМП_ТестЭталонПриват' + ident + '.json')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False)
        s.recording().to_dir(os.path.join(root, 'readings', 'privat', ident))
    return [i for i in ('ЗапПервое', 'ЗапВторое')]


class Sets(unittest.TestCase):
    def test_names_carry_the_synthetic_mark(self):
        for bank in sets.BANKS:
            a, e = sets.names(bank, 'synthetic')
            self.assertTrue(a.endswith('Синт') and e.endswith('Синт'))
            a, e = sets.names(bank, 'run1')
            self.assertTrue(a.endswith('Run1') and 'Синт' not in a + e)
            self.assertTrue(a.startswith('СМП_ТестОтветы') and e.startswith('СМП_ТестЭталоны'))

    def test_synthetic_sets_have_equal_ids_and_restore_the_recording(self):
        total = 0
        for bank in sets.BANKS:
            recs, ets = sets.synthetic_sets(bank)
            self.assertEqual(sorted(recs), sorted(ets))
            for ident, pack in recs.items():
                self.assertEqual(pack['format'], R.PACK_FORMAT)
                self.assertTrue(ident.startswith('Синт'))
                rec = R.Recording.unpack(json.dumps(pack, ensure_ascii=False))
                self.assertEqual(len(rec.exchanges), ets[ident]['recording']['обменов'])
                self.assertTrue(ets[ident]['synthetic'])
            total += len(recs)
        self.assertEqual(total, len(synth.all_scenarios()))

    def test_build_writes_twelve_files_in_the_documented_shape(self):
        with tempfile.TemporaryDirectory() as anon, tempfile.TemporaryDirectory() as out:
            idents = fake_anon_root(anon)
            # у банків без вигаданого виходу наборів run1 немає: build вимагає еталонів усіх банків -- довантажуємо порожні теки
            for bank in ('mono-fop', 'mono-corp'):
                os.makedirs(os.path.join(anon, 'readings', bank), exist_ok=True)
            report = sets.build(anon, out)
            self.assertEqual(len(report), 12)
            self.assertEqual(len(os.listdir(out)), 12)
            name, _ = sets.names('privat', 'run1')
            with open(os.path.join(out, name + '.bin'), 'rb') as f:
                raw = f.read()
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))                     # BinaryData: без BOM
            data = json.loads(raw.decode('utf-8'))
            self.assertEqual((data['format'], data['kind'], data['bank']), (sets.RECORD_SET, 'run1', 'privat'))
            self.assertEqual(sorted(data['records']), sorted(idents))
            _, ename = sets.names('privat', 'run1')
            with open(os.path.join(out, ename + '.txt'), 'rb') as f:
                raw = f.read()
            self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))                       # Text: UTF-8 з BOM, як наявні еталони
            et = json.loads(raw[3:].decode('utf-8'))
            self.assertEqual((et['format'], sorted(et['etalons'])), (sets.ETALON_SET, sorted(idents)))

    def test_mismatching_ids_are_an_error(self):
        with tempfile.TemporaryDirectory() as anon:
            fake_anon_root(anon)
            import shutil
            shutil.rmtree(os.path.join(anon, 'readings', 'privat', 'ЗапВторое'))
            with self.assertRaises(FileNotFoundError):
                sets.run1_sets('privat', anon)


if __name__ == '__main__':
    unittest.main()
