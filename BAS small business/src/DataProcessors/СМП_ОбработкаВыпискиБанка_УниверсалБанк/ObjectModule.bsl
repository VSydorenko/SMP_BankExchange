
Функция СведенияОВнешнейОбработке() Экспорт
	
	ПараметрыРегистрации = ДополнительныеОтчетыИОбработки.СведенияОВнешнейОбработке();
	
	ПараметрыРегистрации.Вид = ДополнительныеОтчетыИОбработкиКлиентСервер.ВидОбработкиДополнительнаяОбработка();
	ПараметрыРегистрации.Наименование = НСтр("ru='Обработка выписки банка Универсал Банк';uk='Обробка виписки банка Універсал Банк'");
	ПараметрыРегистрации.Информация = НСтр("ru='Обработка формата загрузки данных украинского банка Универсал Банк';uk='Обробка формату завантаження даних українського банка Універсал Банк'");
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
	ИмпортНеПустыеПлатежноеПоручениеБюджет);
	
	ТегиРасчетногоСчета = Обработки.СМП_КлиентБанк.СоздатьСоответствиеИзСтроки(
	ВРег("ДатаНачала,ДатаКонца,РасчСчетОрг,НачальныйОстаток,ВсегоПоступило,ВсегоСписано,КонечныйОстаток,КонецРасчСчет"));
	
	ТегиЗаголовка = Обработки.СМП_КлиентБанк.СоздатьСоответствиеИзСтроки(
	ВРег("ВерсияФормата,Кодировка,Отправитель,Получатель,ДатаСоздания,ВремяСоздания,ДатаНачала,ДатаКонца"));
	
	СтруктураЗаголовок = Новый Структура(
	ВРег("ВерсияФормата,Кодировка,Отправитель,Получатель,ДатаСоздания,ВремяСоздания,ДатаНачала,ДатаКонца"));
	
	Элемент.ИмпортЗаголовок = СтруктураЗаголовок;
	ИмпортПризнакОбмена = Ложь;
	НайденКонецФайла = Ложь;
	ИмпортВидыДокументов = Новый Массив;
	РасчетныеСчетаКИмпорту.Очистить();
	ДокументыКИмпорту.Очистить();
	
	ФайлTXT = Новый ТекстовыйДокумент;
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
	
	Для НомерСтроки = 2 По ФайлTXT.КоличествоСтрок() Цикл
		
		Результат.Очистить();
		
		ТекСтрока = ФайлTXT.ПолучитьСтроку(НомерСтроки);
		
		Строки = СтрЗаменить(ТекСтрока, Разделитель, Символы.ПС);
		Строка = "";
		Продолжение = Ложь;
		
		Для Индекс = 1 По СтрЧислоСтрок(Строки) Цикл
			
			Если Продолжение тогда
				Строка = Строка + СтрПолучитьСтроку(Строки, Индекс);
			Иначе
				Строка = СтрПолучитьСтроку(Строки, Индекс);
			КонецЕсли;
			
			Если Лев(СтрПолучитьСтроку(Строки, Индекс),1) = """" и Прав(СтрПолучитьСтроку(Строки, Индекс),1) <> """" тогда
				Продолжение = Истина;
			КонецЕсли;
			
			Если Продолжение и Прав(СтрПолучитьСтроку(Строки, Индекс),1) = """" Тогда
				Продолжение = Ложь;
			КонецЕсли;
			
			Если Не Продолжение Тогда
				Результат.Добавить(Строка);
			КонецЕсли;
			
		КонецЦикла;
		
		ЗаполнитьСтроку(ДокументыКИмпорту, Результат, ИмпортЗагружаемые); 
		
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

// Обработчик чтения формата для конфигурации BASБухгалтерия
Функция Загрузить_Бух(ДокументыДляИмпорта,
						СтруктураДанныхИмпорта,
						ВыводитьСообщения,
						НомерСчета, 
						КодВалютыБанковскогоСчета, 
						Кодировка,
						Организация,
						Импорт_Заголовок,
						Импорт_РасчетныеСчета,
						ИмяВременногоФайла,
						СоздаватьНенайденныеЭлементы = Истина,
						СтекОповещений = Неопределено) Экспорт
	
	ДокументыКИмпорту = СоздатьТаблицуКИмпорту();
	
	РасчетныеСчетаКИмпорту = Импорт_РасчетныеСчета;
	
	Импорт_ВидыДокументов = Новый Массив;
	ДокументыДляИмпорта.Очистить();
	
	РасчетныеСчетаКИмпорту.Очистить();
	ДокументыКИмпорту.Очистить();
	
	ФайлTXT	= Новый ТекстовыйДокумент;
	ФайлTXT.Прочитать(ИмяВременногоФайла, КодировкаТекста.ANSI); //Windows
	
	Результат = Новый Массив;
	
	Разделитель = ";";
	
	Если НЕ ФайлTXT.КоличествоСтрок() Тогда 
		Возврат Ложь;
	КонецЕсли;
		
	Для НомерСтроки = 2 По ФайлTXT.КоличествоСтрок() Цикл
		
		Результат.Очистить();
		
		ТекСтрока = ФайлTXT.ПолучитьСтроку(НомерСтроки);
		
		Строки = СтрЗаменить(ТекСтрока, Разделитель, Символы.ПС);
		Строка = "";
		Продолжение = Ложь;
		
		Для Индекс = 1 По СтрЧислоСтрок(Строки) Цикл
			
			Если Продолжение тогда
				Строка = Строка + СтрПолучитьСтроку(Строки, Индекс);
			Иначе
				Строка = СтрПолучитьСтроку(Строки, Индекс);
			КонецЕсли;
			
			Если Лев(СтрПолучитьСтроку(Строки, Индекс),1) = """" и Прав(СтрПолучитьСтроку(Строки, Индекс),1) <> """" тогда
				Продолжение = Истина;
			КонецЕсли;
			
			Если Продолжение и Прав(СтрПолучитьСтроку(Строки, Индекс),1) = """" Тогда
				Продолжение = Ложь;
			КонецЕсли;
			
			Если Не Продолжение Тогда
				Результат.Добавить(Строка);
			КонецЕсли;
			
		КонецЦикла;
		
		ЗаполнитьСтроку(ДокументыКИмпорту, Результат, Неопределено); 
		
	КонецЦикла;
	
	Импорт_Заголовок = Новый Структура;
	Импорт_Заголовок.Вставить("ДатаНачала", ТекущаяДата());
	Импорт_Заголовок.Вставить("ДатаКонца", Дата("20000101"));
	
	Для каждого СтрокаДокументов из ДокументыКИмпорту Цикл
		
		Если (СтрокаДокументов.ПлательщикСчет <> "" И СтрокаДокументов.ПлательщикСчет <> НомерСчета) и 
			(СтрокаДокументов.ПолучательСчет <> "" И СтрокаДокументов.ПолучательСчет <> НомерСчета) Тогда
			Продолжить;
		КонецЕсли;
		
		НоваяСтрокаДокументов = ДокументыДляИмпорта.Добавить();
		ЗаполнитьЗначенияСвойств(НоваяСтрокаДокументов, СтрокаДокументов);
		ДатаВФормате = Формат(Дата(СтрокаДокументов.Дата), "ДФ=гг") + "-" + Формат(Дата(СтрокаДокументов.Дата), "ДФ=ММ") +
							"-" + Формат(Дата(СтрокаДокументов.Дата), "ДФ=дд");
		
		НоваяСтрокаДокументов.ДокументИД 			= СтрокаДокументов.Номер;
		НоваяСтрокаДокументов.ПлательщикМФО 		= СтрокаДокументов.ПлательщикБИК;
		НоваяСтрокаДокументов.ПлательщикОКПО 		= СтрокаДокументов.ПлательщикКПП;
		НоваяСтрокаДокументов.ПлательщикБанк 		= СтрокаДокументов.ПлательщикБанк1;
		НоваяСтрокаДокументов.ПолучательМФО 		= СтрокаДокументов.ПолучательБИК;
		НоваяСтрокаДокументов.ПолучательОКПО 		= СтрокаДокументов.ПолучательКПП;
		НоваяСтрокаДокументов.ПолучательБанк 		= СтрокаДокументов.ПолучательБанк1;
		НоваяСтрокаДокументов.ДатаПоступило 		= ДатаВФормате;
		НоваяСтрокаДокументов.ДатаСписано 			= ДатаВФормате;
		НоваяСтрокаДокументов.ДатаОтсылкиДок 		= ДатаВФормате;
		НоваяСтрокаДокументов.ДатаДок 				= ДатаВФормате;
		НоваяСтрокаДокументов.Дата 					= ДатаВФормате;
		НоваяСтрокаДокументов.ДатаПроведенияБанком 	= СтрокаДокументов.ДатаПроведения;
		
		Импорт_ВидыДокументов.Добавить(СтрокаДокументов.Операция);
		Импорт_Заголовок.ДатаНачала 				= Мин(Импорт_Заголовок.ДатаНачала, СтрокаДокументов.Дата);
		Импорт_Заголовок.ДатаКонца 					= Макс(Импорт_Заголовок.ДатаКонца, КонецДня(СтрокаДокументов.Дата));
		
	КонецЦикла;
	
	Возврат Истина;
	
