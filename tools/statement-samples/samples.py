# -*- coding: utf-8 -*-
"""Інструмент зразків виписок: єдина точка входу. Запуск: python -P samples.py <команда> ...
Команди — у README.md. Усі команди перевірки повертають ненульовий код при порушенні."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass


def main(argv):
    from sslib import cli
    return cli.main(argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
