﻿
Функция СведенияОВнешнейОбработке() Экспорт
	
	ПараметрыРегистрации = ДополнительныеОтчетыИОбработки.СведенияОВнешнейОбработке();
	
	ПараметрыРегистрации.Вид = ДополнительныеОтчетыИОбработкиКлиентСервер.ВидОбработкиДополнительнаяОбработка();
	ПараметрыРегистрации.Наименование = НСтр("ru='Обработка выписки банка Пивденный';uk='Обробка виписки банка Південний'");
	ПараметрыРегистрации.Информация = НСтр("ru='Обработка формата загрузки данных украинского банка Пивденный';uk='Обробка формату завантаження даних українського банка Південний'");
	ПараметрыРегистрации.Версия = "2.1";
	ПараметрыРегистрации.БезопасныйРежим = Ложь;
	
	Возврат ПараметрыРегистрации;
	
КонецФункции

// Обработчик чтения формата для конфигурации BASSmallBusiness
Процедура Загрузить_УНФ(Элемент, ФайлЗагрузки, ТаблицаТаблицДокументов, ТаблицаКонтрагентов) Экспорт
	
	Элемент.ТаблицаКонтрагентов.ПолучитьЭлементы().Очистить();
	
	// Подготавливаем структуры обработки данных.
	ДокументыКИмпорту = Элемент.Объект.Загрузка.Выгрузить();
	ДокументыКИмпорту.Колонки.Добавить("КодНазПлатежа", Новый ОписаниеТипов("Строка",, Новый КвалификаторыСтроки(1)));

	ИмпортЗагружаемые = Обработки.СМП_КлиентБанк.СформироватьСоответствиеЗагружаемых();
	ИмпортНеПустые = Неопределено;
	ИмпортНеПустыеПлатежноеПоручение = Неопределено;
	ИмпортНеПустыеПлатежноеПоручениеБюджет = Неопределено;
	РасчетныеСчетаКИмпорту = Элемент.Объект.ИмпортРасчетныеСчета.Выгрузить();
	
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
	Элемент.ИмпортЗаголовок = СтруктураЗаголовок;
	ИмпортПризнакОбмена = Ложь;
	НайденКонецФайла = Ложь;
	ИмпортВидыДокументов = Новый Массив;
	РасчетныеСчетаКИмпорту.Очистить();
	ДокументыКИмпорту.Очистить();
		
	КонтекстФормы = Новый Структура;
	КонтекстФормы.Вставить("ИмпортТекстДляРазбора", ФайлЗагрузки);
	КонтекстФормы.Вставить("ПослеЗагрузкиВыписокВ1С", Элемент.ПослеЗагрузкиВыписокВ1С);
	КонтекстФормы.Вставить("ИскатьВСправочникеСоответствий", Элемент.ИскатьВСправочникеСоответствий);
	КонтекстФормы.Вставить("ТаблицаКонтрагентов", ТаблицаКонтрагентов);
	КонтекстФормы.Вставить("РасчетныеСчетаКИмпорту", РасчетныеСчетаКИмпорту);
	КонтекстФормы.Вставить("ДокументыКИмпорту", ДокументыКИмпорту);
	КонтекстФормы.Вставить("ТаблицаТаблицДокументов", ТаблицаТаблицДокументов);
	Если Элемент.ПослеЗагрузкиВыписокВ1С Тогда
		КонтекстФормы.Вставить("СтруктураДанныхЗагрузки", Элемент.СтруктураДанныхЗагрузки);
	КонецЕсли;
	
	ВременнаяСтрока = Элемент.ТаблицаТаблицДокументов.Добавить();
	КонтекстФормы.Вставить("ТаблицаНайденныхДокументов", ВременнаяСтрока.ТаблицаНайденныхДокументов.Выгрузить());
	Элемент.ТаблицаТаблицДокументов.Удалить(0);
	
	КонтекстФормы.Вставить("ЕстьОтборПоБанковскомуСчету", Элемент.ЕстьОтборПоБанковскомуСчету);
	КонтекстФормы.Вставить("ВыдаватьСообщенияОНеверныхРеквизитахИСекциях", Элемент.ВыдаватьСообщенияОНеверныхРеквизитахИСекциях);
	
	СтруктураОбъекта = Новый Структура;
	СтруктураОбъекта.Вставить("Организация", Элемент.Объект.Организация);
	СтруктураОбъекта.Вставить("БанковскийСчет", Элемент.Объект.БанковскийСчет);
	СтруктураОбъекта.Вставить("АвтоматическиПодставлятьДокументы", Элемент.Объект.АвтоматическиПодставлятьДокументы);
	СтруктураОбъекта.Вставить("АнализироватьИсториюВыбораЗначенийРеквизитов", Элемент.Объект.АнализироватьИсториюВыбораЗначенийРеквизитов);
	СтруктураОбъекта.Вставить("СтатьяДДСИсходящий", Элемент.Объект.СтатьяДДСИсходящий);
	СтруктураОбъекта.Вставить("СтатьяДДСВходящий", Элемент.Объект.СтатьяДДСВходящий);
	СтруктураОбъекта.Вставить("СпособЗачета", Элемент.Объект.СпособЗачета);
	
	КонтекстФормы.Вставить("Объект", СтруктураОбъекта);

	
	ФайлXML = Новый ЧтениеXML;
	
	ФайлXML.ОткрытьФайл(ФайлЗагрузки);
	
	Пока ФайлXML.Прочитать() Цикл
		ИмяТега = ВРег(СокрЛП(ФайлXML.Имя)); 
		
		Если ИмяТега = "ROW" И ФайлXML.ТипУзла = ТипУзлаXML.НачалоЭлемента Тогда
			Если НЕ ЗагрузитьСекциюДокументаXMLROW(ДокументыКИмпорту, ФайлXML, ИмпортЗагружаемые) Тогда
				Возврат;
			КонецЕсли;
		ИначеЕсли ИмяТега = "ROW" И ФайлXML.ТипУзла = ТипУзлаXML.КонецЭлемента Тогда
			Продолжить;
			
		ИначеЕсли ИмяТега="ROWDATA" И ФайлXML.ТипУзла = ТипУзлаXML.КонецЭлемента  Тогда
			Если НЕ ИмпортПризнакОбмена Тогда
				ТекстСообщения = НСтр("ru='В файле импорта отсутствует признак обмена ""_1CClientBankExchange""!';uk='У файлі імпорту відсутній признак обміну ""_1CClientBankExchange""!'");
				УправлениеНебольшойФирмойСервер.СообщитьОбОшибке(Элемент, ТекстСообщения);
				Возврат;
			КонецЕсли;
			
			НайденКонецФайла = Истина;
						
		ИначеЕсли ИмяТега="ROWDATA" И ФайлXML.ТипУзла = ТипУзлаXML.НачалоЭлемента  Тогда
			ИмпортПризнакОбмена = Истина;
			
		Иначе
			
			Если ФайлXML.ТипУзла = ТипУзлаXML.НачалоЭлемента Тогда
				ФайлXML.Прочитать();
				Значение = ФайлXML.Значение;
			КонецЕсли;
			
			Если ФайлXML.ТипУзла = ТипУзлаXML.Текст Тогда
				ФайлXML.Прочитать();
			КонецЕсли;
			
		КонецЕсли;
		
	КонецЦикла;
	
	Если НЕ НайденКонецФайла Тогда
		РасчетныеСчетаКИмпорту.Очистить();
		ДокументыКИмпорту.Очистить();
		ТекстСообщения = НСтр("ru='Файл загрузки не соответствует стандарту (не найдена секция КонецФайла)!';uk='Файл завантаження не відповідає стандарту (не знайдена секція КонецФайла)!'");
		УправлениеНебольшойФирмойСервер.СообщитьОбОшибке(Элемент, ТекстСообщения);
	КонецЕсли;
	
	НомерСтроки = 0;
	
	КоличествоНеНайденныхКонтрагентов = 0;
	КоличествоНеНайденныхРСчетов = 0;
	
	ПараметрыВыделенияКолонок = Новый Структура("ВыделитьКолонкуДокумент, ВыделитьКолонкуСуммаСписано, ВыделитьКолонкуСуммаПоступило, 
	|ВыделитьКолонкуКонтрагент, ВыделитьКолонкуДоговор, ВыделитьКолонкуРСКонтрагента, ВыделитьКолонкуВидОперации", 
	Ложь, Ложь, Ложь, Ложь, Ложь, Ложь, Ложь);
	
	Для каждого СтрокаДокумента Из ДокументыКИмпорту Цикл
		Если (СтрокаДокумента.ПлательщикСчет = Элемент.Объект.БанковскийСчет.НомерСчета
			ИЛИ СтрокаДокумента.ПолучательСчет  = Элемент.Объект.БанковскийСчет.НомерСчета) 
			И ЗначениеЗаполнено(Элемент.Объект.БанковскийСчет.ВалютаДенежныхСредств)
			Тогда
			
			Элемент.БанковскийСчетНомер = Элемент.Объект.БанковскийСчет.НомерСчета;
			Элемент.БанковскийСчетВалюта = Элемент.Объект.БанковскийСчет.ВалютаДенежныхСредств;
			
			Обработки.СМП_КлиентБанк.РаспознатьДанныеВСтрокеДокумента(СтрокаДокумента, Неопределено,ПараметрыВыделенияКолонок, Элемент.Объект, ТаблицаТаблицДокументов, КонтекстФормы, Элемент.ПослеЗагрузкиВыписокВ1С);
			НомерСтроки = НомерСтроки + 1;
			СтрокаДокумента.НомерСтроки = НомерСтроки;
			
			Для каждого КолонкаИмпорта из ДокументыКИмпорту.Колонки Цикл
				Обработки.СМП_КлиентБанк.ПроверитьНаПустоеЗначениеИмпорта(СтрокаДокумента, КолонкаИмпорта.Имя, КолонкаИмпорта.Заголовок, ИмпортНеПустые);
			КонецЦикла;
			
			Если ТипЗнч(СтрокаДокумента.Контрагент)=Тип("Строка") ИЛИ
				ТипЗнч(СтрокаДокумента.СчетКонтрагента)=Тип("Строка") ИЛИ
				ТипЗнч(СтрокаДокумента.Договор)=Тип("Строка") Тогда
				
				Обработки.СМП_КлиентБанк.СписокНенайденных(СтрокаДокумента, Элемент.Объект.БанковскийСчет, ТаблицаКонтрагентов, КоличествоНеНайденныхКонтрагентов, КоличествоНеНайденныхРСчетов);
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
	
	Элемент.Объект.Загрузка.Очистить();
	Элемент.Объект.Загрузка.Загрузить(ДокументыКИмпорту);
	
	Элемент.Объект.ИмпортРасчетныеСчета.Очистить();
	Элемент.Объект.ИмпортРасчетныеСчета.Загрузить(РасчетныеСчетаКИмпорту);
	