КонецФункции // РазобратьФайлИмпорта

// Обработчик выгрузки для конфигурации BASБухгалтерия
Функция Выгрузить_Бух(Параметры) Экспорт
	
	Файл = Новый ТекстовыйДокумент;
	СтрокаПробелов 	= "                                                                                                                                                                                                ";
	Файл.УстановитьТипФайла("windows-1251");
	
	Для Каждого Строка из Параметры.ПлатежныеДокументы Цикл
		
		Файл.ДобавитьСтроку("Content-Type=doc/ua_payment");
		Файл.ДобавитьСтроку("");
		Файл.ДобавитьСтроку("DATE_DOC="			+ Формат(Строка.Дата, "ДФ=дд.ММ.гггг"));
		Файл.ДобавитьСтроку("NUM_DOC="			+ Формат(Прав(Строка.Номер,10), "ЧЦ=10;ЧГ=0"));
		Файл.ДобавитьСтроку("AMOUNT="			+ Формат(Строка.СуммаДокумента, "ЧЦ=14;ЧДЦ=2;ЧРД=.;ЧГ=0"));
		
		Файл.ДобавитьСтроку("CLN_NAME="			+ Лев(Строка.Организация, 40));
		Файл.ДобавитьСтроку("CLN_OKPO="			+ Формат(Строка.ОКПОПолучателя, "ЧЦ=10;ЧГ=0"));
		Файл.ДобавитьСтроку("CLN_ACCOUNT="		+ Формат(Строка.ОрганизацияНомерСчета, "ЧЦ=14;ЧГ=0"));
		Файл.ДобавитьСтроку("CLN_BANK_NAME="	+ Лев(Строка.ОрганизацияБанк, 45));
		Файл.ДобавитьСтроку("CLN_BANK_MFO="		+ Формат(Строка.ОрганизацияМФОБанка, "ЧЦ=6;ЧГ=0"));
		
		Файл.ДобавитьСтроку("RCPT_NAME="		+ Лев(Строка.Контрагент, 40));
		Файл.ДобавитьСтроку("RCPT_OKPO="		+ Формат(Строка.ОКПОПлательщика, "ЧЦ=10;ЧГ=0"));
		Файл.ДобавитьСтроку("RCPT_ACCOUNT="		+ Формат(Строка.КонтрагентНомерСчета, "ЧЦ=14;ЧГ=0"));
		Файл.ДобавитьСтроку("RCPT_BANK_NAME="	+ Лев(Строка.КонтрагентБанк, 45));
		
		Файл.ДобавитьСтроку("RCPT_BANK_MFO="	+ Формат(Строка.КонтрагентМФОБанка, "ЧЦ=6;ЧГ=0"));
		
		Файл.ДобавитьСтроку("PAYMENT_DETAILS="	+ Лев(СтрЗаменить(УдалитьНедопустимыеСимволы(Строка.НазначениеПлатежа), Символ(160), Символ(32)), 160));
		Файл.ДобавитьСтроку("");
		
	КонецЦикла;
	
	ИмяФайла = ПолучитьИмяВременногоФайла(ФорматФайла());
	
	Файл.Записать(ИмяФайла, "windows-1251");
	
	Адрес = ПоместитьВоВременноеХранилище(Новый ДвоичныеДанные(ИмяФайла), Параметры.УникальныйИдентификатор);
	
	Возврат Адрес;
	
