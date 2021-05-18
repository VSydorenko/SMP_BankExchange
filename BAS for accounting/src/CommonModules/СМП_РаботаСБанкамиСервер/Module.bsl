Процедура ОбменСБанкамиAPI(КодНастройки) Экспорт
	Ссылка = Справочники.СМП_УчетныеЗаписиБанков.НайтиПоКоду(КодНастройки);
	Если ЗначениеЗаполнено(Ссылка) И НЕ Ссылка.ПометкаУдаления Тогда
		
		Попытка
			
			ОбменСБанком(Ссылка);
			
			//Если Результат.Успех Тогда
			//	Инфо = "Обмен с банком прошел успешно. " + Результат.Информация;
			//Иначе
			//	Инфо = "Обмен с банком не прошел.";
			//КонецЕсли;
			//Инфо = Формат(Результат.ДатаОбновления, "ДФ='dd.MM.yyyy HH:mm:ss'") + " " + Инфо;
			
			//Если ЗначениеЗаполнено(Результат.Ошибка) Тогда
			//	Инфо = Инфо + Символы.ПС + "При обмене с банком произошли следующие ошибки:" + Символы.ПС + Результат.Ошибка;
			//КонецЕсли;
			
			//Объект = Ссылка.ПолучитьОбъект();
			//Объект.Протокол = Инфо + Символы.ПС + Символы.ПС + Объект.Протокол; 
			//Объект.Записать();
			
		Исключение
			ЗаписьЖурналаРегистрации(Ссылка.Наименование,
			УровеньЖурналаРегистрации.Ошибка,,,
			ОписаниеОшибки());
		КонецПопытки;
		
	КонецЕсли;
	
	
КонецПроцедуры

Процедура ОбменСБанком(Ссылка) Экспорт
	
	Обработка = Обработки.КлиентБанк.Создать();
	Обработка.БанковскийСчет = Ссылка.БанковскийСчет;
	Обработка.Организация = Ссылка.Организация;
	Обработка.ГруппаДоступа = Ссылка.ГруппаДоступаДляНовыхКонтрагентов;
	Обработка.ПроводитьЗагружаемые = Истина;
	Обработка.КонПериода = ТекущаяДата();
	Обработка.НачПериода = ТекущаяДата() - 864000;
	Обработка.АвтоматическиПодставлятьДокументы = Истина;
	Обработка.СоздаватьКонтрагентов = ?(Ссылка.СоздаватьНенайденныеЭлементы, 2, 1);
	Если Ссылка.Банк = Перечисления.СМП_ПоддерживаемыеИнтеграцииСБанками.ПриватБанк Тогда
		СМП_РаботаСБанкамиПриватБанкAPIСервер.ВыполнитьРегламент(Обработка, Ссылка);
	КонецЕсли;
	
	ИмпортЗаголовок = Неопределено;
	ТаблицаРезультата = Неопределено;
	ТаблицаПомеченныхНаУдалениеКакДубль = Неопределено;
	Если Обработка.Загрузка.Количество() > 0 Тогда
		Обработка.Загрузить(ИмпортЗаголовок, ТаблицаРезультата, ТаблицаПомеченныхНаУдалениеКакДубль);
	КонецЕсли;
	
КонецПроцедуры