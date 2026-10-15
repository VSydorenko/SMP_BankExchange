# -*- coding: utf-8 -*-
"""Мінімальний розбір JSON із позиціями значень у тексті. Потрібен знеособлювачу (Step 2): замінити лише значення
чутливих полів, лишивши решту тіла БАЙТ-У-БАЙТ (пробіли, порядок ключів, форма запису чисел, екранування), і порівняти
структуру двох тіл.

Вузол: `Node(kind, start, end, value, items)`.
* `kind` -- 'obj' | 'arr' | 'str' | 'num' | 'lit' (true / false / null);
* `value` -- для 'str' розкодований рядок, для 'num' текст числа, для 'lit' Python-значення;
* `items` -- для 'arr' список вузлів, для 'obj' список пар `(ключ, вузол значення)`.
Позиції -- індекси в тексті, з якого розібрано (`text[start:end]` -- рівно токен значення)."""
import json


class JsonSpanError(ValueError):
    """Текст не є JSON; повідомлення містить лише позицію, не вміст."""


class Node:
    __slots__ = ('kind', 'start', 'end', 'value', 'items')

    def __init__(self, kind, start, end, value=None, items=None):
        self.kind, self.start, self.end, self.value, self.items = kind, start, end, value, items

    def is_scalar(self):
        return self.kind in ('str', 'num', 'lit')


_WS = ' \t\r\n'
_NUM_CHARS = set('+-0123456789.eE')


def parse(text):
    n = len(text)
    pos = 0

    def ws(i):
        while i < n and text[i] in _WS:
            i += 1
        return i

    def fail(i):
        raise JsonSpanError('JSON: помилка на позиції %d' % i)

    def string(i):
        if text[i] != '"':
            fail(i)
        j = i + 1
        while j < n:
            c = text[j]
            if c == '\\':
                j += 2
                continue
            if c == '"':
                try:
                    return Node('str', i, j + 1, json.loads(text[i:j + 1]))
                except ValueError:
                    fail(i)
            j += 1
        fail(i)

    def value(i):
        i = ws(i)
        if i >= n:
            fail(i)
        c = text[i]
        if c == '{':
            items, j = [], ws(i + 1)
            if j < n and text[j] == '}':
                return Node('obj', i, j + 1, None, items)
            while True:
                j = ws(j)
                k = string(j)
                j = ws(k.end)
                if j >= n or text[j] != ':':
                    fail(j)
                v = value(j + 1)
                items.append((k.value, v))
                j = ws(v.end)
                if j < n and text[j] == ',':
                    j += 1
                    continue
                if j < n and text[j] == '}':
                    return Node('obj', i, j + 1, None, items)
                fail(j)
        if c == '[':
            items, j = [], ws(i + 1)
            if j < n and text[j] == ']':
                return Node('arr', i, j + 1, None, items)
            while True:
                v = value(j)
                items.append(v)
                j = ws(v.end)
                if j < n and text[j] == ',':
                    j += 1
                    continue
                if j < n and text[j] == ']':
                    return Node('arr', i, j + 1, None, items)
                fail(j)
        if c == '"':
            return string(i)
        for word, val in (('true', True), ('false', False), ('null', None)):
            if text.startswith(word, i):
                return Node('lit', i, i + len(word), val)
        j = i
        while j < n and text[j] in _NUM_CHARS:
            j += 1
        if j == i:
            fail(i)
        tok = text[i:j]
        try:
            json.loads(tok)
        except ValueError:
            fail(i)
        return Node('num', i, j, tok)

    root = value(pos)
    if ws(root.end) != n:
        fail(root.end)
    return root


def replace_spans(text, edits):
    """edits: [(start, end, новий текст)] без перетинів -> новий текст."""
    out, last = [], 0
    for a, b, new in sorted(edits):
        if a < last:
            raise JsonSpanError('JSON: перетин замін')
        out.append(text[last:a])
        out.append(new)
        last = b
    out.append(text[last:])
    return ''.join(out)


def scalar_type(nd):
    """'str' | 'int' | 'float' | 'bool' | 'null' -- тип скаляра (число з крапкою чи експонентою -- float)."""
    if nd.kind == 'num':
        return 'float' if any(c in nd.value for c in '.eE') else 'int'
    if nd.kind == 'lit':
        return 'null' if nd.value is None else 'bool'
    return nd.kind


def skeleton(text, root):
    """Текст, у якому кожне скалярне значення замінено позначкою його виду (для порівняння форми двох тіл)."""
    edits = []

    def walk(nd):
        if nd.kind == 'obj':
            for _, v in nd.items:
                walk(v)
        elif nd.kind == 'arr':
            for v in nd.items:
                walk(v)
        else:
            edits.append((nd.start, nd.end, '\x00%s\x00' % scalar_type(nd)))
    walk(root)
    return replace_spans(text, edits)
