# -*- coding: utf-8 -*-
"""Очікуване синтетичних записів D36 п. 11 (юросіб і ФОП) -- РУКАМИ, за формулами спеки й рішень архітектора, а не оракулом: оракул може їх
рахувати, але цей тест звіряє його результат із ручним очікуваним (розбіжність -- питання, а не підгонка).

Формули (E -- найраніша `time` повної сторінки, U -- поточна верхня межа `to`):
1. межа продовження = Мин(E + 1, U);
2. застрягання -- коли межа продовження = U, тобто E >= U - 1; клас «дія людини», читання неповне;
3. крок після застрягання = Мин(E, U - 1), строго менший за U; діагностика називає секунди U - 1 і U й кількість операцій сторінки;
4. неповними лишаються секунди між новою й поточною межею; операції повної сторінки лишаються в конверті;
5. аномалія -- `time` > `to` або `time` < `from` ФАКТИЧНИХ меж запиту (`time` = `to` НЕ аномалія): клас «повторити», ЦЯ сторінка в конверт не береться;
6. межі першого запиту (спеки 71b3771 і a90f7ea): `from` = `НачалоПериода` - 1 с (S - 1), `to` = Мин(`КонецПериода` + 1 с, момент читання); у записах
   момент читання пізніший за кінець періоду, тож `to` = E + 1. `НачалоПериода` і `КонецПериода` -- включні моменти: операції поза [S, E], але в
   межах запиту, відкидаються мовчки (їхні `ПорядковыйНомер` лишаються зайнятими); межа довіри не пізніша за момент читання.
`ПорядковыйНомер` -- позиція запису в порядку читання з одиниці (усі сторінки, зокрема повтори й відкинуті).
ФОП (задача 5): ті самі формули всередині кожного відрізка; відрізки -- у секундах Unix від найновішого, довжина разом з перекриттям <= 31 x 86400 с,
верхня межа старішого = `from` новішого + 1 с; поріг повної сторінки -- шов `page_limit` (30); між запитами виписки пауза 60 с (документальний ліміт
банку), після `client-info` паузи немає (run1, пункт 11); пауза за заголовком понад стелю 120 с -- «повторити» без очікування."""
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


def same_ops(got, ops):
    """Множина номерів (id випадкові) або точний словник `номер -> id`."""
    return got if isinstance(ops, dict) else set(got)


