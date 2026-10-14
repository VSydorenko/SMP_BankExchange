# -*- coding: utf-8 -*-
"""Тести сторожа (sslib/guard.py): сирі лексеми у файлі в кожній розкладці мусять знаходитись, а чистий
файл — ні. Дані синтетичні (вигадані тут)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sslib import guard

NUMS = {'7654321'}
NAMES = {'Вигадане'}


class ScanFilesEncodings(unittest.TestCase):
    def scan(self, data):
        d = tempfile.mkdtemp()
        p = os.path.join(d, 'x.bin')
        try:
            open(p, 'wb').write(data)
            return guard.scan_files([p], NUMS, NAMES)[p]
        finally:
            os.remove(p)
            os.rmdir(d)

    def test_clean_file_has_no_hits(self):
        self.assertEqual(self.scan('нейтральний текст 12 і слова'.encode('utf-8')), 0)
        self.assertEqual(self.scan('нейтральний текст 12'.encode('utf-16le')), 0)

    def test_known_string_found_in_each_encoding(self):
        for enc in ('utf-8', 'cp1251', 'cp866'):
            with self.subTest(enc=enc):
                self.assertGreater(self.scan(('рядок ' + 'Вигадане ' + '7654321 конец').encode(enc)), 0)

    def test_utf16le_found_at_both_alignments(self):
        body = ('x 7654321 y Вигадане z').encode('utf-16le')
        self.assertGreater(self.scan(body), 0)          # парний зсув
        self.assertGreater(self.scan(b'\x00' + body), 0)  # непарний зсув

    def test_control_can_fail_on_uncovered_encoding(self):
        # Контроль, що вміє падати: у розкладці, яку сторож не читає (UTF-32), збігу немає, тож нуль
        # збігів на чистих даних не пояснюється тим, що сторож «знаходить усе».
        self.assertEqual(self.scan('Вигадане 7654321'.encode('utf-32le')), 0)

    def test_old_encodings_would_have_missed(self):
        # Доказ потреби: лише UTF-8 і windows-1251 (старий набір) не бачать ні UTF-16LE, ні cp866.
        old = ('utf-8', 'cp1251')
        for enc, data in (('utf-16le', '7654321'.encode('utf-16le')), ('cp866', 'Вигадане'.encode('cp866'))):
            with self.subTest(enc=enc):
                self.assertEqual(sum(len(guard.scan_text(data.decode(e, errors='replace'), NUMS, NAMES)) for e in old), 0)
                self.assertGreater(self.scan(data), 0)


if __name__ == '__main__':
    unittest.main()
