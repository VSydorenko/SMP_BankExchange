# -*- coding: utf-8 -*-
"""Записи відповідей API банків (ПриватБанк, monobank ФОП, monobank юросіб): оракул «стара обробка» /
«очікуване», синтетичні записи за документацією, еталон очікуваного конверта.

Це сусід `sslib` (інструмент зразків виписок) у тому самому каталозі: генератори кодів, мапа й сторож — ті самі
(`sslib.gen`, `sslib.guard`), других копій немає. Формат запису — `tools/api-recorder/FORMAT.md`."""
import os
import sys

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
