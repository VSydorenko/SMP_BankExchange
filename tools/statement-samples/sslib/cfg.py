# -*- coding: utf-8 -*-
import glob
import json
import os
import zipfile

from .corpus import _excluded

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(path=None):
    with open(path or os.path.join(HERE, 'config.json'), encoding='utf-8') as f:
        return json.load(f)


def resolve(sample, raw_root):
    """-> байти сирого зразка. Файли `settings*` ніколи не відкриваються."""
    if 'zip' in sample:
        zp = os.path.join(raw_root, sample['zip'])
        if _excluded(zp):
            raise ValueError('виключений файл')
        with zipfile.ZipFile(zp) as z:
            return z.read(sample['member'])
    hits = sorted(p for p in glob.glob(os.path.join(raw_root, sample['src'])) if os.path.isfile(p) and not _excluded(p))
    if not hits:
        raise FileNotFoundError('маска не дала файлів: ' + sample['id'])
    return open(hits[sample.get('pick', 0)], 'rb').read()


def spec(sample):
    """Опис для containers.walk: усе потрібне обходу."""
    d = dict(sample)
    d.setdefault('take_rows', None)
    return d
