# -*- coding: utf-8 -*-
"""Тести перевірки (а) на байтах поза полями для DBF і XLS (D22: «по всіх байтах»). Дані лише синтетичні.
Файли будуються тут: мінімальний dBase III і мінімальна книга OLE2/BIFF8 (SST + WRITEACCESS)."""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sslib import checks, containers, schema

CFG = dict(allowed_words=[], binary_structure_words=['Workbook', 'Root', 'Entry', 'Sheet'], verbatim_texts=[])


# ----------------------------------------------------------------- DBF
def build_dbf(tail=b'\x1a', flag=b' ', reserved=b'\x00' * 14, records=2):
    names = list(schema.DBF_ROLES['oschad'])
    spec = []
    for n in names:
        if n == 'summa':
            spec.append((n, 'N', 12, 2))
        elif n in ('dk',):
            spec.append((n, 'N', 1, 0))
        elif n == 'val':
            spec.append((n, 'N', 4, 0))
        elif n == 'dt':
            spec.append((n, 'D', 8, 0))
        else:
            spec.append((n, 'C', 20, 0))
    rlen = 1 + sum(s[2] for s in spec)
    hlen = 32 + 32 * len(spec) + 1
    head = struct.pack('<BBBBIHH', 3, 24, 1, 1, records, hlen, rlen) + b'\x00' * 20
    for n, t, ln, dc in spec:
        head += n.encode('ascii').ljust(11, b'\x00') + t.encode() + b'\x00' * 4 + bytes([ln, dc]) + reserved
    head += b'\x0d'
    body = b''
    for i in range(records):
        rec = flag
        for n, t, ln, dc in spec:
            if t == 'D':
                v = b'20240315'
            elif n == 'summa':
                v = b'123.45'.rjust(ln)
            elif n in ('dk', 'val'):
                v = b'1'.rjust(ln)
            else:
                v = b''.ljust(ln)
            rec += v
        body += rec
    return head + body + tail


DBF_SPEC = dict(container='dbf', dbf_schema='oschad', take_rows=None)


class DbfResidual(unittest.TestCase):
    def test_clean_file_has_no_residual(self):
        self.assertEqual(checks.residual_violations(DBF_SPEC, build_dbf(), CFG), 0)
        self.assertEqual(checks.residual_violations(DBF_SPEC, build_dbf(tail=b''), CFG), 0)

    def test_text_in_tail_is_caught(self):
        data = build_dbf(tail=b'\x1a' + 'Іваненко Петро'.encode('cp1251'))
        self.assertGreater(checks.residual_violations(DBF_SPEC, data, CFG), 0)

    def test_text_in_reserved_descriptor_bytes_is_caught(self):
        data = build_dbf(reserved=b'SecretValue123')
        # дані в зарезервованих байтах опису поля — це заголовок: слова від 4 літер поза структурою -> порушення
        self.assertGreater(checks.residual_violations(DBF_SPEC, data, CFG), 0)

    def test_bad_record_flag_is_caught(self):
        self.assertGreater(checks.residual_violations(DBF_SPEC, build_dbf(flag=b'X'), CFG), 0)
        self.assertEqual(checks.residual_violations(DBF_SPEC, build_dbf(flag=b'*'), CFG), 0)   # вилучений запис — норма


# ----------------------------------------------------------------- XLS
def rec(rid, data):
    return struct.pack('<HH', rid, len(data)) + data


def xl_str16(s):
    return struct.pack('<HB', len(s), 1) + s.encode('utf-16le')


def build_xls(username='Іваненко Петро'.ljust(40)):
    headers = ['Найменування контрагента', 'Сума']
    texts = headers + ['Тестова Назва']
    sst_data = struct.pack('<II', len(texts), len(texts)) + b''.join(xl_str16(t) for t in texts)
    bof = lambda t: rec(0x0809, struct.pack('<HHHHII', 0x0600, t, 0x0DBB, 0x07CC, 0, 6))
    wa = rec(0x005C, xl_str16(username))
    sst = rec(0x00FC, sst_data)
    eof = rec(0x000A, b'')

    def boundsheet(pos):
        return rec(0x0085, struct.pack('<IBB', pos, 0, 0) + struct.pack('<BB', 6, 0) + b'Sheet1')
    glob_len = len(bof(5)) + len(wa) + len(boundsheet(0)) + len(sst) + len(eof)
    glob = bof(5) + wa + boundsheet(glob_len) + sst + eof

    def label(r, c, idx):
        return rec(0x00FD, struct.pack('<HHHI', r, c, 0, idx))
    sheet = (bof(0x10) + label(0, 0, 0) + label(0, 1, 1) + label(1, 0, 2)
             + rec(0x0203, struct.pack('<HHH', 1, 1, 0) + struct.pack('<d', 123.45)) + eof)
    wb = (glob + sheet).ljust(4608, b'\x00')
    nsec = len(wb) // 512
    END, FREE, FATSECT = 0xFFFFFFFE, 0xFFFFFFFF, 0xFFFFFFFD

    def entry(name, typ, child, start, size):
        nm = name.encode('utf-16le')
        return (nm.ljust(64, b'\x00') + struct.pack('<HBB', len(nm) + 2, typ, 1) + struct.pack('<III', FREE, FREE, child)
                + b'\x00' * 16 + b'\x00' * 4 + b'\x00' * 16 + struct.pack('<IQ', start, size))
    dirsec = (entry('Root Entry', 5, 1, END, 0) + entry('Workbook', 2, FREE, 2, len(wb))
              + b'\x00' * 256).ljust(512, b'\x00')[:512]
    fat = [FATSECT, END] + [i + 3 for i in range(nsec - 1)] + [END]
    fat = (fat + [FREE] * 128)[:128]
    fatsec = struct.pack('<128I', *fat)
    header = (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'\x00' * 16 + struct.pack('<HHHHH', 0x3E, 3, 0xFFFE, 9, 6)
              + b'\x00' * 6 + struct.pack('<IIIIIIIII', 0, 1, 1, 0, 4096, END, 0, END, 0)
              + struct.pack('<109I', 0, *([FREE] * 108)))
    return header + fatsec + dirsec + wb


XLS_SPEC = dict(container='xls', schema='alfa', take_rows=None)


class XlsResidual(unittest.TestCase):
    def test_builder_is_readable(self):
        from sslib import biff
        x = biff.read_xls(build_xls())
        self.assertEqual(x['nrows'], 2)
        self.assertEqual([s.text for s in x['sst']][2], 'Тестова Назва')

    def test_username_is_scrubbed_by_walker_so_residual_is_clean(self):
        data = build_xls()
        out = containers.walk(XLS_SPEC, data, lambda r, t, k: t)
        self.assertEqual(checks.residual_violations(XLS_SPEC, out, CFG), 0)

    def test_text_in_write_access_is_caught_without_scrub(self):
        # файл, який пройшов повз знеособлювач: ім'я користувача в WRITEACCESS лишилось
        self.assertGreater(checks.residual_violations(XLS_SPEC, build_xls(), CFG), 0)

    def test_blank_username_passes(self):
        self.assertEqual(checks.residual_violations(XLS_SPEC, build_xls(username=' ' * 40), CFG), 0)


if __name__ == '__main__':
    unittest.main()