class ByHand(unittest.TestCase):
    def check(self, sid, *, ops, requests, cls, complete, trust, diags=(), pauses=None):
        s = scenario(sid)
        e = E.run(s.recording(), s.params)
        lo = S.to_unix(s.params.period_start) - 1                       # нижня межа запиту: НачалоПериода - 1 с
        got_ops = {o['ПорядковыйНомер']: o['ИдентификаторОперации'] for o in e.ops}
        self.assertEqual(same_ops(got_ops, ops), ops, sid)
        want_requests = ['/ext/v1/statement/%s/%d/%d' % (s.params.account, lo, to) for to in requests]
        got_requests = [r['Путь'] for r in e.requests if '/statement/' in r['Путь']]
        self.assertEqual(got_requests, want_requests, sid)
        self.assertEqual((e.failure_class, e.complete, e.trust), (cls, complete, trust), sid)
        if pauses is not None:
            self.assertEqual([x['Секунд'] for x in e.pauses], pauses, sid)
        key = lambda d: (d[1], d[0])                    # порядок рядків діагностики не специфікація: за номером і рівнем
        self.assertEqual(sorted([(d['Уровень'], d['ПорядковыйНомер'], d['Факты']) for d in e.diags], key=key), sorted(diags, key=key), sid)

    def test_d36_p11_expectations_written_by_hand(self):
        end_of_period = datetime(2026, 10, 15, 23, 59, 59)
        start_of_period = datetime(2026, 10, 14)
        end = S.to_unix(end_of_period)
        frm = S.to_unix(start_of_period)
        hi = end + 1                                                    # верхня межа першого запиту
        bank = 'monobank юросіб'
        warn = 'Предупреждение'
        base = S.utc(2026, 10, 14, 6)

        # секунда розпалась між сторінками: перша сторінка 28 звичайних + дві з п'яти операцій секунди; друга -- вона вся + 4 старіші
        ops = {k: SID('N', 29 - k) for k in range(1, 29)}
        ops.update({29: SID('S', 0), 30: SID('S', 1), 33: SID('S', 2), 34: SID('S', 3), 35: SID('S', 4)})
        ops.update({35 + i: SID('O', i) for i in range(1, 5)})
        self.check('СинтСекундаРаспалась', ops=ops, requests=[hi, base + 1], cls='', complete=True, trust=end_of_period)

        # повна сторінка в одній секунді S (початок періоду): E = S; межа продовження S + 1 < U = E + 1; друга така сама -> застряг (U = S + 1), крок
        # Мин(E, U - 1) = S лежить вище нижньої межі S - 1, тож є ще третій запит (to = S): порожній
        ops = {k: SID('S', k - 1) for k in range(1, 31)}
        self.check('СинтПолнаяНаНачале', ops=ops, requests=[hi, frm + 1, frm], cls='ДействиеЧеловека', complete=False,
                   trust=start_of_period, diags=[(warn, 0, {'Банк': bank, 'Вид': 'cursor-stuck', 'Секунда': local(frm), 'Секунда2': local(frm + 1),
                                                         'Количество': 30})])

        # застрягання посеред читання: три сторінки з перекриттям межової секунди, четверта вся в секунді S, п'ята (to = S) -- старіші
        ops = {k: SID('A', k) for k in range(1, 31)}
        ops.update({31 + i: SID('M', i) for i in range(1, 30)})
        ops.update({61 + i: SID('Z', i) for i in range(1, 30)})
        ops[120] = SID('Z', 30)
        ops.update({120 + i: SID('V', i) for i in range(1, 6)})
        self.check('СинтЗастряла', ops=ops, requests=[hi, base + 2020 + 1, base + 110 + 1, base + 1, base], cls='ДействиеЧеловека',
                   complete=False, trust=start_of_period,
                   diags=[(warn, 0, {'Банк': bank, 'Вид': 'cursor-stuck', 'Секунда': local(base), 'Секунда2': local(base + 1), 'Количество': 30})])

        # повна сторінка, усі 30 операцій на time = to запиту (E + 1, поза періодом -- відкинуто мовчки): E = U -> межа продовження = U (застряг),
        # крок Мин(E, U - 1) = E; старіші читаються (номери 31..33, бо 1..30 зайняті відкинутими)
        ops = {31: SID('U', 0), 32: SID('U', 1), 33: SID('U', 2)}
        self.check('СинтПолнаяНаTo', ops=ops, requests=[hi, end], cls='ДействиеЧеловека', complete=False, trust=start_of_period,
                   diags=[(warn, 0, {'Банк': bank, 'Вид': 'cursor-stuck', 'Секунда': local(end), 'Секунда2': local(end + 1), 'Количество': 30})])

        # аномалія: друга сторінка має time > to -- не береться; перша лишається; «повторити»
        ops = {k: SID('E', 30 - k) for k in range(1, 31)}
        self.check('СинтБанкИгнорируетTo', ops=ops, requests=[hi, base + 1], cls='Повторить', complete=False, trust=start_of_period,
                   diags=[(warn, 0, {'Банк': bank, 'Вид': 'out-of-bounds', 'Статус': 200, 'ОписаниеБанка': ''})])

        # повна сторінка без читаного time: курсора немає, хоча «є ще» -- «повторити», неповне; кожен рядок без часу -- Ошибка bad-date,
        # операцій немає (відповідь записана вручну як аномалія, поза виміряним)
        diags = [(warn, 0, {'Банк': bank, 'Вид': 'page-without-time', 'Статус': 200, 'ОписаниеБанка': ''})]
        diags += [('Ошибка', k, {'Ид': SID('X', k - 1)}) for k in range(1, 31)]
        self.check('СинтПолнаяБезВремени', ops={}, requests=[hi], cls='Повторить', complete=False, trust=start_of_period, diags=diags)

        # операції на time = to (E + 1) і time = from (S - 1) запиту -- НЕ аномалія (банк повернув їх у межах запиту), але поза періодом: відкинуто
        # мовчки (номери 1 і 3 зайняті), лишається лише операція всередині
        self.check('СинтОперацияНаTo', ops={2: SID('Q', 2)}, requests=[hi], cls='', complete=True, trust=end_of_period)

        # межі періоду (модель найгіршого випадку, обидві межі запиту включні): операції на E + 1 (1) і на S - 1 (5) відкинуто, на E (2), всередині
        # (3) і на S (4) лишаються
        self.check('СинтГраницыПериода', ops={2: SID('D', 2), 3: SID('D', 3), 4: SID('D', 4)}, requests=[hi], cls='', complete=True, trust=end_of_period)

        # пауза понад стелю: retry-after 3600 с > 120 с -- «повторити» без повтору й без сну, діагностика називає запитану паузу
        self.check('СинтЛимит429Потолок', ops={}, requests=[hi], cls='Повторить', complete=False, trust=start_of_period, pauses=[],
                   diags=[(warn, 0, {'Банк': bank, 'Вид': 'pause-over-ceiling', 'Статус': 429, 'ОписаниеБанка': 'Too many requests', 'Пауза': 3600})])

        # нерозібраний retry-after (HTTP-дата) -- пауза за замовчуванням 60 с, повтор вдається: два запити з однаковими межами
        self.check('СинтЛимит429Дата', ops={1, 2}, requests=[hi, hi], cls='', complete=True, trust=end_of_period, pauses=[60])


