
#Область ОбработчикиСобытийФормы

&НаСервере
Процедура ПриСозданииНаСервере(Отказ, СтандартнаяОбработка)
	
	Если Объект.Ссылка.Пустая() Тогда
		ЗаполнитьЗначенияСвойств(Объект, Параметры);
		НастроитьРасписаниеРегламентногоЗадания = НСтр("ru='Настроить расписание'; uk='Налаштувати розклад'")
	Иначе
		НастроитьРасписаниеРегламентногоЗадания = РасписаниеРеглЗадания(Объект.РасписаниеРегламентногоЗадания);
	КонецЕсли;
	
	УстановитьВидимостьЭлементов();
	
КонецПроцедуры

&НаСервере
Процедура ПослеЗаписиНаСервере(ТекущийОбъект, ПараметрыЗаписи)
	
	// Обработчик подсистемы запрета редактирования реквизитов объектов
	//ЗапретРедактированияРеквизитовОбъектов.ЗаблокироватьРеквизиты(ЭтотОбъект);
	// Конец СтандартныеПодсистемы.ЗапретРедактированияРеквизитовОбъектов
	
КонецПроцедуры

#КонецОбласти

#Область ОбработчикиСобытийЭлементовШапкиФормы

&НаКлиенте
Процедура БанкПриИзменении(Элемент)
	
	УстановитьВидимостьЭлементов();
	
КонецПроцедуры

&НаКлиенте
Процедура ПодключаемаяОбработкаПриИзменении(Элемент)
	
	ПодключаемаяОбработкаПриИзмененииНаСервере();
	
КонецПроцедуры

&НаКлиенте
Процедура ИспользоватьРегламентныеЗаданияПриИзменении(Элемент)
	
	Если Объект.ИспользоватьРегламентноеЗадание Тогда
		
		Диалог = Новый ДиалогРасписанияРегламентногоЗадания(РасписаниеРеглЗадания(Объект.РасписаниеРегламентногоЗадания));
		Оповещение = Новый ОписаниеОповещения("НастройкаРасписанияЗавершение", ЭтотОбъект);
		Диалог.Показать(Оповещение);
		
	Иначе
		
		Объект.РасписаниеРегламентногоЗадания = "";
		НастроитьРасписаниеРегламентногоЗадания = НСтр("ru='Настроить расписание'; uk='Налаштувати розклад'");
		
	КонецЕсли;
	
	УстановитьВидимостьЭлементов();
	
КонецПроцедуры

&НаКлиенте
Процедура НастроитьРасписаниеРегламентногоЗаданияНажатие(Элемент, СтандартнаяОбработка)
	
	СтандартнаяОбработка = Ложь;
	Диалог = Новый ДиалогРасписанияРегламентногоЗадания(РасписаниеРеглЗадания(Объект.РасписаниеРегламентногоЗадания));
	Оповещение = Новый ОписаниеОповещения("НастройкаРасписанияЗавершение", ЭтотОбъект);
	Диалог.Показать(Оповещение);
	
КонецПроцедуры

&НаКлиенте
Процедура ФайлВыгрузкиНачалоВыбора(Элемент, ДанныеВыбора, СтандартнаяОбработка)
	ВыборФайлаДляВыгрузки(Элемент, НСтр("ru='выгрузки';uk='вивантаження'"));
КонецПроцедуры

&НаКлиенте
Процедура ФайлЗагрузкиНачалоВыбора(Элемент, ДанныеВыбора, СтандартнаяОбработка)
	ВыборФайлаДляЗагрузки(Элемент, НСтр("ru='загрузки';uk='завантаження'"));
КонецПроцедуры

#КонецОбласти

#Область ОбработчикиКомандФормы

 &НаКлиенте
