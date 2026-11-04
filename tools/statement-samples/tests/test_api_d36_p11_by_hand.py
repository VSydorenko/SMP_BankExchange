# -*- coding: utf-8 -*-
"""Очікуване синтетичних записів D36 п. 11 (юросіб) -- РУКАМИ, за формулами спеки й рішень архітектора, а не оракулом: оракул може їх
рахувати, але цей тест звіряє його результат із ручним очікуваним (розбіжність -- питання, а не підгонка).

Формули (E -- найраніша `time` повної сторінки, U -- поточна верхня межа `to`):
1. межа продовження = Мин(E + 1, U);
2. застрягання -- коли межа продовження = U, тобто E >= U - 1; клас «дія людини», читання неповне;
3. крок після застрягання = Мин(E, U - 1), строго менший за U; діагностика називає секунди U - 1 і U й кількість операцій сторінки;
4. неповними лишаються секунди між новою й поточною межею; операції повної сторінки лишаються в конверті;
5. аномалія -- `time` > `to` або `time` < `from` (`time` = `to` НЕ аномалія): клас «повторити», ЦЯ сторінка в конверт не береться.
`ПорядковыйНомер` -- позиція запису в порядку читання з одиниці (усі сторінки, зокрема повтори)."""
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apilib import expected as E, kyiv, synth as S

L = 30                                    # робочий limit
SID = S.seqid


def scenario(sid):
    return next(s for s in S.all_scenarios() if s.bank == 'mono-corp' and s.sid == sid)


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
        self.assertEqual([(d['Уровень'], d['ПорядковыйНомер'], d['Факты']) for d in e.diags], list(diags), sid)

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

        # контроль: операції на time = to і time = from -- НЕ аномалія, звичайні дані, кожна рівно раз (за спаданням time)
        self.check('СинтОперацияНаTo', ops={1: SID('Q', 1), 2: SID('Q', 2), 3: SID('Q', 3)}, requests=[end], cls='', complete=True,
                   trust=end_of_period)


if __name__ == '__main__':
    unittest.main()
