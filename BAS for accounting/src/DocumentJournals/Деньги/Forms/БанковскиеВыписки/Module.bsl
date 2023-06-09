
&НаКлиенте
&ИзменениеИКонтроль("ОткрытьФормуКлиентБанка")
Процедура СМП_ОткрытьФормуКлиентБанка(ПараметрыФормы = Неопределено) Экспорт
	
	Если ПараметрыФормы = Неопределено Тогда
		ПараметрыФормы = Новый Структура;
	КонецЕсли;
	
	ПараметрыФормы.Вставить("РежимПоУмолчанию", "ГруппаЗагрузка");
	Если ОтборОрганизацияИспользование И ЗначениеЗаполнено(ОтборОрганизация) Тогда
		ПараметрыФормы.Вставить("Организация", ОтборОрганизация);
	КонецЕсли;
	
	Если ОтборБанковскийСчетИспользование И ЗначениеЗаполнено(ОтборБанковскийСчет) Тогда
		ПараметрыФормы.Вставить("БанковскийСчет", ОтборБанковскийСчет);
	КонецЕсли;
	
	#Вставка
	Если Не ПараметрыФормы.Свойство("БанковскийСчет") Тогда
		текДанные = Элементы.Список.ТекущиеДанные;
		
		Если НЕ текДанные = Неопределено И ЗначениеЗаполнено(текДанные.БанковскийСчет) Тогда
			
			ПараметрыФормы.Вставить("БанковскийСчет", 	текДанные.БанковскийСчет);
			ПараметрыФормы.Вставить("Организация", 		текДанные.Организация);
		КонецЕсли;
		
	КонецЕсли;
	#КонецВставки
	
	ОткрытьФорму("Обработка.КлиентБанк.Форма.Форма", ПараметрыФормы, ЭтотОбъект);
	
КонецПроцедуры