class ByHandFop(unittest.TestCase):
    """ФОП: очікуване записане руками (ідентифікатори `S.fid`; запити -- пари `(from, to)` у секундах Unix; паузи -- секунди по порядку)."""

    def check(self, sid, *, ops, requests, cls, complete, trust, pauses, diags=()):
        s = scenario(sid, 'mono-fop')
        e = E.run(s.recording(), s.params)
        got_ops = {o['ПорядковыйНомер']: o['ИдентификаторОперации'] for o in e.ops}
        self.assertEqual(same_ops(got_ops, ops), ops, sid)
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
        lo, hi = frm - 1, end + 1                                      # межі першого запиту: НачалоПериода - 1 с, КонецПериода + 1 с
        bank = 'monobank ФОП'
        warn = 'Предупреждение'
        base = S.utc(2026, 10, 14, 6)
        F = S.fid

        ops = {k: F('N', 29 - k) for k in range(1, 29)}
        ops.update({29: F('S', 0), 30: F('S', 1), 33: F('S', 2), 34: F('S', 3), 35: F('S', 4)})
        ops.update({35 + i: F('O', i) for i in range(1, 5)})
        self.check('СинтСекундаРаспалась', ops=ops, requests=[(lo, hi), (lo, base + 1)], cls='', complete=True, trust=end_of_period,
                   pauses=[60])

        # нижня межа S - 1: після застрягання (U = S + 1) крок S лежить вище неї -- ще один запит (to = S), порожній
        ops = {k: F('S', k - 1) for k in range(1, 31)}
        self.check('СинтПолнаяНаНачале', ops=ops, requests=[(lo, hi), (lo, frm + 1), (lo, frm)], cls='ДействиеЧеловека', complete=False,
                   trust=start_of_period, pauses=[60, 60],
                   diags=[(warn, 0, {'Банк': bank, 'Вид': 'cursor-stuck', 'Секунда': local(frm), 'Секунда2': local(frm + 1), 'Количество': 30})])

        ops = {k: F('A', k) for k in range(1, 31)}
        ops.update({31 + i: F('M', i) for i in range(1, 30)})
        ops.update({61 + i: F('Z', i) for i in range(1, 30)})
        ops[120] = F('Z', 30)
        ops.update({120 + i: F('V', i) for i in range(1, 6)})
        self.check('СинтЗастряла', ops=ops, requests=[(lo, hi), (lo, base + 2020 + 1), (lo, base + 110 + 1), (lo, base + 1), (lo, base)],
                   cls='ДействиеЧеловека', complete=False, trust=start_of_period, pauses=[60, 60, 60, 60],
                   diags=[(warn, 0, {'Банк': bank, 'Вид': 'cursor-stuck', 'Секунда': local(base), 'Секунда2': local(base + 1), 'Количество': 30})])

        # 30 операцій на time = to запиту (E + 1) -- поза періодом, відкинуто мовчки (номери 1..30); старіші 31..33
        ops = {31: F('U', 0), 32: F('U', 1), 33: F('U', 2)}
        self.check('СинтПолнаяНаTo', ops=ops, requests=[(lo, hi), (lo, end)], cls='ДействиеЧеловека', complete=False,
                   trust=start_of_period, pauses=[60],
                   diags=[(warn, 0, {'Банк': bank, 'Вид': 'cursor-stuck', 'Секунда': local(end), 'Секунда2': local(end + 1), 'Количество': 30})])

        ops = {k: F('E', 30 - k) for k in range(1, 31)}
        self.check('СинтБанкИгнорируетTo', ops=ops, requests=[(lo, hi), (lo, base + 1)], cls='Повторить', complete=False,
                   trust=start_of_period, pauses=[60],
                   diags=[(warn, 0, {'Банк': bank, 'Вид': 'out-of-bounds', 'Статус': 200, 'ОписаниеБанка': ''})])

        diags = [(warn, 0, {'Банк': bank, 'Вид': 'page-without-time', 'Статус': 200, 'ОписаниеБанка': ''})]
        diags += [('Ошибка', k, {'Ид': F('X', k - 1)}) for k in range(1, 31)]
        self.check('СинтПолнаяБезВремени', ops={}, requests=[(lo, hi)], cls='Повторить', complete=False, trust=start_of_period,
                   pauses=[], diags=diags)

        # операції на E + 1 (1) і S - 1 (3) -- межі запиту, поза періодом: відкинуто мовчки
        self.check('СинтОперацияНаTo', ops={2: F('Q', 2)}, requests=[(lo, hi)], cls='', complete=True,
                   trust=end_of_period, pauses=[])

        # кількість операцій рівно дорівнює порогу: друга сторінка (31-й запис) -- лише повтор межової операції K0, відкидається за id
        ops = {k: F('K', 30 - k) for k in range(1, 31)}
        self.check('СинтКратнаяСтраница', ops=ops, requests=[(lo, hi), (lo, base + 1)], cls='', complete=True, trust=end_of_period,
                   pauses=[60])

        # межі періоду (модель найгіршого випадку, обидві межі запиту включні): E + 1 (1) і S - 1 (5) відкинуто; E (2), всередині (3), S (4) лишаються
        self.check('СинтГраницыПериода', ops={2: F('D', 2), 3: F('D', 3), 4: F('D', 4)}, requests=[(lo, hi)], cls='', complete=True,
                   trust=end_of_period, pauses=[])

        # пауза понад стелю (retry-after 3600 с > 120 с): без повтору й без сну
        self.check('СинтЛимит429Потолок', ops={}, requests=[(lo, hi)], cls='Повторить', complete=False, trust=start_of_period, pauses=[],
                   diags=[(warn, 0, {'Банк': bank, 'Вид': 'pause-over-ceiling', 'Статус': 429, 'ОписаниеБанка': 'Too many requests', 'Пауза': 3600})])

        # нерозібраний retry-after (HTTP-дата): пауза за замовчуванням 60 с, повтор вдається
        self.check('СинтЛимит429Дата', ops={1, 2}, requests=[(lo, hi), (lo, hi)], cls='', complete=True, trust=end_of_period, pauses=[60])

    def test_fop_segments_and_pauses_by_hand(self):
        # період 05.09.2026 06:30 .. 15.10.2026 14:20:07 за Києвом (літо, UTC+3). Межі запиту: від S - 1 до E + 1 (момент читання пізніший).
        # Відрізки від найновішого, довжина разом з перекриттям <= 31 x 86400 с: [E + 1 - 31 доба, E + 1], далі [S - 1, from новішого + 1]
        start = S.utc(2026, 9, 5, 3, 30)
        end = S.utc(2026, 10, 15, 11, 20, 7)
        f0 = S.utc(2026, 9, 14, 11, 20, 7)                              # E - 31 доба
        self.assertEqual(end - f0, 31 * 86400)
        w0 = (f0 + 1, end + 1)                                          # найновіший відрізок: довжина рівно 31 x 86400
        w1 = (start - 1, f0 + 2)                                        # старіший: to = from новішого + 1 = f0 + 2
        self.assertEqual(w0[1] - w0[0], 31 * 86400)
        end_of_period = datetime(2026, 10, 15, 14, 20, 7)
        F = S.fid
        # старіший відрізок порожній; у новішому дві операції (за спаданням часу); пауза лише між двома запитами виписки
        s = scenario('СинтОкна', 'mono-fop')
        two = [o['ИдентификаторОперации'] for o in E.run(s.recording(), s.params).ops]
        self.assertEqual(len(two), 2)
        self.check('СинтОкна', ops={1: two[0], 2: two[1]}, requests=[w0, w1], cls='', complete=True, trust=end_of_period, pauses=[60])
        # у новішому відрізку дві сторінки: W31..W2, далі повтор W2, W1 і Y2 (20.09); у старішому Y1 (08.09)
        base = S.utc(2026, 10, 10, 8)
        ops = {k: F('W', 32 - k) for k in range(1, 31)}
        ops.update({32: F('W', 1), 33: F('Y', 2), 34: F('Y', 1)})
        self.check('СинтОкнаСтраницы', ops=ops, requests=[w0, (w0[0], base + 201), w1], cls='', complete=True, trust=end_of_period,
                   pauses=[60, 60])
        # операція на секунді from новішого відрізка (f0 + 1): від виключного from новіший її не повертає, старіший (to = f0 + 2) повертає -- рівно раз
        self.check('СинтГраницаОтрезков', ops={1: F('G', 1), 2: F('G', 2), 3: F('G', 3)}, requests=[w0, w1], cls='', complete=True,
                   trust=end_of_period, pauses=[60])


if __name__ == '__main__':
    unittest.main()
