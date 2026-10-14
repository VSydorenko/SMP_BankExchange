# -*- coding: utf-8 -*-
"""Обхід контейнерів: CSV, фіксована ширина, DBF, XML, XLS. Один обхід обслуговує три потреби:
знеособлення (fn повертає вигадане значення), перелік полів (fn лише записує) і «скелет»
(blank=True: значення полів замінено на 0x01; усе інше — байт у байт). Скелети сирого й
знеособленого файлів мусять збігатися (перевірка б).

fn(role, text, key) -> новий текст. Ролі — у schema.py. Невідомі колонки / поля / атрибути — виняток.
"""
import re
import struct

from .schema import (KEEP, GAP, CSV_ROLES, DBF_ROLES, XML_ROLES, DAT_SLICES)
from .util import norm_name, split_csv_quoted

BLANK = '\x01'


class SchemaError(Exception):
    pass


def dec(b):
    return b.decode('cp1251', errors='surrogateescape')


def encode(s):
    """str -> cp1251; surrogateescape-символи відновлюються у вихідні байти."""
    return s.encode('cp1251', errors='surrogateescape')


def _split_lines(text):
    parts = re.split(r'(\r\n|\n|\r)', text)
    if parts and parts[-1] == '':
        parts = parts[:-1]
    if len(parts) % 2 == 1:
        parts.append('')
    return [(parts[i], parts[i + 1]) for i in range(0, len(parts), 2)]


# ------------------------------------------------------------------ CSV
def walk_csv(data, spec, fn, blank=False):
    roles_map = CSV_ROLES[spec['schema']]
    take = spec.get('take_rows')
    out, hdr, roles, nrows = [], None, None, 0
    for line, eol in _split_lines(dec(data)):
        if line.strip() == '':
            out.append(line + eol)
            continue
        fields = split_csv_quoted(line)
        if hdr is None:
            hdr = [norm_name(v) for _, v, _ in fields]
            roles = []
            for h in hdr:
                if h == '':
                    roles.append(None)
                elif h in roles_map:
                    roles.append(roles_map[h])
                else:
                    raise SchemaError('невідома колонка CSV (норм.): %r' % h[:40])
            out.append(line + eol)
            continue
        nrows += 1
        if take and nrows > take:
            continue
        new = []
        for i, (raw, val, quoted) in enumerate(fields):
            role = roles[i] if i < len(roles) else None
            if role is None:
                if val.strip() != '':
                    raise SchemaError('непорожнє значення в колонці без класифікації (№%d)' % i)
                new.append(raw)
                continue
            if role == KEEP:
                new.append(BLANK if blank else raw)
                if blank and quoted:
                    new[-1] = '"' + BLANK + '"'
                continue
            key = hdr[i]
            nv = BLANK if blank else fn(role, val, key)
            if blank:
                new.append('"' + BLANK + '"' if quoted else BLANK)
            elif nv == val:
                new.append(raw)
            elif quoted:
                new.append('"' + nv.replace('"', '""') + '"')
            else:
                if ';' in nv or '"' in nv:
                    raise SchemaError('значення без лапок містить службовий символ')
                new.append(nv)
        out.append(';'.join(new) + eol)
    return encode(''.join(out))


def fields_csv(data, spec):
    """-> [(роль, значення, ключ)] для всіх класифікованих полів файлу (без обрізання take_rows)."""
    rec = []
    walk_csv(data, spec, lambda r, t, k: (rec.append((r, t, k)), t)[1])
    # KEEP-поля теж потрібні (їхні лексеми — «збережені»); збираємо окремо
    keep = []
    roles_map = CSV_ROLES[spec['schema']]
    hdr = None
    for line, eol in _split_lines(dec(data)):
        if line.strip() == '':
            continue
        fs = split_csv_quoted(line)
        if hdr is None:
            hdr = [norm_name(v) for _, v, _ in fs]
            continue
        for i, (raw, val, q) in enumerate(fs):
            if i < len(hdr) and hdr[i] in roles_map and roles_map[hdr[i]] == KEEP:
                keep.append((KEEP, val, hdr[i]))
    return rec, keep


def structure_csv(data, spec):
    """Слова структури: заголовок."""
    for line, eol in _split_lines(dec(data)):
        if line.strip():
            return [v for _, v, _ in split_csv_quoted(line)]
    return []


# ------------------------------------------------------------------ фіксована ширина
def _justify(raw, newtext, width):
    s = newtext.strip(' ')
    if len(s) > width:
        s = s[:width]
    lead = len(raw) - len(raw.lstrip(' '))
    trail = len(raw) - len(raw.rstrip(' '))
    if lead > 0 and trail == 0:
        return s.rjust(width)
    return (' ' * 0 + s).ljust(width)