КонецФункции

Функция ЗаполнитьСтроку(ДокументыДляИмпорта, СтрокаФайла, ИмпортЗагружаемые)
	
	Если СокрЛП(СтрокаФайла[0]) = "" Тогда
		Возврат Истина;
	КонецЕсли;
	
	НоваяСтрокаДокументов = ДокументыДляИмпорта.Добавить();
	
	НоваяСтрокаДокументов.Номер				= СокрЛП(СтрокаФайла[11]);
	НоваяСтрокаДокументов.Дата				= Дата(Сред(СокрЛП(СтрокаФайла[4]), 1, 2) + "." + Сред(СокрЛП(СтрокаФайла[4]), 4, 2) + "." + Сред(СокрЛП(СтрокаФайла[4]), 7, 4) + " " + Сред(СокрЛП(СтрокаФайла[4]),12,5) + ":00");
	НоваяСтрокаДокументов.ДатаПроведения	= Дата(Сред(СокрЛП(СтрокаФайла[4]), 1, 2) + "." + Сред(СокрЛП(СтрокаФайла[4]), 4, 2) + "." + Сред(СокрЛП(СтрокаФайла[4]), 7, 4) + " " + Сред(СокрЛП(СтрокаФайла[4]),12,5) + ":00");
	
	СуммаДокументаСтрока = СтрЗаменить(СтрЗаменить(СокрЛП(СтрокаФайла[13]),".",",")," ","");
	
	Если СуммаДокументаСтрока = "" Тогда
		СуммаДокументаСтрока = СтрЗаменить(СтрЗаменить(СокрЛП(СтрокаФайла[14]),".",",")," ",""); 
	КонецЕсли;
	
	Попытка
		НоваяСтрокаДокументов.СуммаДокумента	= Число(СуммаДокументаСтрока);
	Исключение
		НоваяСтрокаДокументов.СуммаДокумента	= 0;
	КонецПопытки;
	
	НоваяСтрокаДокументов.Сумма				= СтрЗаменить(Формат(НоваяСтрокаДокументов.СуммаДокумента, "ЧРГ=&"), "&", "");
	Если СтрЗаменить(СтрЗаменить(СокрЛП(СтрокаФайла[14]),".",",")," ","") = "" Тогда // исходящий
		
		ВидДокумента							= "ПлатежноеПоручение";
		НоваяСтрокаДокументов.СуммаПоступило	= 0;
		НоваяСтрокаДокументов.ДатаСписано 		= НоваяСтрокаДокументов.Дата;
		НоваяСтрокаДокументов.СуммаСписано		= НоваяСтрокаДокументов.СуммаДокумента;
		НоваяСтрокаДокументов.ПлательщикСчет	= СокрЛП(СтрокаФайла[2]);
		НоваяСтрокаДокументов.ПлательщикКПП		= СокрЛП(СтрокаФайла[0]);
		НоваяСтрокаДокументов.ПлательщикБИК		= СокрЛП(СтрокаФайла[1]);
		НоваяСтрокаДокументов.Получатель		= СокрЛП(СтрокаФайла[10]);
		НоваяСтрокаДокументов.ПолучательСчет	= СокрЛП(СтрокаФайла[8]);
		НоваяСтрокаДокументов.ПолучательКПП		= СокрЛП(СтрокаФайла[9]);
		НоваяСтрокаДокументов.ПолучательБИК		= СокрЛП(СтрокаФайла[6]);
	Иначе
		ВидДокумента							= "ПлатежноеТребование";
		НоваяСтрокаДокументов.СуммаПоступило	= НоваяСтрокаДокументов.СуммаДокумента;
		НоваяСтрокаДокументов.ДатаПоступило 	= НоваяСтрокаДокументов.Дата;
		НоваяСтрокаДокументов.СуммаСписано		= 0;
		НоваяСтрокаДокументов.ПолучательСчет	= СокрЛП(СтрокаФайла[2]);
		НоваяСтрокаДокументов.ПолучательКПП		= СокрЛП(СтрокаФайла[0]);
		НоваяСтрокаДокументов.ПолучательБИК		= СокрЛП(СтрокаФайла[1]);
		НоваяСтрокаДокументов.Плательщик		= СокрЛП(СтрокаФайла[10]);
		НоваяСтрокаДокументов.ПлательщикСчет	= СокрЛП(СтрокаФайла[8]);
		НоваяСтрокаДокументов.ПлательщикКПП		= СокрЛП(СтрокаФайла[9]);
		НоваяСтрокаДокументов.ПлательщикБИК		= СокрЛП(СтрокаФайла[6]);
	КонецЕсли;
	
	НоваяСтрокаДокументов.КодВалюты				= СокрЛП(СтрокаФайла[3]);
	НоваяСтрокаДокументов.НазначениеПлатежа		= СокрЛП(СтрокаФайла[15]);
	
	Если ВидДокумента <> Неопределено Тогда
		НоваяСтрокаДокументов.Операция = ВидДокумента;
	Иначе // по умолчанию: "Платежное поручение"
		ВидДокумента = "ПлатежноеПоручение";
		НоваяСтрокаДокументов.Операция = ВидДокумента;
	КонецЕсли;
	
	Возврат Истина;
	