Процедура ВыполнитьОбмен(Команда)
	
	ДлительнаяОперация = НачатьВыполнениеНаСервереОбмена();
	ОповещениеОЗавершении = Новый ОписаниеОповещения("ОбработатьРезультат", ЭтотОбъект);
	ПараметрыОжидания = ДлительныеОперацииКлиент.ПараметрыОжидания(ЭтотОбъект);
	ДлительныеОперацииКлиент.ОжидатьЗавершение(ДлительнаяОперация, ОповещениеОЗавершении, ПараметрыОжидания);
	
КонецПроцедуры

&НаКлиенте
Процедура МоноУстановитьВебХук(Команда)
	
	Если Модифицированность Тогда
		ПоказатьПредупреждение(, 
		нСтр("ru='Сохраните изменения элемента справочника перед установкой webhook!'; uk='Збережіть зміни елемента довідника перед встановленням Webhook!'"),,
		нСтр("ru='Форма изменена!'; uk='Форма змінена!'"))
	ИначеЕсли ПустаяСтрока(Объект.Токен) Тогда
		ОбщегоНазначенияКлиент.СообщитьПользователю(нСтр("ru='Не заполнен токен для доступа!'; uk='Не заповнений токен для доступу!'"),,
		"Токен", "Объект");
		Возврат;
	ИначеЕсли ПустаяСтрока(Объект.АдресДляWebHook) Тогда
		ОбщегоНазначенияКлиент.СообщитьПользователю(нСтр("ru='Не заполнен адрес для WebHook.'; uk='Не заповнена адреса для WebHook.'"),,
		"АдресДляWebHook", "Объект");
		Возврат;
	ИначеЕсли НЕ ПроверитьАдресWebHookНаСервере(Объект.АдресДляWebHook) Тогда
		ОбщегоНазначенияКлиент.СообщитьПользователю(нСтр("ru='Адрес для WebHook заполнен некорректно.'; uk='Адреса для WebHook заповнена некоректно.'"),,
		"АдресДляWebHook", "Объект");
		Возврат;	
	Иначе
		Результат = УстановитьАдресWebHookНаСервере(Объект.Токен, Объект.АдресДляWebHook);
		Если Результат = Истина Тогда
			ПоказатьПредупреждение(, нСтр("ru='WebHook установлен успешно.'; uk='WebHook встановлений успішно.'"));
		Иначе
			ОбщегоНазначенияКлиент.СообщитьПользователю(
			СтрШаблон(нСтр("ru='Ошибка при установке Webhook - %1.'; uk='Помилка при встановленні Webhook - %1'"), Результат));
		Возврат;		
		КонецЕсли;
	КонецЕсли;
	
КонецПроцедуры

#КонецОбласти

#Область СлужебныеПроцедурыФункции

&НаСервере
Процедура УстановитьВидимостьЭлементов()
	
	ЭтоПриватБанкAPI = Объект.Банк = Перечисления.СМП_ПоддерживаемыеИнтеграцииСБанками.ПриватБанк;
	ЭтоМоноБанкAPI = Объект.Банк = Перечисления.СМП_ПоддерживаемыеИнтеграцииСБанками.МОНОБанк;
	ЭтоПумбБанкAPI = Объект.Банк = Перечисления.СМП_ПоддерживаемыеИнтеграцииСБанками.ПУМБ;
	ЭтоФайловаяВыписка = Объект.Банк = Перечисления.СМП_ПоддерживаемыеИнтеграцииСБанками.ПодключаемаяОбработка;
	
	Элементы.ФормаВыполнитьОбмен.Видимость = ЭтоПриватБанкAPI ИЛИ ЭтоПумбБанкAPI ИЛИ ЭтоМоноБанкAPI;
	Элементы.ПодключаемаяОбработка.Видимость = ЭтоФайловаяВыписка;
	Элементы.ДекорацияРаботаСБанкамиПриватБанкАРІ.Видимость = ЭтоПриватБанкAPI;
	Элементы.ДекорацияРаботаСБанкамиМОНОБанкАРІ.Видимость = ЭтоМоноБанкAPI;
	Элементы.ГруппаБанкПумб.Видимость = ЭтоПумбБанкAPI;
	Элементы.ГруппаБанкПриват.Видимость = ЭтоПриватБанкAPI; // Или ЭтоМоноБанкAPI;
	Элементы.ГруппаРегламентноеЗадание.Видимость = ЭтоПриватБанкAPI ИЛИ ЭтоПумбБанкAPI; // Или ЭтоМоноБанкAPI;
	Элементы.НастроитьРасписаниеРегламентногоЗадания.Доступность = Объект.ИспользоватьРегламентноеЗадание;
	Элементы.ДекорацияРазработкаМОНО.Видимость = ЭтоМоноБанкAPI;
	Элементы.ФайлЗагрузки.Видимость = ЭтоФайловаяВыписка;
	Элементы.ФайлВыгрузки.Видимость = ЭтоФайловаяВыписка;
	
