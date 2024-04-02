
#Область ОписаниеПеременных

#Область ПеременныеФормы

&НаКлиенте
Перем ТекстовыйДокументВыписки;

#КонецОбласти

#КонецОбласти

#Область ОбработчикиСобытийФормы

&НаСервере
Процедура ПриСозданииНаСервере(Отказ, СтандартнаяОбработка)
	
	РасширениеРаботыСФайламиПодключено = Истина;
	
	ПутьКФайлу          = Параметры.ПутьКФайлу;
	АдресИсходныхДанных = Параметры.АдресИсходныхДанных;
	
	Если Параметры.Кодировка = "DOS" Тогда
		Кодировка = "cp866";        // КодировкаТекста.OEM;
	Иначе
		Кодировка = "windows-1251"; // КодировкаТекста.ANSI;
	КонецЕсли;
	
	ЭтоВебКлиент = ОбщегоНазначения.ЭтоВебКлиент();
	
	Элементы.Проверить.Видимость                       = ЭтоВебКлиент;
	Если ЭтоВебКлиент Тогда
		Элементы.ГруппаПроверка.ТекущаяСтраница = Элементы.ГруппаПроверкаПоКнопке;
	Иначе
		Элементы.ГруппаПроверка.ТекущаяСтраница = Элементы.ГруппаПроверкаВыполняется;
	КонецЕсли;
	
	Если Не ЭтоВебКлиент Тогда
		ТекстВыгрузкиСтрокой = ТекстВыгрузкиСтрокой(Параметры.АдресИсходныхДанных, Кодировка);
	КонецЕсли;
	
КонецПроцедуры

&НаКлиенте
Процедура ПриОткрытии(Отказ)
	
	#Если ВебКлиент Тогда
		ПодключитьОбработчикОжидания("Подключаемый_ПодключитьРасширениеРаботыСФайлами", 0.1, Истина);
	#Иначе
		ПодключитьОбработчикОжидания("Подключаемый_ПроверитьФайлВыгрузки", 2, Истина);
	#КонецЕсли
	
КонецПроцедуры

&НаКлиенте
Процедура ПередЗакрытием(Отказ, ЗавершениеРаботы, ТекстПредупреждения, СтандартнаяОбработка)
	
	Если Не ЗавершениеРаботы
		И ЗначениеЗаполнено(ПутьКФайлу) Тогда
		
		Отказ = Истина;
		УдалитьФайлПередЗакрытием();
		
	КонецЕсли;
	
КонецПроцедуры

#КонецОбласти

#Область ОбработчикиКомандФормы

&НаКлиенте
Процедура Проверить(Команда)
	
	Если РасширениеРаботыСФайламиПодключено Тогда
		ОписаниеОповещения = Новый ОписаниеОповещения("ПоказатьРезультатОднократно", ЭтотОбъект);
		ПроверитьФайлНаКлиенте(ОписаниеОповещения);
	Иначе
		ОповещениеПомещениеФайла = Новый ОписаниеОповещения("ПомещениеФайлаЗавершение", ЭтотОбъект);
		#Если ВебКлиент Тогда
			ДиалогВыбораФайлов = Новый ДиалогВыбораФайла(РежимДиалогаВыбораФайла.Открытие);
			ДиалогВыбораФайлов.Заголовок = "Выбор файла для помещения";
			ДиалогВыбораФайлов.МножественныйВыбор = Ложь;
			ДиалогВыбораФайлов.Фильтр = "Внешние обработки|*.epf|Внешние отчеты|*.erf";
			
			НачатьПомещениеФайла(ОповещениеПомещениеФайла, , ДиалогВыбораФайлов, Истина, ЭтотОбъект.УникальныйИдентификатор);
		#Иначе
			НачатьПомещениеФайла(ОповещениеПомещениеФайла, , "1c_to_kl.txt", Истина, ЭтотОбъект.УникальныйИдентификатор);
		#КонецЕсли
		
	КонецЕсли;
	
КонецПроцедуры

&НаКлиенте
Процедура Пропустить(Команда)
	
	Закрыть();
	
КонецПроцедуры

#КонецОбласти

#Область СлужебныеПроцедурыИФункции

