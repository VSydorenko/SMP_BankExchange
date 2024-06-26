
#Область СлужебныйПрограммныйИнтерфейс

// Запускает процес загрузки банковской выписки через API банка.
//
// Параметры:
//   ФормаЗагрузкиКлиентБанка - ФормаКлиентскогоПриложения - обработка КлиентБанк: ФормаЗагрузка.
//   УчетнаяЗаписьБанка - СправочникСсылка.СМП_УчетныеЗаписиБанков - учетная запись для которой выполняется загрузка данных.
//   ТаблицаТаблицДокументов - ТаблицаЗначений - таблица найденных документов.
//   ТаблицаКонтрагентов - ДеревоЗначений - список контрагентов.
//
Процедура ЗагрузитьВыпискуЧерезAPI(ФормаЗагрузкиКлиентБанка, УчетнаяЗаписьБанка, ТаблицаТаблицДокументов, ТаблицаКонтрагентов) Экспорт
	
	ДанныеУчетнойЗаписи = ОбщегоНазначения.ЗначенияРеквизитовОбъекта(УчетнаяЗаписьБанка, "Банк, ИД, Токен, Логин, Пароль", Истина);
	
	Если СМП_РаботаСБанкамиСервер.ФункционалБанкаПодключен(ДанныеУчетнойЗаписи.Банк, "ПриватБанк") Тогда
		
		МодульИнтеграцииСБанкомПриватБанк = ОбщегоНазначения.ОбщийМодуль("СМП_РаботаСБанкамиПриватБанкAPIСервер");
		МодульИнтеграцииСБанкомПриватБанк.Прочитать(
		ФормаЗагрузкиКлиентБанка, ДанныеУчетнойЗаписи.ИД, ДанныеУчетнойЗаписи.Токен, ТаблицаТаблицДокументов, ТаблицаКонтрагентов);
		
	ИначеЕсли СМП_РаботаСБанкамиСервер.ФункционалБанкаПодключен(ДанныеУчетнойЗаписи.Банк, "МОНОБанк") Тогда
		
		МодульИнтеграцииСБанкомМонобанк = ОбщегоНазначения.ОбщийМодуль("СМП_РаботаСБанкамиМонобанкAPIСервер");
		МодульИнтеграцииСБанкомМонобанк.ЗагрузитьДанныеПоВыписке(
		ФормаЗагрузкиКлиентБанка, УчетнаяЗаписьБанка, ДанныеУчетнойЗаписи.Токен, ТаблицаТаблицДокументов, ТаблицаКонтрагентов);
		
	ИначеЕсли СМП_РаботаСБанкамиСервер.ФункционалБанкаПодключен(ДанныеУчетнойЗаписи.Банк, "ПУМБ") Тогда
		
		МодульИнтеграцииСБанкомПУМБ = ОбщегоНазначения.ОбщийМодуль("СМП_РаботаСБанкамиПУМБAPIСервер");
		МодульИнтеграцииСБанкомПУМБ.Прочитать(
		ФормаЗагрузкиКлиентБанка, УчетнаяЗаписьБанка, ДанныеУчетнойЗаписи, ТаблицаТаблицДокументов, ТаблицаКонтрагентов);
		
	КонецЕсли;
		
КонецПроцедуры // ЗагрузитьВыпискуЧерезAPI

#КонецОбласти

#Область СлужебныеПроцедурыИФункции

// СтандартныеПодсистемы.ЗапретРедактированияРеквизитовОбъектов

// Функция возвращает список имен «ключевых» реквизитов.
//
Функция ПолучитьБлокируемыеРеквизитыОбъекта() Экспорт
	
	Результат = Новый Массив;
	Результат.Добавить("Организация");
	Результат.Добавить("БанковскийСчет");
	Результат.Добавить("Банк");
	Результат.Добавить("ПодключаемаяОбработка");
	Результат.Добавить("ИД");
	Результат.Добавить("Токен");
	Результат.Добавить("ИспользоватьРегламентныеЗадания");
	Результат.Добавить("АдресДляWebHook");
	
	Возврат Результат;
	
КонецФункции // ПолучитьБлокируемыеРеквизитыОбъекта()

// Конец СтандартныеПодсистемы.ЗапретРедактированияРеквизитовОбъектов

#КонецОбласти