КонецПроцедуры

&НаСервере
Функция НачатьВыполнениеНаСервереОбмена()
	
	ПараметрыВыполнения = ДлительныеОперации.ПараметрыВыполненияФункции(УникальныйИдентификатор);
	ПараметрыВыполнения.ОжидатьЗавершение = Ложь;
	ПараметрыВыполнения.НаименованиеФоновогоЗадания = "Обмен с банком (" + Объект.Ссылка + ")";
	ПараметрыВыполнения.ЗапуститьВФоне = Истина;
	
	Возврат ДлительныеОперации.ВыполнитьПроцедуру(ПараметрыВыполнения, "СМП_РаботаСБанкамиСервер.ОбменСБанком", Объект.Ссылка);
	
КонецФункции

&НаКлиенте
Процедура ОбработатьРезультат(Результат, ДополнительныеПараметры) Экспорт
	
	Если Результат = Неопределено Тогда
		Возврат;
	КонецЕсли;
	
	Если Результат.Статус = "Ошибка" Тогда
		Сообщить(Результат.КраткоеПредставлениеОшибки);
	Иначе
		
		//РезультатРаботы = ПолучитьИзВременногоХранилища(Результат.АдресРезультата);
		//Если ЗначениеЗаполнено(РезультатРаботы.Ошибка) Тогда
		//	Сообщить(РезультатРаботы.Ошибка);
		//Иначе
		//	ЭтотОбъект.Прочитать();
		//	Элементы.Товары.Обновить();
		//КонецЕсли;
		
	КонецЕсли;
	
КонецПроцедуры 

&НаКлиенте
Процедура ВыборФайлаДляЗагрузки(Элемент, Режим) Экспорт
	
	ДиалогВыбора = Новый ДиалогВыбораФайла(РежимДиалогаВыбораФайла.Открытие);
	
	ДиалогВыбора.Фильтр                      = НСтр("ru='" + Объект.РасширениеФайлаИмпорта + " файл';uk='" + Объект.РасширениеФайлаИмпорта + " файл'") + " (*." + Объект.РасширениеФайлаИмпорта + ")|*." + Объект.РасширениеФайлаИмпорта;
	ДиалогВыбора.Заголовок                   = СтроковыеФункцииКлиентСервер.ПодставитьПараметрыВСтроку(
		НСтр("ru='Выберите файл для %1 данных из клиента банка';uk='Виберіть файл для %1 даних з клієнта банку'"), Режим);
	ДиалогВыбора.ПредварительныйПросмотр     = Ложь;
	ДиалогВыбора.Расширение                  = Объект.РасширениеФайлаИмпорта;
	ДиалогВыбора.ИндексФильтра               = 0;
	ДиалогВыбора.ПолноеИмяФайла              = ?(ПустаяСтрока(Элемент.ТекстРедактирования),
		?(Режим = НСтр("ru='выгрузки';uk='вивантаження'"), "1C_to_CB." + Объект.РасширениеФайлаИмпорта, "CB_to_1C." + Объект.РасширениеФайлаИмпорта), Элемент.ТекстРедактирования);
	ДиалогВыбора.ПроверятьСуществованиеФайла = Ложь;
	
	Если ДиалогВыбора.Выбрать() Тогда
		Если Режим = НСтр("ru='загрузки';uk='завантаження'") Тогда
			Объект.ФайлЗагрузки = ДиалогВыбора.ПолноеИмяФайла;
		Иначе
			Объект.ФайлВыгрузки = ДиалогВыбора.ПолноеИмяФайла;
		КонецЕсли;
	КонецЕсли;
	