&НаКлиенте
Процедура Подключаемый_ПодключитьРасширениеРаботыСФайлами() Экспорт
	
	ОписаниеОповещения = Новый ОписаниеОповещения("ПодключитьРасширениеРаботыСФайламиЗавершение", ЭтотОбъект);
	ФайловаяСистемаКлиент.ПодключитьРасширениеДляРаботыСФайлами(ОписаниеОповещения);
	
КонецПроцедуры

&НаКлиенте
Процедура ПодключитьРасширениеРаботыСФайламиЗавершение(ПодключеноРасширениеРаботыСФайлами, ДополнительныеПараметры) Экспорт
	
	РасширениеРаботыСФайламиПодключено = ПодключеноРасширениеРаботыСФайлами;
	
КонецПроцедуры

&НаКлиенте
Процедура ПомещениеФайлаЗавершение(Результат, АдресФайлаПомещенный, ВыбранноеИмяФайла, ДополнительныеПараметры) Экспорт
	
	Если Результат = Ложь ИЛИ АдресФайлаПомещенный = "" Тогда
		Возврат;
	КонецЕсли;
	
	Результат = СравнитьПолученныйФайл(АдресФайлаПомещенный);
	ПоказатьРезультатОднократно(Результат, Новый Структура);
	
КонецПроцедуры

&НаСервере
Функция СравнитьПолученныйФайл(АдресФайлаПомещенный)
	
	ТекстВыгрузкиФайлаСтрокой          = ТекстВыгрузкиСтрокой(АдресФайлаПомещенный, Кодировка);
	ТекстВыгрузкиИсходногоФайлаСтрокой = ТекстВыгрузкиСтрокой(АдресИсходныхДанных, Кодировка);
	
	Возврат ?(ТекстВыгрузкиФайлаСтрокой = ТекстВыгрузкиИсходногоФайлаСтрокой, "ПроверкаВыполненаУспешно", "ФайлИзменен");
	
КонецФункции

&НаСервереБезКонтекста
Функция ТекстВыгрузкиСтрокой(Знач АдресИсходныхДанных, Знач Кодировка)
	
	ДвоичныеДанныеИсходногоФайла = ПолучитьИзВременногоХранилища(АдресИсходныхДанных);
	ИмяВременногоФайла = ПолучитьИмяВременногоФайла();
	ДвоичныеДанныеИсходногоФайла.Записать(ИмяВременногоФайла);
	
#Если МобильныйКлиент Тогда
	
	ТекстСтрокой = "";
	
#Иначе
	
	ТекстовыйДокумент = Новый ТекстовыйДокумент;
	ТекстовыйДокумент.Прочитать(ИмяВременногоФайла, Кодировка);
	ТекстСтрокой = ТекстовыйДокумент.ПолучитьТекст();
	УдалитьФайлы(ИмяВременногоФайла);
	
#КонецЕсли 
	
	Возврат ТекстСтрокой;
	
КонецФункции

&НаКлиенте
Процедура ПоказатьРезультатПроверки(РезультатПроверки)
	
	Если РезультатПроверки = "ПроверкаВыполненаУспешно" Тогда
		// Проверка выполнена успешно
		
		Элементы.ГруппаПроверка.ТекущаяСтраница = Элементы.ГруппаПроверкаУспешна;
		
	ИначеЕсли РезультатПроверки = "ФайлИзменен" Тогда
		// Файл изменен
		
		Элементы.ГруппаПроверка.ТекущаяСтраница = Элементы.ГруппаФайлИзменен;
		
	ИначеЕсли РезультатПроверки = "ФайлУдален" Тогда
		// Файл удален
		
		Элементы.ГруппаПроверка.ТекущаяСтраница = Элементы.ГруппаФайлУдален;
		
	КонецЕсли;
	
КонецПроцедуры

&НаКлиенте
Процедура Подключаемый_ПроверитьФайлВыгрузки()
	
	ОписаниеОповещения = Новый ОписаниеОповещения("ЗапуститьПроверкуПовторно", ЭтотОбъект);
	ПроверитьФайлНаКлиенте(ОписаниеОповещения);
	
КонецПроцедуры

&НаКлиенте
Процедура ЗапуститьПроверкуПовторно(Результат, ДополнительныеПараметры) Экспорт
	
	Если Результат = "ПроверкаВыполненаУспешно" Тогда
		ПодключитьОбработчикОжидания("Подключаемый_ПроверитьФайлВыгрузки", 5, Истина);
	Иначе
		ПоказатьРезультатПроверки(Результат);
	КонецЕсли;
	