КонецФункции

Функция ФорматФайла() Экспорт
	Возврат "csv";
КонецФункции

Функция ФорматФайлаВыгрузки() Экспорт
	Возврат "txt";
КонецФункции

Функция СоздатьТаблицуКИмпорту();
	
	ОписаниеЧисло = Новый ОписаниеТипов("Число", Новый КвалификаторыЧисла(15, 2));
	ДокументыКИмпорту = Новый ТаблицаЗначений;
	ДокументыКИмпорту.Колонки.Добавить("СуммаПоступило", ОписаниеЧисло);
	ДокументыКИмпорту.Колонки.Добавить("ДатаСписано");
	ДокументыКИмпорту.Колонки.Добавить("СуммаСписано", ОписаниеЧисло);
	ДокументыКИмпорту.Колонки.Добавить("ПлательщикСчет");
	ДокументыКИмпорту.Колонки.Добавить("ПлательщикБИК");
	ДокументыКИмпорту.Колонки.Добавить("ПлательщикКПП");
	ДокументыКИмпорту.Колонки.Добавить("Получатель");
	ДокументыКИмпорту.Колонки.Добавить("ПолучательСчет");
	ДокументыКИмпорту.Колонки.Добавить("ПолучательКПП");
	ДокументыКИмпорту.Колонки.Добавить("ПолучательБИК");
	ДокументыКИмпорту.Колонки.Добавить("ПолучательБанк1");
	ДокументыКИмпорту.Колонки.Добавить("ДатаПоступило");
	ДокументыКИмпорту.Колонки.Добавить("Плательщик");
	ДокументыКИмпорту.Колонки.Добавить("ПлательщикБанк1");
	ДокументыКИмпорту.Колонки.Добавить("КодВалюты");
	ДокументыКИмпорту.Колонки.Добавить("НазначениеПлатежа");
	ДокументыКИмпорту.Колонки.Добавить("Номер");
	ДокументыКИмпорту.Колонки.Добавить("Дата");
	ДокументыКИмпорту.Колонки.Добавить("СуммаДокумента", ОписаниеЧисло);
	ДокументыКИмпорту.Колонки.Добавить("Сумма");
	ДокументыКИмпорту.Колонки.Добавить("Операция");
	ДокументыКИмпорту.Колонки.Добавить("ДатаПроведения");
	
	Возврат ДокументыКИмпорту;
	
КонецФункции

Функция УдалитьНедопустимыеСимволы(Стр)
	
	//Создаем переменную, в которую поместим все допустимые символы
	ДопустимыеСимволы = " абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯabcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,ІіЇїЄє;";
	Символ = СтрДлина(Стр);
	ДлинаДС = СтрДлина(ДопустимыеСимволы);
	//Обойдем каждый символ этой строки, начиная с конца
	Пока Символ>0 Цикл
		Найдено = Ложь;
		
		//Проверим, есть ли этот символ в перечне допустимых.
		//Здесь вместо цикла можно было бы использовать еще функцию Найти()
		Для ДопустимыйСимвол = 1 По ДлинаДС Цикл
			Если Сред(Стр,Символ, 1)=Сред(ДопустимыеСимволы, ДопустимыйСимвол, 1) Тогда
				Найдено = Истина;
				Прервать;
			КонецЕсли;
		КонецЦикла;
		
		//Если символ не найден, удаляем его.
		Если Не Найдено ТОгда
			Стр = СтрЗаменить(Стр, Сред(Стр,Символ, 1), "");
		КонецЕсли;
		Символ = Символ-1;
	КонецЦикла;
	
	Возврат Стр;

КонецФункции