КонецПроцедуры

&НаКлиенте
Процедура ВыборФайлаДляВыгрузки(Элемент, Режим) Экспорт
	
	ДиалогВыбора = Новый ДиалогВыбораФайла(РежимДиалогаВыбораФайла.Открытие);
	
	ДиалогВыбора.Фильтр                      = НСтр("ru='" + Объект.РасширениеФайлаЭкспорта + " файл';uk='" + Объект.РасширениеФайлаЭкспорта + " файл'") + " (*." + Объект.РасширениеФайлаЭкспорта + ")|*." + Объект.РасширениеФайлаЭкспорта;
	ДиалогВыбора.Заголовок                   = СтроковыеФункцииКлиентСервер.ПодставитьПараметрыВСтроку(
		НСтр("ru='Выберите файл для %1 данных из клиента банка';uk='Виберіть файл для %1 даних з клієнта банку'"), Режим);
	ДиалогВыбора.ПредварительныйПросмотр     = Ложь;
	ДиалогВыбора.Расширение                  = Объект.РасширениеФайлаЭкспорта;
	ДиалогВыбора.ИндексФильтра               = 0;
	ДиалогВыбора.ПолноеИмяФайла              = ?(ПустаяСтрока(Элемент.ТекстРедактирования),
		?(Режим = НСтр("ru='выгрузки';uk='вивантаження'"), "1C_to_CB." + Объект.РасширениеФайлаЭкспорта, "CB_to_1C." + Объект.РасширениеФайлаЭкспорта), Элемент.ТекстРедактирования);
	ДиалогВыбора.ПроверятьСуществованиеФайла = Ложь;
	
	Если ДиалогВыбора.Выбрать() Тогда
		Если Режим = НСтр("ru='загрузки';uk='завантаження'") Тогда
			Объект.ФайлЗагрузки = ДиалогВыбора.ПолноеИмяФайла;
		Иначе
			Объект.ФайлВыгрузки = ДиалогВыбора.ПолноеИмяФайла;
		КонецЕсли;
	КонецЕсли;
	
КонецПроцедуры

&НаСервере
Процедура ПодключаемаяОбработкаПриИзмененииНаСервере()
	Если ЗначениеЗаполнено(Объект.ПодключаемаяОбработка) Тогда
		Объект.РасширениеФайлаИмпорта = ПолучитьФорматФайла(Объект.ПодключаемаяОбработка);  
		Объект.РасширениеФайлаЭкспорта = ПолучитьФорматФайлаЭкспорта(Объект.ПодключаемаяОбработка);
	КонецЕсли;
КонецПроцедуры   

&НаСервере
Функция ПолучитьФорматФайла(ОбработкаПротокола)
	
	Если ЗначениеЗаполнено(ОбработкаПротокола) И ТИПЗНЧ(ОбработкаПротокола) <> ТИП("СправочникСсылка.СМП_УчетныеЗаписиБанков") Тогда
		Попытка
			ИмяФайла = ПолучитьИмяВременногоФайла("epf");
			ОбработкаОткр = ОбработкаПротокола.ХранилищеОбработки.Получить();
			ОбработкаОткр.Записать(ИмяФайла);
			ВнешняяОбработка = ВнешниеОбработки.Создать(ИмяФайла, Ложь);
			Формат = ВнешняяОбработка.ФорматФайла();
			УдалитьФайлы(ИмяФайла);
			Возврат Формат;
		Исключение
		КонецПопытки;
	КонецЕсли;
	
	Возврат "xml";
	