КонецПроцедуры

Функция ЗагрузитьСекциюДокументаXMLROW(ДокументыДляИмпорта, ФайлXML, ИмпортЗагружаемые)
	
	НоваяСтрокаДокументов = ДокументыДляИмпорта.Добавить();
	НоваяСтрокаДокументов.Номер				= ФайлXML.ПолучитьАтрибут("DOCUMENTNO");
	НоваяСтрокаДокументов.Дата				= Сред(ФайлXML.ПолучитьАтрибут("DOCUMENTDATE"), 7, 2) + "." + Сред(ФайлXML.ПолучитьАтрибут("DOCUMENTDATE"), 5, 2) + "." + Сред(ФайлXML.ПолучитьАтрибут("DOCUMENTDATE"), 1, 4) + " " + Сред(ФайлXML.ПолучитьАтрибут("BOOKEDDATE"), 10, 8) ;
	НоваяСтрокаДокументов.СуммаДокумента	= Число(ФайлXML.ПолучитьАтрибут("SUMMA")) / 100;
	НоваяСтрокаДокументов.Сумма				= СтрЗаменить(Формат(НоваяСтрокаДокументов.СуммаДокумента, "ЧРГ=&"), "&", "");
	
	Если ФайлXML.ПолучитьАтрибут("OPERATIONID") = "0" Тогда // исходящий
		
		ВидДокумента	= "ПлатежноеПоручение";
		НоваяСтрокаДокументов.СуммаПоступило	= 0;
		НоваяСтрокаДокументов.ДатаСписано 		= НоваяСтрокаДокументов.Дата;
		НоваяСтрокаДокументов.СуммаСписано		= НоваяСтрокаДокументов.СуммаДокумента;
		НоваяСтрокаДокументов.ПлательщикСчет	= СокрЛП(Формат(ФайлXML.ПолучитьАтрибут("IBAN"),"ЧГ=0"));
		НоваяСтрокаДокументов.ПлательщикКПП		= СокрЛП(Формат(ФайлXML.ПолучитьАтрибут("IDENTIFYCODE"),"ЧГ=0"));
		НоваяСтрокаДокументов.ПлательщикБИК		= СокрЛП(Формат(ФайлXML.ПолучитьАтрибут("BANKID"),"ЧГ=0"));
		НоваяСтрокаДокументов.Получатель		= СокрЛП(Формат(ФайлXML.ПолучитьАтрибут("CORRCONTRAGENTSNAME"),"ЧГ=0"));
		НоваяСтрокаДокументов.ПолучательСчет	= СокрЛП(Формат(ФайлXML.ПолучитьАтрибут("CORRIBAN"),"ЧГ=0"));
		НоваяСтрокаДокументов.ПолучательКПП		= СокрЛП(Формат(ФайлXML.ПолучитьАтрибут("CORRIDENTIFYCODE"),"ЧГ=0"));
		НоваяСтрокаДокументов.ПолучательБИК		= СокрЛП(Формат(ФайлXML.ПолучитьАтрибут("CORRBANKID"),"ЧГ=0"));
		НоваяСтрокаДокументов.ПолучательБанк1	= СокрЛП(Формат(ФайлXML.ПолучитьАтрибут("CORRBANKNAME"),"ЧГ=0"));
	Иначе
		ВидДокумента	= "ПлатежноеТребование";
		НоваяСтрокаДокументов.СуммаПоступило	= НоваяСтрокаДокументов.СуммаДокумента;
		НоваяСтрокаДокументов.ДатаПоступило 	= НоваяСтрокаДокументов.Дата;
		НоваяСтрокаДокументов.СуммаСписано		= 0;
		НоваяСтрокаДокументов.ПолучательСчет	= СокрЛП(Формат(ФайлXML.ПолучитьАтрибут("IBAN"),"ЧГ=0"));
		НоваяСтрокаДокументов.ПолучательКПП		= СокрЛП(Формат(ФайлXML.ПолучитьАтрибут("IDENTIFYCODE"),"ЧГ=0"));
		НоваяСтрокаДокументов.ПолучательБИК		= СокрЛП(Формат(ФайлXML.ПолучитьАтрибут("BANKID"),"ЧГ=0"));
		НоваяСтрокаДокументов.Плательщик		= СокрЛП(Формат(ФайлXML.ПолучитьАтрибут("CORRCONTRAGENTSNAME"),"ЧГ=0"));
		НоваяСтрокаДокументов.ПлательщикСчет	= СокрЛП(Формат(ФайлXML.ПолучитьАтрибут("CORRIBAN"),"ЧГ=0"));
		НоваяСтрокаДокументов.ПлательщикКПП		= СокрЛП(Формат(ФайлXML.ПолучитьАтрибут("CORRIDENTIFYCODE"),"ЧГ=0"));
		НоваяСтрокаДокументов.ПлательщикБИК		= СокрЛП(Формат(ФайлXML.ПолучитьАтрибут("CORRBANKID"),"ЧГ=0"));
		НоваяСтрокаДокументов.ПлательщикБанк1	= СокрЛП(Формат(ФайлXML.ПолучитьАтрибут("CORRBANKNAME"),"ЧГ=0"));
	КонецЕсли;
	
	НоваяСтрокаДокументов.КодВалюты				= ФайлXML.ПолучитьАтрибут("CURRENCYID");
	НоваяСтрокаДокументов.НазначениеПлатежа		= СтрЗаменить(ФайлXML.ПолучитьАтрибут("PLATPURPOSE"),Символы.ПС," ");
	
	Если ВидДокумента <> Неопределено Тогда
		НоваяСтрокаДокументов.Операция = ВидДокумента;
		
	Иначе // по умолчанию: "Платежное поручение"
		
		ВидДокумента = "ПлатежноеПоручение";
		НоваяСтрокаДокументов.Операция = ВидДокумента;
		
	КонецЕсли;
	
	Возврат Истина;
	
КонецФункции

Функция ФорматФайла() Экспорт
	Возврат "xml";
КонецФункции