////////////////////////////////////////////////////////////////////////////////
// СМП_РаботаСБанкамиМонобанкAPIСервер: содержит процедуры подключения, получения данных и парсинга выписки через API Monobank
// Описание API monobank:
// https://api.monobank.ua/docs/
////////////////////////////////////////////////////////////////////////////////

#Область ПрограммныйИнтерфейс

#КонецОбласти

#Область СлужебныйПрограммныйИнтерфейс

// Выполняет загрузку даных через API monobank.
//
// Параметры:
//   ФормаЗагрузкиКлиентБанка - ФормаКлиентскогоПриложения - обработка КлиентБанк: ФормаЗагрузка.
//   УчетнаяЗаписьБанка - СправочникСсылка.СМП_УчетныеЗаписиБанков - учетная запись для которой выполняется получение данных.
//   ТокенАвторизации - Строка - ключ для авторизации при подключении через API.
//   ТаблицаТаблицДокументов - ТаблицаЗначений - таблица документов.
//	 ТаблицаКонтрагентов - ДеревоЗначений - список контрагентов.
//
Процедура ЗагрузитьДанныеПоВыписке(ФормаЗагрузкиКлиентБанка, УчетнаяЗаписьБанка, ТокенАвторизации, ТаблицаТаблицДокументов, ТаблицаКонтрагентов) Экспорт

	ФормаЗагрузкиКлиентБанка.ТаблицаКонтрагентов.ПолучитьЭлементы().Очистить();
	// Подготавливаем структуры обработки данных.
	ДокументыКИмпорту = ФормаЗагрузкиКлиентБанка.Объект.Загрузка.Выгрузить();
	ДокументыКИмпорту.Колонки.Добавить("КодНазПлатежа", Новый ОписаниеТипов("Строка",, Новый КвалификаторыСтроки(1)));

	ИмпортЗагружаемые = Обработки.СМП_КлиентБанк.СформироватьСоответствиеЗагружаемых();
	ИмпортНеПустые = Неопределено;
	ИмпортНеПустыеПлатежноеПоручение = Неопределено;
	ИмпортНеПустыеПлатежноеПоручениеБюджет = Неопределено;
	РасчетныеСчетаКИмпорту = ФормаЗагрузкиКлиентБанка.Объект.ИмпортРасчетныеСчета.Выгрузить();
	
	Обработки.СМП_КлиентБанк.СформироватьСоответствияНеПустыхПриИмпорте(
	ИмпортНеПустые,
	ИмпортНеПустыеПлатежноеПоручение,
	ИмпортНеПустыеПлатежноеПоручениеБюджет
	);
	ТегиРасчетногоСчета = Обработки.СМП_КлиентБанк.СоздатьСоответствиеИзСтроки(
	ВРег("ДатаНачала,ДатаКонца,РасчСчетОрг,НачальныйОстаток,ВсегоПоступило,ВсегоСписано,КонечныйОстаток,КонецРасчСчет")
	);
	ТегиЗаголовка = Обработки.СМП_КлиентБанк.СоздатьСоответствиеИзСтроки(
	ВРег("ВерсияФормата,Кодировка,Отправитель,Получатель,ДатаСоздания,ВремяСоздания,ДатаНачала,ДатаКонца")
	);
	СтруктураЗаголовок = Новый Структура(
	ВРег("ВерсияФормата,Кодировка,Отправитель,Получатель,ДатаСоздания,ВремяСоздания,ДатаНачала,ДатаКонца")
	);
	ФормаЗагрузкиКлиентБанка.ИмпортЗаголовок = СтруктураЗаголовок;
	ИмпортПризнакОбмена = Ложь;
	НайденКонецФайла = Ложь;
	ИмпортВидыДокументов = Новый Массив;
	РасчетныеСчетаКИмпорту.Очистить();
	ДокументыКИмпорту.Очистить();
		
	КонтекстФормы = Новый Структура;
	КонтекстФормы.Вставить("ИмпортТекстДляРазбора", "");
	КонтекстФормы.Вставить("ПослеЗагрузкиВыписокВ1С", ФормаЗагрузкиКлиентБанка.ПослеЗагрузкиВыписокВ1С);
	КонтекстФормы.Вставить("ИскатьВСправочникеСоответствий", ФормаЗагрузкиКлиентБанка.ИскатьВСправочникеСоответствий);
	КонтекстФормы.Вставить("ТаблицаКонтрагентов", ТаблицаКонтрагентов);
	КонтекстФормы.Вставить("РасчетныеСчетаКИмпорту", РасчетныеСчетаКИмпорту);
	КонтекстФормы.Вставить("ДокументыКИмпорту", ДокументыКИмпорту);
	КонтекстФормы.Вставить("ТаблицаТаблицДокументов", ТаблицаТаблицДокументов);
	Если ФормаЗагрузкиКлиентБанка.ПослеЗагрузкиВыписокВ1С Тогда
		КонтекстФормы.Вставить("СтруктураДанныхЗагрузки", ФормаЗагрузкиКлиентБанка.СтруктураДанныхЗагрузки);
	КонецЕсли;
	
	ВременнаяСтрока = ФормаЗагрузкиКлиентБанка.ТаблицаТаблицДокументов.Добавить();
	КонтекстФормы.Вставить("ТаблицаНайденныхДокументов", ВременнаяСтрока.ТаблицаНайденныхДокументов.Выгрузить());
	ФормаЗагрузкиКлиентБанка.ТаблицаТаблицДокументов.Удалить(0);
	
	КонтекстФормы.Вставить("ЕстьОтборПоБанковскомуСчету", ФормаЗагрузкиКлиентБанка.ЕстьОтборПоБанковскомуСчету);
	КонтекстФормы.Вставить("ВыдаватьСообщенияОНеверныхРеквизитахИСекциях", ФормаЗагрузкиКлиентБанка.ВыдаватьСообщенияОНеверныхРеквизитахИСекциях);
	
	СтруктураОбъекта = Новый Структура;
	СтруктураОбъекта.Вставить("Организация", ФормаЗагрузкиКлиентБанка.Объект.Организация);
	СтруктураОбъекта.Вставить("БанковскийСчет", ФормаЗагрузкиКлиентБанка.Объект.БанковскийСчет);
	СтруктураОбъекта.Вставить("АвтоматическиПодставлятьДокументы", ФормаЗагрузкиКлиентБанка.Объект.АвтоматическиПодставлятьДокументы);
	СтруктураОбъекта.Вставить("АнализироватьИсториюВыбораЗначенийРеквизитов", ФормаЗагрузкиКлиентБанка.Объект.АнализироватьИсториюВыбораЗначенийРеквизитов);
	СтруктураОбъекта.Вставить("СтатьяДДСИсходящий", ФормаЗагрузкиКлиентБанка.Объект.СтатьяДДСИсходящий);
	СтруктураОбъекта.Вставить("СтатьяДДСВходящий", ФормаЗагрузкиКлиентБанка.Объект.СтатьяДДСВходящий);
	СтруктураОбъекта.Вставить("СпособЗачета", ФормаЗагрузкиКлиентБанка.Объект.СпособЗачета);
	
	КонтекстФормы.Вставить("Объект", СтруктураОбъекта);

	//ПрочитатьВыписки(ФормаЗагрузкиКлиентБанка.Объект.НачПериода, 
	//	КонецДня(ФормаЗагрузкиКлиентБанка.Объект.КонПериода), 
	//	ФормаЗагрузкиКлиентБанка.Объект.БанковскийСчет, 
	//	ДокументыКИмпорту, 
	//	"", 
	//	ТокенАвторизации);
	
	ПрочитатьДанныеБанковскойВыписки(ДокументыКИмпорту, ФормаЗагрузкиКлиентБанка.Объект.БанковскийСчет, ТокенАвторизации, 
	ФормаЗагрузкиКлиентБанка.Объект.НачПериода, КонецДня(ФормаЗагрузкиКлиентБанка.Объект.КонПериода));
	
	НомерСтроки = 0;
	
	КоличествоНеНайденныхКонтрагентов = 0;
	КоличествоНеНайденныхРСчетов = 0;
	
	ПараметрыВыделенияКолонок = Новый Структура("ВыделитьКолонкуДокумент, ВыделитьКолонкуСуммаСписано, ВыделитьКолонкуСуммаПоступило, 
	|ВыделитьКолонкуКонтрагент, ВыделитьКолонкуДоговор, ВыделитьКолонкуРСКонтрагента, ВыделитьКолонкуВидОперации", 
	Ложь, Ложь, Ложь, Ложь, Ложь, Ложь, Ложь);
	
	Для каждого СтрокаДокумента Из ДокументыКИмпорту Цикл
		Если (СтрокаДокумента.ПлательщикСчет = ФормаЗагрузкиКлиентБанка.Объект.БанковскийСчет.НомерСчета
			ИЛИ СтрокаДокумента.ПолучательСчет  = ФормаЗагрузкиКлиентБанка.Объект.БанковскийСчет.НомерСчета) 
			И ЗначениеЗаполнено(ФормаЗагрузкиКлиентБанка.Объект.БанковскийСчет.ВалютаДенежныхСредств)
			Тогда
			
			ФормаЗагрузкиКлиентБанка.БанковскийСчетНомер = ФормаЗагрузкиКлиентБанка.Объект.БанковскийСчет.НомерСчета;
			ФормаЗагрузкиКлиентБанка.БанковскийСчетВалюта = ФормаЗагрузкиКлиентБанка.Объект.БанковскийСчет.ВалютаДенежныхСредств;
			
			Обработки.СМП_КлиентБанк.РаспознатьДанныеВСтрокеДокумента(СтрокаДокумента, Неопределено, ПараметрыВыделенияКолонок, 
			ФормаЗагрузкиКлиентБанка.Объект, ТаблицаТаблицДокументов, КонтекстФормы, ФормаЗагрузкиКлиентБанка.ПослеЗагрузкиВыписокВ1С);
			НомерСтроки = НомерСтроки + 1;
			СтрокаДокумента.НомерСтроки = НомерСтроки;
			
			Для каждого КолонкаИмпорта из ДокументыКИмпорту.Колонки Цикл
				Обработки.СМП_КлиентБанк.ПроверитьНаПустоеЗначениеИмпорта(СтрокаДокумента, КолонкаИмпорта.Имя, КолонкаИмпорта.Заголовок, ИмпортНеПустые);
			КонецЦикла;
			
			Если ТипЗнч(СтрокаДокумента.Контрагент)=Тип("Строка") ИЛИ
				ТипЗнч(СтрокаДокумента.СчетКонтрагента)=Тип("Строка") ИЛИ
				ТипЗнч(СтрокаДокумента.Договор)=Тип("Строка") Тогда
				
				Обработки.СМП_КлиентБанк.СписокНенайденных(СтрокаДокумента, ФормаЗагрузкиКлиентБанка.Объект.БанковскийСчет, 
				ТаблицаКонтрагентов, КоличествоНеНайденныхКонтрагентов, КоличествоНеНайденныхРСчетов);
			КонецЕсли;
		Иначе
			//остальные помечаем для последующего удаления
			СтрокаДокумента.НомерСтроки = 0;
		КонецЕсли;
	КонецЦикла;
	
	//Удалим не нужные строки из таблицы
	Количество = ДокументыКИмпорту.количество()-1;
	Для й=0 по Количество Цикл
		Если ДокументыКИмпорту[Количество-й].НомерСтроки = 0 Тогда
			ДокументыКИмпорту.Удалить(Количество-й);
		КонецЕсли;
	КонецЦикла;
	
	Для каждого СтрокаДокумента Из ДокументыКИмпорту Цикл
		СтрокаДокумента.Загружать = ПустаяСтрока(СтрокаДокумента.ОписаниеОшибок);
		СтрокаДокумента.НазначениеПлатежа = СокрЛП(СтрокаДокумента.НазначениеПлатежа);
		СтрокаДокумента.НомерКартинки = ?(ПустаяСтрока(СтрокаДокумента.ОписаниеОшибок), 0, 1);
	КонецЦикла;
	
	ФормаЗагрузкиКлиентБанка.Объект.Загрузка.Очистить();
	ФормаЗагрузкиКлиентБанка.Объект.Загрузка.Загрузить(ДокументыКИмпорту);
	
	ФормаЗагрузкиКлиентБанка.Объект.ИмпортРасчетныеСчета.Очистить();
	ФормаЗагрузкиКлиентБанка.Объект.ИмпортРасчетныеСчета.Загрузить(РасчетныеСчетаКИмпорту);	
	
