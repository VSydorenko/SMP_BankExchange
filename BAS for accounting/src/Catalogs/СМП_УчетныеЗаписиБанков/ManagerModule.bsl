
Процедура Загрузить(ФормаКлиентБанка, Эл) Экспорт
	
	//Если ОбщегоНазначения.ПодсистемаСуществует("СМП_simplyUNF.РаботаСБанками.ПриватБанк") Тогда
		Если Эл.Банк = Перечисления.СМП_ПоддерживаемыеИнтеграцииСБанками.ПриватБанк Тогда
			МодульИнтеграцииСБанкомПриватБанк = ОбщегоНазначения.ОбщийМодуль("СМП_РаботаСБанкамиПриватБанкAPIСервер");
			МодульИнтеграцииСБанкомПриватБанк.Прочитать(ФормаКлиентБанка, Эл.ИД, Эл.Токен);
		КонецЕсли;
	//КонецЕсли;
	
КонецПроцедуры

// Функция возвращает список имен «ключевых» реквизитов.
//
//Функция ПолучитьБлокируемыеРеквизитыОбъекта() Экспорт
//	
//	Результат = Новый Массив;
//	Результат.Добавить("Организация");
//	Результат.Добавить("БанковскийСчет");
//	Результат.Добавить("Банк");
//	Результат.Добавить("ПодключаемаяОбработка");
//	Результат.Добавить("ИД");
//	Результат.Добавить("Токен");
//	Результат.Добавить("ИспользоватьРегламентныеЗадания");
//	
//	Возврат Результат;
//	
//КонецФункции // ПолучитьБлокируемыеРеквизитыОбъекта()