КонецФункции

&НаСервере
Функция ПолучитьФорматФайлаЭкспорта(ОбработкаПротокола)
	
	Если ЗначениеЗаполнено(ОбработкаПротокола) И ТИПЗНЧ(ОбработкаПротокола) <> ТИП("СправочникСсылка.СМП_УчетныеЗаписиБанков") Тогда
		Попытка
			ИмяФайла = ПолучитьИмяВременногоФайла("epf");
			ОбработкаОткр = ОбработкаПротокола.ХранилищеОбработки.Получить();
			ОбработкаОткр.Записать(ИмяФайла);
			ВнешняяОбработка = ВнешниеОбработки.Создать(ИмяФайла, Ложь);
			Формат = ВнешняяОбработка.ФорматФайлаВыгрузки();
			УдалитьФайлы(ИмяФайла);
			Возврат Формат;
		Исключение
		КонецПопытки;
	КонецЕсли;
	
	Возврат "xml";
	
КонецФункции

// Возвращает "Истина" если введен корректный адрес публикации http-сервиса.
//
// Параметры:
//   АдресWebHook - Строка - Адрес публикации http-сервиса информационной базы для установки WebHook.
//
// Возвращаемое значение:
//   Булево - результат проверки адреса.
//
&НаСервереБезКонтекста
Функция ПроверитьАдресWebHookНаСервере(АдресWebHook) 

	Результат = Истина;

	СтруктураURL = КоннекторHTTP_BankExchange.РазобратьURL(АдресWebHook);
	Если СтруктураURL.Путь = "/" ИЛИ СтрНайти(СтруктураURL.Путь, "/hs/") = 0 Тогда //Адрес базы введен некоретно
		Результат = Ложь;
	КонецЕсли;	
	
	Возврат Результат;
	
КонецФункции // ПроверитьАдресWebHookНаСервере

// Возврашает результат установки адреса для Webhook.
//
// Параметры:
//	 Токен - Строка - токен доступа к API монобанка.
//   АдресWebHook - Строка - Адрес публикации http-сервиса информационной базы для установки WebHook.
//
// Возвращаемое значение:
//   Булево, Строка - Истина - если успешно, Строка - если возникла ошибка.
//
&НаСервереБезКонтекста
Функция УстановитьАдресWebHookНаСервере(Токен, АдресWebHook) 
	
	Результат = Истина;
	АдресСервераМонобанк = "https://api.monobank.ua/personal/webhook";
	
	ТелоСтруктура = Новый Структура("webHookUrl", АдресWebHook);
	Заголовки = Новый Соответствие;
	Заголовки.Вставить("X-Token", Токен);
	
	ДопПараметры = Новый Структура("JSON, Заголовки", ТелоСтруктура, Заголовки);
	ДанныеОтвета = КоннекторHTTP_BankExchange.Post(АдресСервераМонобанк,, ДопПараметры);
	
	Если ДанныеОтвета.КодСостояния <> 200 Тогда
		сОтвет = КоннекторHTTP_BankExchange.КакJson(ДанныеОтвета);
		
		СтрокаРезультат = "";
		Для Каждого КлючИЗначение Из сОтвет Цикл
			
			СтрокаРезультат = КлючИЗначение.Ключ + ": " + КлючИЗначение.Значение; 
			Прервать;
			
		КонецЦикла;
		Результат = СтрокаРезультат;
	КонецЕсли;
	
	Возврат Результат;
	
КонецФункции // УстановитьАдресWebHookНаСервере 

#Область РегламентноеЗадание

// .
//
// Параметры:
//   
//
&НаКлиенте
Процедура НастройкаРасписанияЗавершение(пРасписание, пДополнительныеПараметры) Экспорт
	
	Если пРасписание <> Неопределено Тогда
		
		НастроитьРасписаниеРегламентногоЗадания = пРасписание;
		УстановитьНовоеРасписание(пРасписание);
		Модифицированность = Истина;
		
	КонецЕсли;
	
