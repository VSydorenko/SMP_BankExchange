
&НаСервере
Процедура ПриСозданииНаСервере(Отказ, СтандартнаяОбработка)
	
	МенеджерЗаписи = РегистрыСведений.ИсторияРаботыСКлиентомБанка.СоздатьМенеджерЗаписи();
	
	МенеджерЗаписи.Период = Параметры.Период;
	МенеджерЗаписи.Организация = Параметры.Организация;
	МенеджерЗаписи.БанковскийСчет = Параметры.БанковскийСчет;
	МенеджерЗаписи.Прочитать();
	
	Если НЕ МенеджерЗаписи.Выбран() Тогда
		Отказ = Истина;
		Возврат;
	КонецЕсли;
	
	ТаблицаПротокола = МенеджерЗаписи.ПротоколЗагрузки.Получить();
	
КонецПроцедуры

&НаКлиенте
Процедура ТаблицаПротоколаОбработкаРасшифровки(Элемент, Расшифровка, СтандартнаяОбработка)
	СтандартнаяОбработка = Ложь;
	ПоказатьЗначение(,Расшифровка);
КонецПроцедуры
