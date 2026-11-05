# -*- coding: utf-8 -*-
"""Наборы записей і еталонів для макетів (R15): форма, однакові ідентифікатори, запис відновлюється з набору без втрат.
Дані синтетичні; справжніх записів у тестах немає (run1 моделюється вигаданим «знеособленим виходом» з синтетики)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import common as C, etalon, readings, recording as R, sets, synth


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
    def test_zero_real_records_is_a_problem_for_every_bank(self):
        # правило «не менше однієї справжньої записи» однакове для всіх банків, ПУМБ теж (виняток очікування run2 знято)
        for bank in ('privat', 'mono-fop', 'mono-corp', 'pumb'):
            self.assertEqual(sets.real_records_problem(bank, 1), '')
            self.assertIn(bank, sets.real_records_problem(bank, 0))
        self.assertFalse(hasattr(sets, 'AWAITING_REAL_RECORDS'))

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


class ReplayExclusion(unittest.TestCase):
    """Читання run1 виключається з набору, якщо конектор не відтворить його запитів; контроль -- запис з direction і з чужим вікном balances."""

    def corp(self):
        s = next(x for x in synth.all_scenarios() if x.bank == 'mono-corp' and x.sid == 'СинтСтраницы')
        return s, s.recording()

    def test_synthetic_connector_shaped_record_is_kept(self):
        s, rec = self.corp()
        self.assertEqual(readings.replay_exclusion('mono-corp', rec, etalon.build(s)[0]['parameters']), '')

    def test_direction_excludes(self):
        s, rec = self.corp()
        st = next(e for e in rec.exchanges if R.statement_window(e))
        st['request']['query'] += '&direction=UP'
        self.assertIn('direction', readings.replay_exclusion('mono-corp', rec, etalon.build(s)[0]['parameters']))

    def test_foreign_balances_window_excludes(self):
        s, rec = self.corp()
        params = dict(etalon.build(s)[0]['parameters'], КонецПериода='2030-01-01T23:59:59')
        self.assertIn('balances', readings.replay_exclusion('mono-corp', rec, params))

    def test_record_truncated_on_a_full_page_excludes_but_a_stuck_page_does_not(self):
        s, rec = self.corp()
        rec.exchanges = [e for e in rec.exchanges if R.statement_window(e)][:1]      # обірвано на повній сторінці, яку можна продовжити
        self.assertIn('повною сторінкою', readings.replay_exclusion('mono-corp', rec, etalon.build(s)[0]['parameters']))
        stuck = next(x for x in synth.all_scenarios() if x.bank == 'mono-corp' and x.sid == 'СинтПолнаяНаНачале')
        self.assertEqual(readings.replay_exclusion('mono-corp', stuck.recording(), etalon.build(stuck)[0]['parameters']), '')

    def privat(self, sid='СинтСтраницыСлед'):
        s = next(x for x in synth.all_scenarios() if x.bank == 'privat' and x.sid == sid)
        return s, s.recording()

    def test_privat_connector_shaped_record_is_kept(self):
        s, rec = self.privat()
        self.assertEqual(readings.replay_exclusion('privat', rec, etalon.build(s)[0]['parameters']), '')

    def test_privat_requests_the_connector_does_not_make_are_excluded(self):
        # контроль: запис із запитом, якого конектор не зробить (немає limit; немає endDate; acc -- повний IBAN; чужі дні), виключається з причиною
        for drop, want in ((lambda q: q.replace('&limit=100', ''), 'limit'), (lambda q: q.replace('&endDate=15-10-2026', ''), 'endDate'),
                           (lambda q: q.replace('acc=', 'acc=UA00'), 'acc'), (lambda q: q.replace('startDate=15-10-2026', 'startDate=14-10-2026'), 'startDate')):
            s, rec = self.privat()
            tx = next(e for e in rec.exchanges if e['request']['path'] == C.PRIVAT_PATH)
            tx['request']['query'] = drop(tx['request']['query'])
            reason = readings.replay_exclusion('privat', rec, etalon.build(s)[0]['parameters'])
            self.assertIn(want, reason)

    def test_privat_reversed_and_future_periods_are_excluded(self):
        s, rec = self.privat()
        params = dict(etalon.build(s)[0]['parameters'])
        self.assertIn('навпаки', readings.replay_exclusion('privat', rec, dict(params, НачалоПериода='2026-10-16T00:00:00')))
        self.assertIn('майбутньому', readings.replay_exclusion('privat', rec, dict(params, НачалоПериода='2030-01-01T00:00:00', КонецПериода='2030-01-02T00:00:00')))

if __name__ == '__main__':
    unittest.main()