КонецПроцедуры

&НаКлиенте
Процедура ПоказатьРезультатОднократно(Результат, ДополнительныеПараметры) Экспорт
	
	ПоказатьРезультатПроверки(Результат);
	Если Результат = "ПроверкаВыполненаУспешно" Тогда
		Элементы.Проверить.Видимость = Ложь;
	ИначеЕсли Результат = "ФайлИзменен" Тогда
		Элементы.ДекорацияПроверкаУспешнаТекстСообщения7.Видимость = РасширениеРаботыСФайламиПодключено;
	КонецЕсли;
	
КонецПроцедуры

&НаКлиенте
Процедура ПроверитьФайлНаКлиенте(ОповещениеПослеПроверки)
	
	ДополнительныеПараметры = Новый Структура("ОповещениеПослеПроверки", ОповещениеПослеПроверки);
	ОписаниеОповещения = Новый ОписаниеОповещения("ПроверитьФайлНаКлиентеСозданиеФайла", ЭтотОбъект, ДополнительныеПараметры);
	
	Файл = Новый Файл();
	Файл.НачатьИнициализацию(ОписаниеОповещения, ПутьКФайлу);
	
КонецПроцедуры

&НаКлиенте
Процедура ПроверитьФайлНаКлиентеСозданиеФайла(Файл, ДополнительныеПараметры) Экспорт
	
	ОписаниеОповещения = Новый ОписаниеОповещения("ПроверитьФайлНаКлиентеПроверкаСуществования", ЭтотОбъект, ДополнительныеПараметры);
	Файл.НачатьПроверкуСуществования(ОписаниеОповещения);
	
КонецПроцедуры

&НаКлиенте
Процедура ПроверитьФайлНаКлиентеПроверкаСуществования(Существует, ДополнительныеПараметры) Экспорт

#Если НЕ МобильныйКлиент Тогда
	
	Если Существует Тогда
		
		ОписаниеОповещения = Новый ОписаниеОповещения("ПроверитьФайлНаКлиентеПослеЧтенияФайла", ЭтотОбъект, ДополнительныеПараметры);
		
		ТекстовыйДокументВыписки = Новый ТекстовыйДокумент;
		ТекстовыйДокументВыписки.НачатьЧтение(ОписаниеОповещения, ПутьКФайлу, Кодировка);
		
	Иначе
		
		ОписаниеОповещения = ДополнительныеПараметры.ОповещениеПослеПроверки;
		ВыполнитьОбработкуОповещения(ОписаниеОповещения, "ФайлУдален");
		
	КонецЕсли;
	
#КонецЕсли 
	
КонецПроцедуры

&НаКлиенте
Процедура ПроверитьФайлНаКлиентеПослеЧтенияФайла(ДополнительныеПараметры) Экспорт
	
	ТекстПроверяемогоФайла = ТекстовыйДокументВыписки.ПолучитьТекст();
	#Если ВебКлиент Тогда
		ТекстВыгрузкиИсходногоФайлаСтрокой = ТекстВыгрузкиСтрокой(АдресИсходныхДанных, Кодировка);
	#Иначе
		ТекстВыгрузкиИсходногоФайлаСтрокой = ТекстВыгрузкиСтрокой;
	#КонецЕсли
	Результат = ?(ТекстВыгрузкиИсходногоФайлаСтрокой = ТекстПроверяемогоФайла, "ПроверкаВыполненаУспешно", "ФайлИзменен");
	
	ТекстовыйДокументВыписки = Неопределено;
	
	ОписаниеОповещения = ДополнительныеПараметры.ОповещениеПослеПроверки;
	ВыполнитьОбработкуОповещения(ОписаниеОповещения, Результат);
	
КонецПроцедуры

&НаКлиенте
Процедура УдалитьФайлПередЗакрытием()
	
	ОписаниеОповещения = Новый ОписаниеОповещения("УдалитьФайлПередЗакрытиемЗавершение", ЭтотОбъект);
	
	НачатьУдалениеФайлов(ОписаниеОповещения, ПутьКФайлу);
	
КонецПроцедуры

&НаКлиенте
Процедура УдалитьФайлПередЗакрытиемЗавершение(ДополнительныеПараметры) Экспорт
	
	ПутьКФайлу = "";
	Закрыть();
	
КонецПроцедуры


#КонецОбласти