def walk_lines(data, spec, fn, blank=False):
    lay = DAT_SLICES[spec['schema']]
    width, slices = lay['width'], sorted(lay['slices'], key=lambda x: x[1])
    take = spec.get('take_rows')
    out, n = [], 0
    for line, eol in _split_lines(dec(data)):
        if line.strip() == '':
            out.append(line + eol)
            continue
        n += 1
        if take and n > take:
            continue
        if len(line) != width:
            raise SchemaError('довжина рядка %d, очікувалось %d' % (len(line), width))
        pos, pieces = 0, []

        def gap(a, b):
            seg = line[a:b]
            if seg == '':
                return ''
            if blank:
                return BLANK * len(seg) if seg.strip(' 0') else seg
            if seg.strip(' 0') == '':
                return seg
            return fn(GAP, seg, 'gap')[:len(seg)].ljust(len(seg))
        for name, a, b, role in slices:
            pieces.append(gap(pos, a))
            seg = line[a:b]
            if role == KEEP or seg.strip() == '':
                pieces.append(BLANK * len(seg) if (blank and role == KEEP) else seg)
            elif blank:
                pieces.append(BLANK * len(seg))
            else:
                nv = fn(role, seg, name)
                pieces.append(seg if nv == seg else _justify(seg, nv, b - a))
            pos = b
        pieces.append(gap(pos, width))
        out.append(''.join(pieces) + eol)
    return encode(''.join(out))


def fields_lines(data, spec):
    lay = DAT_SLICES[spec['schema']]
    rec, keep = [], []
    for line, eol in _split_lines(dec(data)):
        if line.strip() == '':
            continue
        pos = 0
        for name, a, b, role in sorted(lay['slices'], key=lambda x: x[1]):
            if a > pos:
                seg = line[pos:a]
                if seg.strip(' 0'):
                    rec.append((GAP, seg, 'gap'))
            (keep if role == KEEP else rec).append((role, line[a:b], name))
            pos = b
        if pos < lay['width']:
            seg = line[pos:]
            if seg.strip(' 0'):
                rec.append((GAP, seg, 'gap'))
    return rec, keep


# ------------------------------------------------------------------ DBF
def _dbf_parse(b):
    nrec = struct.unpack('<I', b[4:8])[0]
    hlen, rlen = struct.unpack('<HH', b[8:12])
    fields, pos, off = [], 32, 1
    while b[pos] != 0x0D:
        name = b[pos:pos + 11].split(b'\x00')[0].decode('ascii', 'replace')
        t = chr(b[pos + 11])
        ln = b[pos + 16]
        dc = b[pos + 17]
        if t == 'C':
            ln = ln + dc * 256
        fields.append((name, t, off, ln))
        off += ln
        pos += 32
    return fields, nrec, hlen, rlen


def walk_dbf(data, spec, fn, blank=False):
    roles_map = DBF_ROLES[spec['dbf_schema']]
    fields, nrec, hlen, rlen = _dbf_parse(data)
    for name, t, off, ln in fields:
        if name.lower() not in roles_map:
            raise SchemaError('невідоме поле DBF: %r' % name)
    take = spec.get('take_rows')
    keep_n = min(nrec, take) if take else nrec
    head = bytearray(data[:hlen])
    if take:
        struct.pack_into('<I', head, 4, keep_n)
    out = [bytes(head)]
    for i in range(keep_n):
        rec = bytearray(data[hlen + i * rlen: hlen + (i + 1) * rlen])
        for name, t, off, ln in fields:
            role = roles_map[name.lower()]
            raw = bytes(rec[off:off + ln])
            if role == KEEP or raw.strip(b' \x00') == b'':
                if blank and role == KEEP:
                    rec[off:off + ln] = BLANK.encode('latin-1') * ln
                continue
            if blank:
                rec[off:off + ln] = BLANK.encode('latin-1') * ln
                continue
            text = dec(raw)
            nv = fn(role, text, name.lower())
            if nv == text:
                continue
            pad = raw[-1:] if raw[-1:] in (b'\x00', b' ') else b' '
            nb = encode(nv.strip())
            if len(nb) > ln:
                nb = nb[:ln]
            lead = len(raw) - len(raw.lstrip(b' '))
            trail = len(raw) - len(raw.rstrip(b' \x00'))
            if t == 'N' or (lead > 0 and trail == 0):
                new = nb.rjust(ln, b' ')
            else:
                new = nb.ljust(ln, pad)
            rec[off:off + ln] = new
        out.append(bytes(rec))
    out.append(data[hlen + nrec * rlen:])
    return b''.join(out)


def fields_dbf(data, spec):
    roles_map = DBF_ROLES[spec['dbf_schema']]
    fields, nrec, hlen, rlen = _dbf_parse(data)
    rec, keep = [], []
    for i in range(nrec):
        r = data[hlen + i * rlen: hlen + (i + 1) * rlen]
        for name, t, off, ln in fields:
            role = roles_map[name.lower()]
            (keep if role == KEEP else rec).append((role, dec(r[off:off + ln]), name.lower()))
    return rec, keep