КонецПроцедуры //НастройкаРасписанияЗавершение

// .
//
// Параметры:
//   <Параметр1> - <Тип.Вид> - <описание параметра>
//                 <продолжение описания параметра>
//   <Параметр2> - <Тип.Вид> - <описание параметра>
//                 <продолжение описания параметра>
//
&НаСервере
Процедура УстановитьНовоеРасписание(пРасписание) 
	
	Объект.РасписаниеРегламентногоЗадания = ЗначениеВСтрокуВнутр(пРасписание);
	
КонецПроцедуры //УстановитьНовоеРасписание

// .
//
// Параметры:
//   <Параметр1> - <Тип.Вид> - <описание параметра>
//                 <продолжение описания параметра>
//   <Параметр2> - <Тип.Вид> - <описание параметра>
//                 <продолжение описания параметра>
//
// Возвращаемое значение:
//   <Тип.Вид> - <описание возвращаемого значения>
//
&НаСервереБезКонтекста
Функция РасписаниеРеглЗадания(пРасписание) 
	
	Результат = Неопределено;
	
	Попытка
		Результат = ЗначениеИзСтрокиВнутр(пРасписание);
	Исключение
	КонецПопытки;
	
	Если ТипЗнч(Результат) <> Тип("РасписаниеРегламентногоЗадания") Тогда
		Результат = Новый РасписаниеРегламентногоЗадания;
	КонецЕсли;
	
	Возврат Результат;
	
КонецФункции // РасписаниеРеглЗадания


&НаСервере
// Создает новое задание очереди заданий.
//
// Возвращаемое значение: УникальныйИдентификатор.
//
Функция СоздатьНовоеЗадание(КодНастройки, НаименованиеНастройки, Расписание, ПолныйПарсинг = Ложь) Экспорт
	
	УстановитьПривилегированныйРежим(Истина);
	
	ПараметрыЗадания = Новый Массив;
	ПараметрыЗадания.Добавить(КодНастройки);
	
	ИдентификаторРегламентногоЗадания = Неопределено;
	Задание = РегламентныеЗадания.СоздатьРегламентноеЗадание("СМП_ОбменСБанкамиAPI");
	Задание.Использование = Истина;
	Задание.Ключ = Строка(Новый УникальныйИдентификатор);
	Задание.Наименование = НаименованиеНастройки;
	Задание.Параметры = ПараметрыЗадания;
	Задание.Расписание = Расписание;
	Задание.Записать();
	
	ИдентификаторРегламентногоЗадания = Задание.УникальныйИдентификатор;
	
	Возврат ИдентификаторРегламентногоЗадания;
	
КонецФункции

&НаСервере
// Устанавливает параметры регламентного задания или задания очереди заданий.
//
// Параметры:
//  Задание - СправочникСсылка.ОчередьЗаданийОбластейДанных,
//  Использование - булево, флаг использования регламентного задания,
//  КодУзла - Строка - Код узла плана обмена
//  НаименованиеУзла - Строка - Наименование узла плана обмена
//  Расписание - РасписаниеРегламентногоЗадания.
//
Процедура УстановитьПараметрыЗадания(Задание, Использование, КодНастройки, НаименованиеНастройки, Расписание) Экспорт
	
	УстановитьПривилегированныйРежим(Истина);
	
	ПараметрыЗадания = Новый Массив;
	ПараметрыЗадания.Добавить(КодНастройки);
	
	Задание.Использование = Истина;
	Задание.Ключ = Строка(Новый УникальныйИдентификатор);
	Задание.Наименование = НаименованиеНастройки;
	Задание.Параметры = ПараметрыЗадания;
	Задание.Расписание = Расписание;
	Задание.Записать();
	
КонецПроцедуры

#КонецОбласти

#КонецОбласти
