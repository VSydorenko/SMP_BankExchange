# -*- coding: utf-8 -*-
"""Очікуване синтетичних записів D36 п. 11 (юросіб і ФОП) -- РУКАМИ, за формулами спеки й рішень архітектора, а не оракулом: оракул може їх
рахувати, але цей тест звіряє його результат із ручним очікуваним (розбіжність -- питання, а не підгонка).

Формули (E -- найраніша `time` повної сторінки, U -- поточна верхня межа `to`):
1. межа продовження = Мин(E + 1, U);
2. застрягання -- коли межа продовження = U, тобто E >= U - 1; клас «дія людини», читання неповне;
3. крок після застрягання = Мин(E, U - 1), строго менший за U; діагностика називає секунди U - 1 і U й кількість операцій сторінки;
4. неповними лишаються секунди між новою й поточною межею; операції повної сторінки лишаються в конверті;
5. аномалія -- `time` > `to` або `time` < `from` (`time` = `to` НЕ аномалія): клас «повторити», ЦЯ сторінка в конверт не береться.
`ПорядковыйНомер` -- позиція запису в порядку читання з одиниці (усі сторінки, зокрема повтори).
ФОП (задача 5): ті самі формули всередині кожного відрізка ≤ 31 доби; поріг повної сторінки -- шов `page_limit` (30); між запитами
виписки пауза 60 с (документальний ліміт банку), після `client-info` паузи немає (run1, пункт 11)."""
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import expected as E, kyiv, synth as S

L = 30                                    # робочий limit
SID = S.seqid


def scenario(sid, bank='mono-corp'):
    return next(s for s in S.all_scenarios() if s.bank == bank and s.sid == sid)


def local(sec):
    return kyiv.unix_to_local(sec).strftime('%d.%m.%Y %H:%M:%S')


class ByHand(unittest.TestCase):
    def check(self, sid, *, ops, requests, cls, complete, trust, diags=()):
        s = scenario(sid)
        e = E.run(s.recording(), s.params)
        frm = S.to_unix(s.params.period_start)
        got_ops = {o['ПорядковыйНомер']: o['ИдентификаторОперации'] for o in e.ops}
        self.assertEqual(got_ops, ops, sid)
        want_requests = ['/ext/v1/statement/%s/%d/%d' % (s.params.account, frm, to) for to in requests]
        got_requests = [r['Путь'] for r in e.requests if '/statement/' in r['Путь']]
        self.assertEqual(got_requests, want_requests, sid)
        self.assertEqual((e.failure_class, e.complete, e.trust), (cls, complete, trust), sid)
        key = lambda d: (d[1], d[0])                    # порядок рядків діагностики не специфікація: за номером і рівнем
        self.assertEqual(sorted([(d['Уровень'], d['ПорядковыйНомер'], d['Факты']) for d in e.diags], key=key), sorted(diags, key=key), sid)

    def test_d36_p11_expectations_written_by_hand(self):
        end_of_period = datetime(2026, 10, 15, 23, 59, 59)
        start_of_period = datetime(2026, 10, 14)
        end = S.to_unix(end_of_period)
        frm = S.to_unix(start_of_period)
        bank = 'monobank юросіб'
        warn = 'Предупреждение'
        base = S.utc(2026, 10, 14, 6)

        # секунда розпалась між сторінками: перша сторінка 28 звичайних + дві з п'яти операцій секунди; друга -- вона вся + 4 старіші
        ops = {k: SID('N', 29 - k) for k in range(1, 29)}
        ops.update({29: SID('S', 0), 30: SID('S', 1), 33: SID('S', 2), 34: SID('S', 3), 35: SID('S', 4)})
        ops.update({35 + i: SID('O', i) for i in range(1, 5)})
        self.check('СинтСекундаРаспалась', ops=ops, requests=[end, base + 1], cls='', complete=True, trust=end_of_period)

        # повна сторінка в одній секунді на початку відрізка: E = from; межа продовження T + 1; друга така сама -> застряг (U = T + 1)
        ops = {k: SID('S', k - 1) for k in range(1, 31)}
        self.check('СинтПолнаяНаНачале', ops=ops, requests=[end, frm + 1], cls='ДействиеЧеловека', complete=False,
                   trust=start_of_period, diags=[(warn, 0, {'Банк': bank, 'Вид': 'cursor-stuck', 'Секунда': local(frm), 'Секунда2': local(frm + 1),
                                                         'Количество': 30})])

        # застрягання посеред читання: три сторінки з перекриттям межової секунди, четверта вся в секунді S, п'ята (to = S) -- старіші
        ops = {k: SID('A', k) for k in range(1, 31)}
        ops.update({31 + i: SID('M', i) for i in range(1, 30)})
        ops.update({61 + i: SID('Z', i) for i in range(1, 30)})
        ops[120] = SID('Z', 30)
        ops.update({120 + i: SID('V', i) for i in range(1, 6)})
        self.check('СинтЗастряла', ops=ops, requests=[end, base + 2020 + 1, base + 110 + 1, base + 1, base], cls='ДействиеЧеловека',
                   complete=False, trust=start_of_period,
                   diags=[(warn, 0, {'Банк': bank, 'Вид': 'cursor-stuck', 'Секунда': local(base), 'Секунда2': local(base + 1), 'Количество': 30})])

        # повна сторінка, усі операції на time = to: E = U -> межа продовження = U (застряг), крок Мин(E, U - 1) = U - 1; старіші читаються
        ops = {k: SID('T', k - 1) for k in range(1, 31)}
        ops.update({31: SID('U', 0), 32: SID('U', 1), 33: SID('U', 2)})
        self.check('СинтПолнаяНаTo', ops=ops, requests=[end, end - 1], cls='ДействиеЧеловека', complete=False, trust=start_of_period,
                   diags=[(warn, 0, {'Банк': bank, 'Вид': 'cursor-stuck', 'Секунда': local(end - 1), 'Секунда2': local(end), 'Количество': 30})])

        # аномалія: друга сторінка має time > to -- не береться; перша лишається; «повторити»
        ops = {k: SID('E', 30 - k) for k in range(1, 31)}
        self.check('СинтБанкИгнорируетTo', ops=ops, requests=[end, base + 1], cls='Повторить', complete=False, trust=start_of_period,
                   diags=[(warn, 0, {'Банк': bank, 'Вид': 'out-of-bounds', 'Статус': 200, 'ОписаниеБанка': ''})])

        # повна сторінка без читаного time: курсора немає, хоча «є ще» -- «повторити», неповне; кожен рядок без часу -- Ошибка bad-date,
        # операцій немає (відповідь записана вручну як аномалія, поза виміряним)
        diags = [(warn, 0, {'Банк': bank, 'Вид': 'page-without-time', 'Статус': 200, 'ОписаниеБанка': ''})]
        diags += [('Ошибка', k, {'Ид': SID('X', k - 1)}) for k in range(1, 31)]
        self.check('СинтПолнаяБезВремени', ops={}, requests=[end], cls='Повторить', complete=False, trust=start_of_period, diags=diags)

        # контроль: операції на time = to і time = from -- НЕ аномалія, звичайні дані, кожна рівно раз (за спаданням time)
        self.check('СинтОперацияНаTo', ops={1: SID('Q', 1), 2: SID('Q', 2), 3: SID('Q', 3)}, requests=[end], cls='', complete=True,
                   trust=end_of_period)


