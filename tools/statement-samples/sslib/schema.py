# -*- coding: utf-8 -*-
"""Ролі полів кожного формату. Роль — що робить знеособлювач зі значенням:

  KEEP      зберігається свідомо (сума, дата, час, валюта, напрям, номер документа, МФО банку, коди
            операцій, службові прапорці). Перевірка (а) виключає лексеми цих полів явно й рахує їх.
  CODE      ЄДРПОУ / ІПН: вигаданий з правильною контрольною сумою й тією ж довжиною.
  ACC       рахунок: IBAN (mod 97) або старий номер; зв'язок IBAN <-> старий номер зберігається.
  NAME      назва / ПІБ.
  BANKNAME  назва банку.
  PURPOSE   призначення платежу: фраза зі словника за категорією.
  SCRAMBLE  службовий ідентифікатор довільної форми: цифри -> цифри, літери -> літери, розділювачі лишаються.
  DOCTYPE   текстова назва виду документа (нейтральна заміна «вид документа N»).

Кожне поле кожного формату мусить бути класифіковане: невідоме ім'я колонки / поля / атрибута —
помилка знеособлювача, а не мовчазне збереження.
"""
from . import named
from .util import norm_name

KEEP, CODE, ACC, NAME, BANKNAME, PURPOSE, SCRAMBLE, DOCTYPE = (
    'KEEP', 'CODE', 'ACC', 'NAME', 'BANKNAME', 'PURPOSE', 'SCRAMBLE', 'DOCTYPE')

# канонічне поле (з таблиць синонімів оракула) -> роль
_IFOBS = dict(own_edrpou=CODE, own_mfo=KEEP, own_name=NAME, own_acc=ACC, currency=KEEP, op_date=KEEP,
              op_code=KEEP, cp_mfo=KEEP, cp_bank=BANKNAME, cp_acc=ACC, cp_edrpou=CODE, cp_name=NAME,
              doc_no=KEEP, doc_date=KEEP, debit=KEEP, credit=KEEP, purpose=PURPOSE, cover=KEEP)
_ALFA = dict(own_acc_old=ACC, own_acc=ACC, direction=KEEP, cp_acc_old=ACC, cp_acc=ACC, cp_mfo=KEEP,
             cp_name=NAME, cp_edrpou=CODE, purpose=PURPOSE, op_date=KEEP, doc_no=KEEP, amount=KEEP,
             currency=KEEP, op_time=KEEP, doc_date=KEEP, arch_date=KEEP, own_edrpou=CODE, own_name=NAME,
             own_mfo=KEEP)
_UKRGAZ = dict(op_date=KEEP, own_mfo=KEEP, own_acc_old=SCRAMBLE, own_edrpou=CODE, own_name=NAME, doc_no=KEEP,
               doc_date=KEEP, dk=KEEP, cp_mfo=KEEP, cp_acc_old=SCRAMBLE, cp_edrpou=CODE, cp_name=NAME,
               cur_alpha=KEEP, cur_tag=KEEP, amount=KEEP, amount_eq=KEEP, purpose=PURPOSE, in_rst=KEEP,
               out_rst=KEEP, db_sum=KEEP, cr_sum=KEEP, own_acc=ACC, cp_acc=ACC)
# колонки УкрГазу без синонімів в оракулі: числа й коди курсу/валюти
_UKRGAZ_EXTRA = {'CUR_RATE': KEEP, 'AC_CUR_TAG': KEEP, 'AccountCur': KEEP, 'IN_RST_EQ': KEEP, 'OUT_RST_EQ': KEEP,
                 'DB_SUM_EQ': KEEP, 'CR_SUM_EQ': KEEP, 'DAT_OST_OB': KEEP, 'SUM_PD_EQ': KEEP}


def _build(syn, roles, extra=None):
    out = {}
    for canon, names in syn.items():
        for n in names:
            out[norm_name(n)] = roles[canon]
    for n, r in (extra or {}).items():
        out[norm_name(n)] = r
    return out


CSV_ROLES = {
    'ifobs': _build(named.SYN_IFOBS, _IFOBS, {'Код': CODE, 'Плательщик': NAME}),
    'alfa': _build(named.SYN_ALFA, _ALFA),
    'ukrgaz': _build(named.SYN_UKRGAZ, _UKRGAZ, _UKRGAZ_EXTRA),
}
# Альфа ФОП читається як iFOBS-подібний CSV з російськомовним заголовком; його колонки покриті ifobs

