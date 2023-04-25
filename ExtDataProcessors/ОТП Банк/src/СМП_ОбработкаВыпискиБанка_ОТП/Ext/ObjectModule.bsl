﻿
Функция СведенияОВнешнейОбработке() Экспорт
	
	ПараметрыРегистрации = ДополнительныеОтчетыИОбработки.СведенияОВнешнейОбработке();
	
	ПараметрыРегистрации.Вид = ДополнительныеОтчетыИОбработкиКлиентСервер.ВидОбработкиДополнительнаяОбработка();
	ПараметрыРегистрации.Наименование = НСтр("ru='Обработка выписки банка ОТП';uk='Обробка виписки банка ОТП'");
	ПараметрыРегистрации.Информация = НСтр("ru='Обработка формата загрузки данных украинского банка ОТП';uk='Обробка формату завантаження даних українського банка ОТП'");
	ПараметрыРегистрации.Версия = "1.2";
	ПараметрыРегистрации.БезопасныйРежим = Ложь;
	
	Возврат ПараметрыРегистрации;
	
КонецФункции

// Обработчик чтения формата для конфигурации BASSmallBusiness
Процедура Загрузить_УНФ(Элемент, ФайлЗагрузки, ТаблицаТаблицДокументов, ТаблицаКонтрагентов) Экспорт
	
	Элемент.ТаблицаКонтрагентов.ПолучитьЭлементы().Очистить();
	
	// Подготавливаем структуры обработки данных.
	ДокументыКИмпорту = Элемент.Объект.Загрузка.Выгрузить();
	ДокументыКИмпорту.Колонки.Добавить("КодНазПлатежа", Новый ОписаниеТипов("Строка",, Новый КвалификаторыСтроки(1)));

	ИмпортЗагружаемые = Обработки.КлиентБанк.СформироватьСоответствиеЗагружаемых();
	ИмпортНеПустые = Неопределено;
	ИмпортНеПустыеПлатежноеПоручение = Неопределено;
	ИмпортНеПустыеПлатежноеПоручениеБюджет = Неопределено;
	РасчетныеСчетаКИмпорту = Элемент.Объект.ИмпортРасчетныеСчета.Выгрузить();
	
	Обработки.КлиентБанк.СформироватьСоответствияНеПустыхПриИмпорте(
	ИмпортНеПустые,
	ИмпортНеПустыеПлатежноеПоручение,
	ИмпортНеПустыеПлатежноеПоручениеБюджет
	);
	ТегиРасчетногоСчета = Обработки.КлиентБанк.СоздатьСоответствиеИзСтроки(
	ВРег("ДатаНачала,ДатаКонца,РасчСчетОрг,НачальныйОстаток,ВсегоПоступило,ВсегоСписано,КонечныйОстаток,КонецРасчСчет")
	);
	ТегиЗаголовка = Обработки.КлиентБанк.СоздатьСоответствиеИзСтроки(
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
	
	ФайлTXT	= Новый ТекстовыйДокумент;
	ФайлTXT.Прочитать(ФайлЗагрузки, КодировкаТекста.ANSI); //Windows
	
	Результат = Новый Массив;
	
	Разделитель = ";";
	
	Если НЕ ФайлTXT.КоличествоСтрок() Тогда 
		Возврат;
	КонецЕсли;
	
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
	
	Для НомерСтроки = 1 По ФайлTXT.КоличествоСтрок() Цикл
		
		Результат.Очистить();
		
		ТекСтрока = ФайлTXT.ПолучитьСтроку(НомерСтроки);		
			
		ЗаполнитьСтроку(ДокументыКИмпорту, ТекСтрока, ИмпортЗагружаемые); 		
		
	КонецЦикла;
	
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
			
			Обработки.КлиентБанк.РаспознатьДанныеВСтрокеДокумента(СтрокаДокумента, Неопределено,ПараметрыВыделенияКолонок, Элемент.Объект, ТаблицаТаблицДокументов, КонтекстФормы, Элемент.ПослеЗагрузкиВыписокВ1С);
			НомерСтроки = НомерСтроки + 1;
			СтрокаДокумента.НомерСтроки = НомерСтроки;
			
			Для каждого КолонкаИмпорта из ДокументыКИмпорту.Колонки Цикл
				Обработки.КлиентБанк.ПроверитьНаПустоеЗначениеИмпорта(СтрокаДокумента, КолонкаИмпорта.Имя, КолонкаИмпорта.Заголовок, ИмпортНеПустые);
			КонецЦикла;
			
			Если ТипЗнч(СтрокаДокумента.Контрагент)=Тип("Строка") ИЛИ
				ТипЗнч(СтрокаДокумента.СчетКонтрагента)=Тип("Строка") ИЛИ
				ТипЗнч(СтрокаДокумента.Договор)=Тип("Строка") Тогда
				
				Обработки.КлиентБанк.СписокНенайденных(СтрокаДокумента, Элемент.Объект.БанковскийСчет, ТаблицаКонтрагентов, КоличествоНеНайденныхКонтрагентов, КоличествоНеНайденныхРСчетов);
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

Функция ЗаполнитьСтроку(ДокументыДляИмпорта, СтрокаФайла, ИмпортЗагружаемые)
	
	НоваяСтрокаДокументов = ДокументыДляИмпорта.Добавить();
	
	
	НоваяСтрокаДокументов.Номер				= СокрЛП(СокрЛП(Сред(СтрокаФайла,132,11)));
	НоваяСтрокаДокументов.Дата				= Сред(СтрокаФайла, 1190, 2) + "." + Сред(СтрокаФайла, 1188, 2) + ".20" + Сред(СтрокаФайла, 1186, 2);
	НоваяСтрокаДокументов.СуммаДокумента	= Число(Сред(СтрокаФайла, 117, 16))/100;
	НоваяСтрокаДокументов.Сумма				= СтрЗаменить(Формат(НоваяСтрокаДокументов.СуммаДокумента, "ЧРГ=&"), "&", "");
	
	Если СокрЛП(Сред(СтрокаФайла,115,1)) = "1" Тогда // исходящий
		
		ВидДокумента	= "ПЛАТЕЖНОЕПОРУЧЕНИЕ";
		НоваяСтрокаДокументов.СуммаПоступило	= НоваяСтрокаДокументов.СуммаДокумента;
		НоваяСтрокаДокументов.СуммаСписано		= 0;
	Иначе
		ВидДокумента	= "ПЛАТЕЖНОЕТРЕБОВАНИЕ";
		НоваяСтрокаДокументов.СуммаПоступило	= 0;
		НоваяСтрокаДокументов.СуммаСписано		= НоваяСтрокаДокументов.СуммаДокумента;
	КонецЕсли;
	НоваяСтрокаДокументов.ДатаПоступило 	= Сред(СтрокаФайла, 1190, 2) + "." + Сред(СтрокаФайла, 1188, 2) + ".20" + Сред(СтрокаФайла, 1186, 2);
	НоваяСтрокаДокументов.ДатаСписано 		= Сред(СтрокаФайла, 1190, 2) + "." + Сред(СтрокаФайла, 1188, 2) + ".20" + Сред(СтрокаФайла, 1186, 2);
	НоваяСтрокаДокументов.Плательщик		= СокрЛП(Сред(СтрокаФайла, 185, 138));
	НоваяСтрокаДокументов.ПлательщикСчет	= СокрЛП(Сред(СтрокаФайла, 29, 29));
	НоваяСтрокаДокументов.ПлательщикКПП		= СокрЛП(Сред(СтрокаФайла, 976, 14));
	НоваяСтрокаДокументов.ПлательщикБИК		= СокрЛП(Сред(СтрокаФайла, 0, 10)) ;
	НоваяСтрокаДокументов.Получатель		= СокрЛП(Сред(СтрокаФайла, 324, 138));
	НоваяСтрокаДокументов.ПолучательСчет	= СокрЛП(Сред(СтрокаФайла, 86, 29));
	НоваяСтрокаДокументов.ПолучательКПП		= СокрЛП(Сред(СтрокаФайла, 1005, 14));
	НоваяСтрокаДокументов.ПолучательБИК		= СокрЛП(Сред(СтрокаФайла, 58, 9));
	
	НоваяСтрокаДокументов.НазначениеПлатежа		= Сред(СтрокаФайла, 464, 500);
	
	
	
	Если ВидДокумента <> Неопределено Тогда
		НоваяСтрокаДокументов.Операция = ВидДокумента;
		
	Иначе // по умолчанию: "Платежное поручение"
		
		ВидДокумента = "ПЛАТЕЖНОЕТРЕБОВАНИЕ";
		НоваяСтрокаДокументов.Операция = ВидДокумента;
		
	КонецЕсли;	
	
	Возврат Истина;
	
КонецФункции

Функция ФорматФайла() Экспорт
	Возврат "txt;*.dat";
КонецФункции