КонецПроцедуры //ЗагрузитьДанныеПоВыписке

#КонецОбласти

#Область СлужебныеПроцедурыИФункции

// ПрочитатьДанныеОТранзакицяхЗаПериод.
//
// Параметры:
//   ДокументыКИмпорту - ТаблицаЗначений - контейнер для данных банковской выписки.
//   БанковскийСчет - СправочникСсылка.БанковскиеСчета - счет бля которого выполняется загрузка данных. 
//   ТокенАвторизации - Строка - ключ для авторизации через API.
//   НачалоПериода - Дата - дата начала периода за который загружаются данные.
//	 КонецПериода - Дата - дата окончания периода за который загружаются данные.
//
Процедура ПрочитатьДанныеБанковскойВыписки(ДокументыКИмпорту, БанковскийСчет, ТокенАвторизации, НачалоПериода, КонецПериода) 
	
	НомерСчетаIBAN = ОбщегоНазначения.ЗначениеРеквизитаОбъекта(БанковскийСчет, "НомерСчета", Истина);
		
	мСессия = КоннекторHTTP_BankExchange.СоздатьСессию();
	мСессия.Заголовки.Вставить("X-Token", ТокенАвторизации);
	
	URLКлиентИнфо = "https://api.monobank.ua/personal/client-info";
	идСчета = ПолучитьИдентификаторСчетаIBAN(мСессия, URLКлиентИнфо, НомерСчетаIBAN); 
	
	Если идСчета = Неопределено Тогда
		
		ТекстСообщения = НСтр("ru='Не обнаружены данные по счету № %1. Возможно указан некорректный номер счета IBAN.';
		|uk='Не знайдені дані по рахунку № %1. Можливо вказаний некоректний номер рахунку IBAN.'");
		ТекстСообщения = СтрШаблон(ТекстСообщения, НомерСчетаIBAN);
		ОбщегоНазначения.СообщитьПользователю(ТекстСообщения);
		Возврат;
		
	КонецЕсли;
	
	ЮниксДатаНач = ДатаВремяВUnixTime(НачалоПериода);
	ЮниксдатаКон = ДатаВремяВUnixTime(КонецПериода);
	
	URLВыпискаЗаПериод = "https://api.monobank.ua/personal/statement/%1/%2/%3";
	URLВыпискаЗаПериод = СтрШаблон(URLВыпискаЗаПериод, идСчета, ЮниксДатаНач, ЮниксдатаКон);
	
	мОтветВыписка = КоннекторHTTP_BankExchange.Get(URLВыпискаЗаПериод,,, мСессия);
	Если мОтветВыписка.КодСостояния = 200 Тогда
		
		ДанныеВыписки = КоннекторHTTP_BankExchange.КакJson(мОтветВыписка);
		ЗаполнитьТаблицуДаннымиТранзакций(ДанныеВыписки, ДокументыКИмпорту, НомерСчетаIBAN);
		
	Иначе
		
		СтрокаОшибка = "";
		ДанныеОшибка = КоннекторHTTP_BankExchange.КакJson(мОтветВыписка);
		Для Каждого КлючЗначениеОтвета Из ДанныеОшибка Цикл
			
			СтрокаОшибка = КлючЗначениеОтвета.Ключ + ": " + КлючЗначениеОтвета.Значение;
			Прервать;
			
		КонецЦикла;
		
		ТекстСообщения = НСтр("ru='Ошибка при получении банковской выписки за указанный период: ';
		|uk='Помилка отримання банківської виписки за вказаний період: '") + Символы.ПС + СтрокаОшибка;
		ОбщегоНазначения.СообщитьПользователю(ТекстСообщения);
		
	КонецЕсли;
	
КонецПроцедуры //ПрочитатьДанныеОТранзакцияхЗаПериод

// Возвращает идентификатор банковского счета.
//
// Параметры:
//   Сессия - Структура - см. КоннекторHTTP_BankExchange.СоздатьСессию() .
//   URLКлиентИнфо - Строка - URL-адрес для отправки запроса.
//   НомерСчетаIBAN - Строка - номер банковского счета для которого нужно получить идентификатор.
//
// Возвращаемое значение:
//   Строка, Неопределено - идентификатор банковского счета.
//
Функция ПолучитьИдентификаторСчетаIBAN(Сессия, URLКлиентИнфо, НомерСчетаIBAN) 
	
	идСчета = Неопределено;
	
	ОтветКлиентИнфо = КоннекторHTTP_BankExchange.Get(URLКлиентИнфо,,, Сессия);
	
	Если ОтветКлиентИнфо.КодСостояния = 200 Тогда
		
		мДанныеКлиента = КоннекторHTTP_BankExchange.КакJson(ОтветКлиентИнфо);
		мСписокСчетов = мДанныеКлиента["accounts"];
		
		Для Каждого мДанныеСчета Из мСписокСчетов Цикл
			
			Если мДанныеСчета["iban"] = НомерСчетаIBAN Тогда
				идСчета = мДанныеСчета["id"];
				Прервать;
			КонецЕсли;
			
		КонецЦикла;
	КонецЕсли;
	
	Возврат идСчета;
	
КонецФункции // ПолучитьИдентификаторСчетаIBAN

// Возвращает значение даты в формате "Unix Time".
//
// Параметры:
//   ДатаВремя - Дата - дата для преобразования.
//
// Возвращаемое значение:
//   Число - Время в формате "Unix Time" (количество секунд начиная с 01.01.1970).
//
Функция ДатаВремяВUnixTime(ДатаВремя) 
	
	Результат = Формат(ДатаВремя - Дата("19700101"), "ЧГ=0");	
	
	Возврат Результат;
	
КонецФункции // ДатаВремяВUnixTime

// Выполняет анализ и загрузку данных о транзакциях в таблицу.
//
// Параметры:
//   ДанныеВыписки - Соответствие - преобразованные данные из JSON, полученные через API.
//   ДокументыКИмпорту - ТаблицаЗначений - таблица для наполнения данными.
//
Процедура ЗаполнитьТаблицуДаннымиТранзакций(ДанныеВыписки, ДокументыКИмпорту, НомерСчетаIBAN) 

	МассивТранзакций = Неопределено;
	Если ТипЗнч(ДанныеВыписки) = Тип("Массив") Тогда
		МассивТранзакций = ДанныеВыписки;
	Иначе
		ОбщегоНазначения.СообщитьПользователю(
		НСтр("ru='Изменился формат получаемых данных! Обратитесь к разработчику.'; uk='Змінився формат отримуваних даних. Зверніться до розробника.'"));
		Возврат;
	КонецЕсли;
	
	Для Каждого мТранзакция Из МассивТранзакций Цикл
		
		КонтрагентСчет = мТранзакция["counterIban"];
		КонтрагентЕДРПОУ = мТранзакция["counterEdrpou"];		
		мДатаТранзакции = Дата("19700101") + мТранзакция["time"];
		мДатаТрСтрокой = Формат(мДатаТранзакции, "ДФ='dd.MM.yyyy HH:mm:ss'");
		
		НоваяСтрока = ДокументыКИмпорту.Добавить();
		НоваяСтрока.ДокументИД = мТранзакция["id"];
		НоваяСтрока.Дата = мДатаТрСтрокой;
		НоваяСтрока.НазначениеПлатежа = СокрЛП(мТранзакция["description"]);
		
        мСумма = мТранзакция["amount"] / 100;
		НоваяСтрока.СуммаДокумента = ?(мСумма < 0, -1 * мСумма, мСумма);
		Если мСумма < 0 Тогда
			
			НоваяСтрока.Операция = "ПлатежноеПоручение";
			НоваяСтрока.Сумма = Формат(НоваяСтрока.СуммаДокумента, "ЧГ=0");
			НоваяСтрока.СуммаСписано = НоваяСтрока.СуммаДокумента;
			НоваяСтрока.ПлательщикСчет = НомерСчетаIBAN;
			НоваяСтрока.ПолучательСчет = КонтрагентСчет;
			НоваяСтрока.ПолучательКПП = КонтрагентЕДРПОУ;
			НоваяСтрока.ДатаСписано = мДатаТрСтрокой;
			НоваяСтрока.Списано = мДатаТранзакции;
		Иначе
			НоваяСтрока.Операция = "ПлатежноеТребование";
			НоваяСтрока.Сумма = Формат(НоваяСтрока.СуммаДокумента, "ЧГ=0");
			НоваяСтрока.ПлательщикСчет = КонтрагентСчет;
			НоваяСтрока.ПлательщикКПП = КонтрагентЕДРПОУ;
			НоваяСтрока.ПолучательСчет = НомерСчетаIBAN;
			НоваяСтрока.СуммаПоступило = НоваяСтрока.СуммаДокумента;
			НоваяСтрока.ДатаПоступило = мДатаТрСтрокой;
			НоваяСтрока.Поступило = мДатаТранзакции;
		КонецЕсли;
		
		
		НоваяСтрока.КодВалюты = мТранзакция["currencyCode"];
		
		Комиссия = мТранзакция["commissionRate"];
		Кэшбэк = мТранзакция["cashbackAmount"];
		
		Если Комиссия > 0 Тогда
			НоваяСтрока.НазначениеПлатежа = НоваяСтрока.НазначениеПлатежа + " Сума комісії " + Формат(Комиссия / 100, "ЧГ=0");
		КонецЕсли;
		
		Если Кэшбэк > 0 Тогда
			НоваяСтрока.НазначениеПлатежа = НоваяСтрока.НазначениеПлатежа + " Кешбек " + Формат(Кэшбэк / 100, "ЧГ=0");	
		КонецЕсли;
			
	КонецЦикла;
	
КонецПроцедуры //ЗаполнитьТаблицуДаннымиТранзакций

#КонецОбласти