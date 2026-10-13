# -*- coding: utf-8 -*-
"""Еталон `СМП_ТестЭталон<…>`: текст з очікуваними операціями й очікуваною діагностикою знеособленого зразка.
Рахується Python-оракулом (режим «очікуване») з ЗНЕОСОБЛЕНОГО файлу — тим самим, що лежить у макеті
`СМП_ТестВыписка<…>`. Формат (версія 1) описано в README.md."""
from . import corpus, legacy, named
from .legacy import dev3_foreign_accounts

VERSION = 1
COLUMNS = ['ПорядковыйНомер', 'НомерСчета', 'Валюта', 'ДатаОперации', 'НомерДокумента', 'Сумма', 'Направление',
           'КонтрагентНаименование', 'КонтрагентНомерСчета', 'КонтрагентКод', 'КонтрагентМФО', 'НазначениеПлатежа']
DIAG_COLUMNS = ['Уровень', 'ПорядковыйНомер', 'Что', 'СырьеЗначение']


def esc(v):
    """Екранування значення: \\ -> \\\\, TAB -> \\t, LF -> \\n, CR -> \\r (рядок еталона = один фізичний рядок)."""
    return (str(v).replace('\\', '\\\\').replace('\t', '\\t').replace('\n', '\\n').replace('\r', '\\r'))


def _line(vals):
    return '\t'.join(esc(v) for v in vals)


def _amount(d):
    return '%.2f' % d


def rows_to_ops(rows):
    """Рядки емуляції -> (операції, діагностика)."""
    ops, diag = [], []
    for x in rows:
        if x.status == 'skip':
            continue
        if x.status != 'ok':
            if x.errors:
                for what, raw in x.errors:
                    diag.append(('Ошибка', x.n, what, raw))
            else:
                diag.append(('Ошибка', x.n, x.status, ''))
            continue
        r = x.r
        out = r['dir'] == 'out'
        own, cp = (r['payer'], r['recv']) if out else (r['recv'], r['payer'])
        cp_name = cp[3] if len(cp) > 3 else ''
        ops.append([x.n, own[0], r.get('cur') or '', r['date'].strftime('%Y-%m-%dT%H:%M:%S'), r['num'],
                    _amount(r['amount']), 'Списано' if out else 'Поступило', cp_name, cp[0], cp[1], cp[2],
                    r['purpose']])
    return ops, diag


def build(sample, anon, reject_reason=None):
    """-> текст еталона (рядки з \\n)."""
    out = ['# СМП_ТестЭталон', '# Версия формата: %d' % VERSION, '# Режим: ожидаемое (старая обработка + отступы 1-5)',
           '[Образец]', 'Идентификатор=' + sample['id'], 'Контейнер=' + sample['container']]
    if not sample.get('accepted'):
        ops_named = corpus.read_any_bytes(anon, sample['named'])[0]
        out += ['Принимается=Нет', 'Причина=' + (sample.get('note') or ''), 'ЗаписейИсточника=%d' % len(ops_named)]
        return '\n'.join(out) + '\n'
    rows = legacy.emulate(anon, sample['layout'], 'expected')
    ops, diag = rows_to_ops(rows)
    skipped = sum(1 for x in rows if x.status == 'skip')
    out += ['Принимается=Да', 'Схема=' + sample['layout'], 'ЗаписейИсточника=%d' % len(rows),
            'ПропущенныхСтрок=%d' % skipped]
    # власні рахунки в порядку першої появи; перший — рахунок читання (Параметры.НомерСчета)
    accs = []
    for o in ops:
        if o[1] not in accs:
            accs.append(o[1])
    cnt = {a: sum(1 for o in ops if o[1] == a) for a in accs}
    out.append('[Счета]')
    out += [_line([a, cnt[a]]) for a in accs]
    if accs:
        out.append('НомерСчетаЧтения=' + accs[0])
    out.append('[Операции]')
    out.append(_line(COLUMNS))
    out += [_line(o) for o in ops]
    out.append('[Диагностика]')
    out.append(_line(DIAG_COLUMNS))
    out += [_line(d) for d in diag]
    out.append('[ЧужиеСчета]')
    out.append(_line(['НомерСчета', 'НомераСтрок']))
    foreign = dev3_foreign_accounts([x for x in rows], {accs[0]} if accs else set())
    for a, ns in foreign.items():
        out.append(_line([a, ','.join(str(n) for n in ns)]))
    return '\n'.join(out) + '\n'