class ByHandFop(unittest.TestCase):
    """ФОП: очікуване записане руками (ідентифікатори `S.fid`; запити -- пари `(from, to)` у секундах Unix; паузи -- секунди по порядку)."""

    def check(self, sid, *, ops, requests, cls, complete, trust, pauses, diags=()):
        s = scenario(sid, 'mono-fop')
        e = E.run(s.recording(), s.params)
        got_ops = {o['ПорядковыйНомер']: o['ИдентификаторОперации'] for o in e.ops}
        self.assertEqual(got_ops, ops, sid)
        got_requests = [tuple(int(x) for x in r['Путь'].split('/')[-2:]) for r in e.requests if '/statement/' in r['Путь']]
        self.assertEqual(got_requests, requests, sid)
        self.assertEqual((e.failure_class, e.complete, e.trust), (cls, complete, trust), sid)
        self.assertEqual([x['Секунд'] for x in e.pauses], pauses, sid)       # лише між запитами виписки; після client-info паузи немає
        key = lambda d: (d[1], d[0])
        self.assertEqual(sorted([(d['Уровень'], d['ПорядковыйНомер'], d['Факты']) for d in e.diags], key=key), sorted(diags, key=key), sid)

    def test_d36_p11_expectations_for_fop_written_by_hand(self):
        end_of_period = datetime(2026, 10, 15, 23, 59, 59)
        start_of_period = datetime(2026, 10, 14)
        end = S.to_unix(end_of_period)
        frm = S.to_unix(start_of_period)
        bank = 'monobank ФОП'
        warn = 'Предупреждение'
        base = S.utc(2026, 10, 14, 6)
        F = S.fid

        ops = {k: F('N', 29 - k) for k in range(1, 29)}
        ops.update({29: F('S', 0), 30: F('S', 1), 33: F('S', 2), 34: F('S', 3), 35: F('S', 4)})
        ops.update({35 + i: F('O', i) for i in range(1, 5)})
        self.check('СинтСекундаРаспалась', ops=ops, requests=[(frm, end), (frm, base + 1)], cls='', complete=True, trust=end_of_period,
                   pauses=[60])

        ops = {k: F('S', k - 1) for k in range(1, 31)}
        self.check('СинтПолнаяНаНачале', ops=ops, requests=[(frm, end), (frm, frm + 1)], cls='ДействиеЧеловека', complete=False,
                   trust=start_of_period, pauses=[60],
                   diags=[(warn, 0, {'Банк': bank, 'Вид': 'cursor-stuck', 'Секунда': local(frm), 'Секунда2': local(frm + 1), 'Количество': 30})])

        ops = {k: F('A', k) for k in range(1, 31)}
        ops.update({31 + i: F('M', i) for i in range(1, 30)})
        ops.update({61 + i: F('Z', i) for i in range(1, 30)})
        ops[120] = F('Z', 30)
        ops.update({120 + i: F('V', i) for i in range(1, 6)})
        self.check('СинтЗастряла', ops=ops, requests=[(frm, end), (frm, base + 2020 + 1), (frm, base + 110 + 1), (frm, base + 1), (frm, base)],
                   cls='ДействиеЧеловека', complete=False, trust=start_of_period, pauses=[60, 60, 60, 60],
                   diags=[(warn, 0, {'Банк': bank, 'Вид': 'cursor-stuck', 'Секунда': local(base), 'Секунда2': local(base + 1), 'Количество': 30})])

        ops = {k: F('T', k - 1) for k in range(1, 31)}
        ops.update({31: F('U', 0), 32: F('U', 1), 33: F('U', 2)})
        self.check('СинтПолнаяНаTo', ops=ops, requests=[(frm, end), (frm, end - 1)], cls='ДействиеЧеловека', complete=False,
                   trust=start_of_period, pauses=[60],
                   diags=[(warn, 0, {'Банк': bank, 'Вид': 'cursor-stuck', 'Секунда': local(end - 1), 'Секунда2': local(end), 'Количество': 30})])

        ops = {k: F('E', 30 - k) for k in range(1, 31)}
        self.check('СинтБанкИгнорируетTo', ops=ops, requests=[(frm, end), (frm, base + 1)], cls='Повторить', complete=False,
                   trust=start_of_period, pauses=[60],
                   diags=[(warn, 0, {'Банк': bank, 'Вид': 'out-of-bounds', 'Статус': 200, 'ОписаниеБанка': ''})])

        diags = [(warn, 0, {'Банк': bank, 'Вид': 'page-without-time', 'Статус': 200, 'ОписаниеБанка': ''})]
        diags += [('Ошибка', k, {'Ид': F('X', k - 1)}) for k in range(1, 31)]
        self.check('СинтПолнаяБезВремени', ops={}, requests=[(frm, end)], cls='Повторить', complete=False, trust=start_of_period,
                   pauses=[], diags=diags)

        self.check('СинтОперацияНаTo', ops={1: F('Q', 1), 2: F('Q', 2), 3: F('Q', 3)}, requests=[(frm, end)], cls='', complete=True,
                   trust=end_of_period, pauses=[])

        # кількість операцій рівно дорівнює порогу: друга сторінка (31-й запис) -- лише повтор межової операції K0, відкидається за id
        ops = {k: F('K', 30 - k) for k in range(1, 31)}
        self.check('СинтКратнаяСтраница', ops=ops, requests=[(frm, end), (frm, base + 1)], cls='', complete=True, trust=end_of_period,
                   pauses=[60])

    def test_fop_segments_and_pauses_by_hand(self):
        # період 05.09.2026 06:30 .. 15.10.2026 23:59:59 за Києвом (літо, UTC+3): перший відрізок рівно 31 доба, межа посеред доби
        start = S.utc(2026, 9, 5, 3, 30)
        boundary = start + 2678400
        end = S.to_unix(datetime(2026, 10, 15, 23, 59, 59))
        self.assertEqual(boundary, S.utc(2026, 10, 6, 3, 30))
        end_of_period = datetime(2026, 10, 15, 23, 59, 59)
        F = S.fid
        # порожній перший відрізок, у другому дві операції; пауза лише між двома запитами виписки (після client-info її немає)
        two = [o['ИдентификаторОперации'] for o in E.run(scenario('СинтОкна', 'mono-fop').recording(), scenario('СинтОкна', 'mono-fop').params).ops]
        self.assertEqual(len(two), 2)
        self.check('СинтОкна', ops={1: two[0], 2: two[1]}, requests=[(start, boundary), (boundary, end)], cls='', complete=True,
                   trust=end_of_period, pauses=[60])
        # два відрізки, у першому дві сторінки: W99 (за секунду до межі) і W30..W2, далі повтор W2 і W1; другий відрізок -- Y2 і Y1
        ops = {1: F('W', 99)}
        ops.update({k: F('W', 32 - k) for k in range(2, 31)})
        ops.update({32: F('W', 1), 33: F('Y', 2), 34: F('Y', 1)})
        w2 = S.utc(2026, 9, 10, 8) + 200
        self.check('СинтОкнаСтраницы', ops=ops, requests=[(start, boundary), (start, w2 + 1), (boundary, end)], cls='', complete=True,
                   trust=end_of_period, pauses=[60, 60])


if __name__ == '__main__':
    unittest.main()
