# -*- coding: utf-8 -*-
"""Мінімальний читач OLE2 / BIFF8 (XLS) без сторонніх бібліотек.

Потрібен у двох місцях: оракул читає XLS (Альфа-банк під розширенням .csv, ОТП .xls) і знеособлювач
правильно підмінює рядки в таблиці спільних рядків (SST) з тією самою довжиною. Нічого не пише, крім
`patch_bytes`, яка змінює байти у копії файлу в пам'яті.
"""
import struct
from datetime import date, timedelta

SIG = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
FREE, ENDCHAIN = 0xFFFFFFFF, 0xFFFFFFFE


class Ole:
    def __init__(self, data):
        self.d = data
        if data[:8] != SIG:
            raise ValueError('не OLE2')
        self.ss = 1 << struct.unpack('<H', data[0x1E:0x20])[0]
        self.mss = 1 << struct.unpack('<H', data[0x20:0x22])[0]
        nfat, first_dir, _, cutoff, first_mini, nmini, first_dif, ndif = struct.unpack('<IIIIIIII', data[0x2C:0x4C])
        self.cutoff = cutoff
        difat = list(struct.unpack('<109I', data[0x4C:0x4C + 436]))
        s = first_dif
        for _ in range(ndif):
            sec = self._sector(s)
            vals = struct.unpack('<%dI' % (self.ss // 4), sec)
            difat += list(vals[:-1])
            s = vals[-1]
        self.fat = []
        for fs in difat[:nfat]:
            if fs in (FREE, ENDCHAIN):
                continue
            self.fat += list(struct.unpack('<%dI' % (self.ss // 4), self._sector(fs)))
        # каталог
        self.entries = []
        dirdata = b''.join(self._sector(s) for s in self._chain(first_dir))
        for i in range(len(dirdata) // 128):
            e = dirdata[i * 128:(i + 1) * 128]
            nlen = struct.unpack('<H', e[64:66])[0]
            name = e[:max(nlen - 2, 0)].decode('utf-16le', 'replace')
            typ = e[66]
            start = struct.unpack('<I', e[116:120])[0]
            size = struct.unpack('<Q', e[120:128])[0]
            self.entries.append(dict(name=name, type=typ, start=start, size=size, idx=i))
        self.root = self.entries[0]
        self.minifat = []
        if first_mini not in (FREE, ENDCHAIN):
            md = b''.join(self._sector(s) for s in self._chain(first_mini))
            self.minifat = list(struct.unpack('<%dI' % (len(md) // 4), md))
        self.dir_start = first_dir

    def _off(self, sec):
        return (sec + 1) * self.ss

    def _sector(self, sec):
        o = self._off(sec)
        return self.d[o:o + self.ss]

    def _chain(self, start):
        out, s, seen = [], start, set()
        while s not in (FREE, ENDCHAIN) and s not in seen and s < len(self.fat):
            seen.add(s)
            out.append(s)
            s = self.fat[s]
        return out

    def find(self, name):
        for e in self.entries:
            if e['type'] in (2, 5) and e['name'] == name:
                return e
        return None

    def segments(self, entry):
        """Список (зміщення у файлі, довжина) для потоку в порядку потоку."""
        size = entry['size']
        segs = []
        if entry['type'] == 5 or size >= self.cutoff:
            left = size
            for s in self._chain(entry['start']):
                n = min(self.ss, left)
                segs.append((self._off(s), n))
                left -= n
                if left <= 0:
                    break
        else:
            root_segs = self.segments_of_chain(self.root['start'], self.root['size'])
            left = size
            s = entry['start']
            seen = set()
            while s not in (FREE, ENDCHAIN) and left > 0 and s not in seen:
                seen.add(s)
                n = min(self.mss, left)
                # мініпотік лежить у корінному потоці
                pos = s * self.mss
                acc = 0
                for off, ln in root_segs:
                    if pos < acc + ln:
                        segs.append((off + (pos - acc), n))
                        break
                    acc += ln
                left -= n
                s = self.minifat[s] if s < len(self.minifat) else ENDCHAIN
        return segs

    def segments_of_chain(self, start, size):
        segs, left = [], size
        for s in self._chain(start):
            n = min(self.ss, left)
            segs.append((self._off(s), n))
            left -= n
            if left <= 0:
                break
        return segs

    def read(self, entry):
        return b''.join(self.d[o:o + n] for o, n in self.segments(entry))

    def stream_to_file(self, entry):
        """-> функція: зміщення у потоці -> зміщення у файлі (для одного байта)."""
        segs = self.segments(entry)
        starts, acc = [], 0
        for o, n in segs:
            starts.append((acc, o, n))
            acc += n

        def f(pos):
            for a, o, n in starts:
                if a <= pos < a + n:
                    return o + (pos - a)
            raise IndexError(pos)
        return f


# ------------------------------------------------------------------ BIFF
def records(stream):
    """-> список (id, зміщення_даних, довжина)."""
    out, p, n = [], 0, len(stream)
    while p + 4 <= n:
        rid, ln = struct.unpack('<HH', stream[p:p + 4])
        out.append((rid, p + 4, ln))
        p += 4 + ln
    return out


def _rk(v):
    if v & 2:
        x = (v >> 2)
        if x & (1 << 29):
            x -= (1 << 30)
        x = float(x)
    else:
        x = struct.unpack('<d', struct.pack('<Q', (v & 0xFFFFFFFC) << 32))[0]
    if v & 1:
        x /= 100.0
    return x


class SstString:
    __slots__ = ('text', 'high', 'char_spans', 'rich', 'ext')


def parse_sst(stream, recs):
    """Таблиця спільних рядків. -> список SstString; char_spans — [(зміщення_у_потоці, кількість_байтів)]
    для байтів символів (для підміни на місці)."""
    # SST + CONTINUE-и: збираємо частини даних зі зміщеннями у потоці
    parts = []
    started = False
    for rid, off, ln in recs:
        if rid == 0x00FC:
            parts = [(off, ln)]
            started = True
        elif rid == 0x003C and started:
            parts.append((off, ln))
        elif started:
            break
    if not parts:
        return []
    # лінійний курсор по частинах
    st = {'pi': 0, 'po': 0}

    def left_in_part():
        return parts[st['pi']][1] - st['po']

    def read_n(n, skip_flag=False):
        """Прочитати n байтів, не перетинаючи межу частини; повернути (зміщення у потоці, байти)."""
        off = parts[st['pi']][0] + st['po']
        b = stream[off:off + n]
        st['po'] += n
        return off, b

    def advance_if_needed():
        while st['pi'] < len(parts) and left_in_part() <= 0:
            st['pi'] += 1
            st['po'] = 0

    _, hdr = read_n(8)
    total, uniq = struct.unpack('<II', hdr)
    res = []
    for _ in range(uniq):
        advance_if_needed()
        if st['pi'] >= len(parts):
            break
        _, b = read_n(3)
        cch, flags = struct.unpack('<HB', b)
        high = bool(flags & 1)
        ext = bool(flags & 4)
        rich = bool(flags & 8)
        crun = cext = 0
        if rich:
            advance_if_needed()
            _, b = read_n(2)
            crun = struct.unpack('<H', b)[0]
        if ext:
            advance_if_needed()
            _, b = read_n(4)
            cext = struct.unpack('<I', b)[0]
        chars, spans = [], []
        remaining = cch
        while remaining > 0:
            if left_in_part() <= 0:
                st['pi'] += 1
                st['po'] = 0
                # перший байт нової частини — прапорець кодування продовження
                _, fb = read_n(1)
                high = bool(fb[0] & 1)
            width = 2 if high else 1
            can = left_in_part() // width
            take = min(remaining, can)
            off, b = read_n(take * width)
            spans.append((off, take * width, high))
            chars.append(b.decode('utf-16le') if high else b.decode('latin-1'))
            remaining -= take
        # run-и форматування і розширення
        skip = crun * 4 + cext
        while skip > 0:
            advance_if_needed()
            if st['pi'] >= len(parts):
                break
            n = min(skip, left_in_part())
            read_n(n)
            skip -= n
        s = SstString()
        s.text = ''.join(chars)
        s.char_spans = spans
        s.high = any(h for _, _, h in spans)
        s.rich = rich
        s.ext = ext
        res.append(s)
    return res


BUILTIN_DATE_FMT = set(list(range(14, 23)) + [27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 45, 46, 47, 50, 51, 52, 53, 54, 55, 56, 57, 58])


def is_date_fmt_string(f):
    import re
    f = re.sub(r'"[^"]*"|\\.|\[[^\]]*\]|_.|\*.', '', f)
    return bool(re.search(r'[dmyhs]', f.lower()))


def read_xls(data):
    """Аркуш з індексом 0 -> dict(header, rows, nrows, strings, cells_sst)
    rows: список списків; числа як рядки (ціле без .0), дати як datetime.date.
    cells: {(r,c): ('sst', idx) | ('str', s) | ('num', v) | ('date', d)}"""
    ole = Ole(data)
    ent = ole.find('Workbook') or ole.find('Book')
    if ent is None:
        raise ValueError('немає потоку Workbook')
    st = ole.read(ent)
    recs = records(st)
    sst = parse_sst(st, recs)
    datemode = 0
    xf_fmt = []
    fmts = {}
    sheets = []
    for rid, off, ln in recs:
        d = st[off:off + ln]
        if rid == 0x0022:
            datemode = struct.unpack('<H', d[:2])[0]
        elif rid == 0x041E:
            idx = struct.unpack('<H', d[:2])[0]
            cch = struct.unpack('<H', d[2:4])[0]
            fl = d[4]
            fmts[idx] = d[5:5 + cch * 2].decode('utf-16le') if fl & 1 else d[5:5 + cch].decode('latin-1')
        elif rid == 0x00E0:
            xf_fmt.append(struct.unpack('<H', d[2:4])[0])
        elif rid == 0x0085:
            pos = struct.unpack('<I', d[:4])[0]
            sheets.append(pos)
    if not sheets:
        raise ValueError('немає аркушів')

    def isdate(xf):
        if xf >= len(xf_fmt):
            return False
        f = xf_fmt[xf]
        if f in fmts:
            return is_date_fmt_string(fmts[f])
        return f in BUILTIN_DATE_FMT

    epoch = date(1899, 12, 30) if datemode == 0 else date(1904, 1, 1)
    cells = {}
    cellpos = {}
    # записи першого аркуша: від BOF за зміщенням sheets[0] до EOF
    start = sheets[0]
    inside = False
    depth = 0
    pending_str = None
    for rid, off, ln in recs:
        hdr = off - 4
        if hdr == start:
            inside = True
            depth = 0
        if not inside:
            continue
        d = st[off:off + ln]
        if rid == 0x0809:
            depth += 1
        elif rid == 0x000A:
            depth -= 1
            if depth <= 0:
                break
        elif rid == 0x00FD and depth == 1:
            r, c, xf, idx = struct.unpack('<HHHI', d[:10])
            cells[(r, c)] = ('sst', idx)
        elif rid == 0x0204 and depth == 1:
            r, c, xf, cch = struct.unpack('<HHHH', d[:8])
            fl = d[8]
            s = d[9:9 + cch * 2].decode('utf-16le') if fl & 1 else d[9:9 + cch].decode('latin-1')
            cells[(r, c)] = ('str', s)
        elif rid == 0x0203 and depth == 1:
            r, c, xf = struct.unpack('<HHH', d[:6])
            v = struct.unpack('<d', d[6:14])[0]
            cellpos[(r, c)] = (rid, off + 6)
            cells[(r, c)] = ('date', epoch + timedelta(days=int(v))) if isdate(xf) else ('num', v)
        elif rid == 0x027E and depth == 1:
            r, c, xf, rk = struct.unpack('<HHHI', d[:10])
            cellpos[(r, c)] = (rid, off + 6)
            v = _rk(rk)
            cells[(r, c)] = ('date', epoch + timedelta(days=int(v))) if isdate(xf) else ('num', v)
        elif rid == 0x00BD and depth == 1:
            r, c1 = struct.unpack('<HH', d[:4])
            c2 = struct.unpack('<H', d[-2:])[0]
            p = 4
            for c in range(c1, c2 + 1):
                xf, rk = struct.unpack('<HI', d[p:p + 6])
                cellpos[(r, c)] = (rid, off + p + 2)
                p += 6
                v = _rk(rk)
                cells[(r, c)] = ('date', epoch + timedelta(days=int(v))) if isdate(xf) else ('num', v)
    if not cells:
        return dict(rows=[], header=[], nrows=0, sst=sst, cells=cells, cellpos=cellpos, ole=ole, entry=ent, stream=st)
    nr = max(r for r, _ in cells) + 1
    nc = max(c for _, c in cells) + 1
    rows = []
    for r in range(nr):
        row = []
        for c in range(nc):
            x = cells.get((r, c))
            if x is None:
                row.append('')
            elif x[0] == 'sst':
                row.append(sst[x[1]].text if x[1] < len(sst) else '')
            elif x[0] == 'str':
                row.append(x[1])
            elif x[0] == 'date':
                row.append(x[1])
            else:
                v = x[1]
                row.append(str(int(v)) if v == int(v) and abs(v) < 1e15 else repr(v))
        rows.append(row)
    return dict(header=rows[0], rows=rows[1:], nrows=nr, sst=sst, cells=cells, cellpos=cellpos, ole=ole, entry=ent, stream=st)


def xls_table(src):
    b = open(src, 'rb').read() if isinstance(src, str) else src
    x = read_xls(b)
    return x['header'], x['rows'], {'sheets': 1, 'nrows': x['nrows']}
