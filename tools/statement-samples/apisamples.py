# -*- coding: utf-8 -*-
"""Інструмент записів відповідей API банків: єдина точка входу. Запуск: python -P apisamples.py <команда> ...
Команди — у README.md (розділ «Записи відповідей API») і в `apilib/cli.py`. Сусід `samples.py` (зразки виписок):
генератори кодів, мапа й сторож — ті самі (`sslib`), других копій немає."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass


def main(argv):
    from apilib import cli
    return cli.main(argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