# ------------------------------------------------------------------ XML
_ENT = {'&quot;': '"', '&amp;': '&', '&lt;': '<', '&gt;': '>', '&apos;': "'"}


def xml_unescape(s):
    s = re.sub(r'&#x([0-9A-Fa-f]+);', lambda m: chr(int(m.group(1), 16)), s)
    s = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), s)
    return re.sub(r'&(quot|amp|lt|gt|apos);', lambda m: _ENT[m.group(0)], s)


def xml_escape(s, entities_for_ctl=False):
    s = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    if entities_for_ctl:
        s = s.replace('\n', '&#10;').replace('\r', '&#13;').replace('\t', '&#9;')
    return s


_TAG = re.compile(r'<([A-Za-z_][\w.:-]*)((?:\s+[A-Za-z_][\w.:-]*\s*=\s*"[^"]*")*)(\s*/?)>')
_ATTR = re.compile(r'(\s+)([A-Za-z_][\w.:-]*)(\s*=\s*)"([^"]*)"')


def walk_xml(data, spec, fn, blank=False):
    roles_map = XML_ROLES[spec['xml_schema']]
    rowtag = spec.get('row_tag', 'ROW')
    text = dec(data)

    def tag_sub(m):
        tag, attrs, close = m.group(1), m.group(2), m.group(3)
        if tag != rowtag:
            if attrs.strip():
                raise SchemaError('атрибути поза %s: <%s>' % (rowtag, tag))
            return m.group(0)

        def a_sub(am):
            sp, name, eq, raw = am.groups()
            if name not in roles_map:
                raise SchemaError('невідомий атрибут XML: %r' % name)
            role = roles_map[name]
            if blank:
                return '%s%s%s"%s"' % (sp, name, eq, BLANK)
            if role == KEEP or raw == '':
                return am.group(0)
            val = xml_unescape(raw)
            nv = fn(role, val, name)
            if nv == val:
                return am.group(0)
            return '%s%s%s"%s"' % (sp, name, eq, xml_escape(nv, '&#' in raw))
        return '<' + tag + _ATTR.sub(a_sub, attrs) + close + '>'
    out = _TAG.sub(tag_sub, text)
    # решта (поза тегами) — лише порожній простір, декларація, закриваючі теги
    rest = re.sub(r'<\?xml[^>]*\?>|</[\w.:-]+>|<[^<>]*>', '', _TAG.sub('', text))
    if rest.strip():
        raise SchemaError('текст поза атрибутами XML')
    return encode(out)


def fields_xml(data, spec):
    roles_map = XML_ROLES[spec['xml_schema']]
    rowtag = spec.get('row_tag', 'ROW')
    rec, keep = [], []
    for m in _TAG.finditer(dec(data)):
        if m.group(1) != rowtag:
            continue
        for am in _ATTR.finditer(m.group(2)):
            name, raw = am.group(2), xml_unescape(am.group(4))
            role = roles_map[name]
            (keep if role == KEEP else rec).append((role, raw, name))
    return rec, keep


# ------------------------------------------------------------------ диспетчер
def walk(spec, data, fn, blank=False):
    k = spec['container']
    if k == 'csv':
        return walk_csv(data, spec, fn, blank)
    if k == 'lines':
        return walk_lines(data, spec, fn, blank)
    if k == 'dbf':
        return walk_dbf(data, spec, fn, blank)
    if k == 'xml':
        return walk_xml(data, spec, fn, blank)
    if k == 'xls':
        from . import xls_walk
        return xls_walk.walk_xls(data, spec, fn, blank)
    raise ValueError(k)


def fields(spec, data):
    """-> (чутливі поля [(роль, текст, ключ)], збережені поля [...])."""
    k = spec['container']
    if k == 'csv':
        return fields_csv(data, spec)
    if k == 'lines':
        return fields_lines(data, spec)
    if k == 'dbf':
        return fields_dbf(data, spec)
    if k == 'xml':
        return fields_xml(data, spec)
    if k == 'xls':
        from . import xls_walk
        return xls_walk.fields_xls(data, spec)
    raise ValueError(k)


def structure_words(spec, data):
    """Слова структури (заголовки, імена полів / тегів / атрибутів): не чутливі за визначенням."""
    k = spec['container']
    if k == 'csv':
        return structure_csv(data, spec)
    if k == 'dbf':
        return [f[0] for f in _dbf_parse(data)[0]]
    if k == 'xml':
        return re.findall(r'[A-Za-z_][\w.:-]*', ' '.join(re.findall(r'</?([A-Za-z_][\w.:-]*)', dec(data))
                                                         + [m.group(2) for m in _ATTR.finditer(dec(data))]))
    if k == 'xls':
        from . import xls_walk
        return xls_walk.structure_xls(data, spec)
    return []