DBF_ROLES = {
    'oschad': dict(ndoc=KEEP, dt=KEEP, mfocli=KEEP, okpocli=CODE, acccli=ACC, namecli=NAME, bankcli=BANKNAME,
                   mfocor=KEEP, acccor=ACC, okpocor=CODE, namecor=NAME, bankcor=BANKNAME, dk=KEEP, summa=KEEP,
                   nazn=PURPOSE, val=KEEP, uetr=SCRAMBLE),
    'otp': dict(n_doc=KEEP, mfo_db=KEEP, rr_db=ACC, iban_db=ACC, naim_d=NAME, okpo_db=CODE, mfo_cr=KEEP, rr_k=ACC,
                iban_k=ACC, naim_k=NAME, okpo_cr=CODE, sum=KEEP, sumeq=KEEP, prizn=PURPOSE, prizn2=PURPOSE,
                prizn_end=PURPOSE, dat=KEEP, dat_pr=KEEP, kod_val=KEEP, operat=KEEP, dat_gn=KEEP, dat_arc=KEEP,
                tim_pr=KEEP),
}

XML_ROLES = {
    'rowdata': dict(ARCDATE=KEEP, DOCUMENTNO=KEEP, ACCOUNTNO=ACC, IBAN=ACC, CURRENCYID=KEEP, BANKID=KEEP,
                    CORRBANKID=KEEP, CORRACCOUNTNO=ACC, CORRIBAN=ACC, OPERATIONID=KEEP, BANKDATE=KEEP,
                    CURRSYMBOLCODE=KEEP, DOCSUBTYPESNAME=DOCTYPE, PLATPURPOSE=PURPOSE, DOCUMENTDATE=KEEP,
                    CORRBANKNAME=BANKNAME, CORRIDENTIFYCODE=CODE, CORRCONTRAGENTSNAME=NAME, BANKNAME=BANKNAME,
                    IDENTIFYCODE=CODE, ACCDESCR=NAME, CONTRAGENTSNAME=NAME, ACCOUNTID=SCRAMBLE, BOOKEDDATE=KEEP,
                    DOCUMENTTYPEID=KEEP, DATAVERSION=SCRAMBLE, SUMMAEQ=KEEP, SUMMA=KEEP, AMOUNTEQ=KEEP,
                    KODPLATPURPOSE=KEEP, ACC_OPERATOR=SCRAMBLE, ACC_OPERATOR_FIO=NAME, COMMISSION=KEEP,
                    DOCRATE=KEEP, DOCUMENTBRANCHID=SCRAMBLE, PAYMENTID=SCRAMBLE, PAYMENTTYPEID=KEEP,
                    ADDITIONALREQUISITES=SCRAMBLE, CORRACCOUNTNO_SWIFT=SCRAMBLE,
                    CORRDESCRIPTION_SWIFT=SCRAMBLE, CORR_BIC=SCRAMBLE),
}

# ОТП, текст фіксованої ширини: (ім'я, початок, кінець, роль), 0-базові, кінець виключно (40-oracle.md, розд. 3.5)
DAT_SLICES = {
    'otp1191': dict(width=1191, slices=[
        ('mfo_db', 0, 9, KEEP), ('rr_db', 9, 28, ACC), ('iban_db', 28, 57, ACC), ('mfo_cr', 57, 66, KEEP),
        ('rr_k', 66, 85, ACC), ('iban_k', 85, 114, ACC), ('flag', 114, 115, KEEP), ('amount', 115, 131, KEEP),
        ('kind', 131, 133, KEEP), ('doc_no', 133, 168, KEEP), ('cur', 168, 171, KEEP), ('dat', 171, 177, KEEP),
        ('dat_pr', 177, 183, KEEP), ('name_d', 183, 323, NAME), ('name_k', 323, 463, NAME),
        ('purpose', 463, 883, PURPOSE), ('okpo_db', 948, 983, CODE), ('okpo_cr', 983, 1018, CODE),
        ('bank_id', 1018, 1027, SCRAMBLE), ('dat_end', 1185, 1191, KEEP)]),
    'otp660': dict(width=660, slices=[
        ('mfo_db', 0, 9, KEEP), ('rr_db', 9, 28, ACC), ('iban_db', 28, 57, ACC), ('mfo_cr', 57, 66, KEEP),
        ('rr_k', 66, 85, ACC), ('iban_k', 85, 114, ACC), ('flag', 114, 115, KEEP), ('amount', 115, 131, KEEP),
        ('kind', 131, 133, KEEP), ('doc_no', 133, 143, KEEP), ('cur', 143, 146, KEEP), ('dat', 146, 152, KEEP),
        ('dat_pr', 152, 158, KEEP), ('name_d', 158, 196, NAME), ('name_k', 196, 234, NAME),
        ('purpose', 234, 394, PURPOSE), ('okpo_db', 459, 473, CODE), ('okpo_cr', 473, 487, CODE),
        ('bank_id', 487, 496, SCRAMBLE), ('dat_end', 654, 660, KEEP)]),
}
GAP = 'GAP'     # байти фіксованої ширини поза зрізами: порожні / нулі лишаються, решта перемішується


def xls_roles():
    return CSV_ROLES['alfa']
