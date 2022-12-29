
&НаСервере
&ИзменениеИКонтроль("ПриСозданииНаСервере")
Процедура СМП_ПриСозданииНаСервере(Отказ, СтандартнаяОбработка)

	ЗаполнитьЗначенияСвойств(Объект, Параметры);

	Объект.НачПериода = ОбщегоНазначенияБП.ПолучитьРабочуюДату();
	Объект.КонПериода = ОбщегоНазначенияБП.ПолучитьРабочуюДату();

	Если НЕ ЗначениеЗаполнено(Объект.Организация) Тогда
		Объект.Организация = БухгалтерскийУчетПереопределяемый.ПолучитьЗначениеПоУмолчанию("ОсновнаяОрганизация");
	КонецЕсли;

	Если НЕ ЗначениеЗаполнено(Объект.БанковскийСчет) Тогда
		Объект.БанковскийСчет = БухгалтерскийУчетПереопределяемый.ПолучитьБанковскийСчетПоУмолчанию(Объект.Организация);
	КонецЕсли;

	Если Параметры.Свойство("РежимПоУмолчанию") Тогда
		Элементы.ГруппаСтраницы.ТекущаяСтраница = Элементы[Параметры.РежимПоУмолчанию];
	КонецЕсли;

	ЗаполнитьВидыДокументов(ТаблицаДокументов);
	ВалютаРегламентированногоУчета = Константы.ВалютаРегламентированногоУчета.Получить();
	ИспользоватьСтатьиДДС          = Истина;

	#Удаление
	ЗагрузитьНастройкиДляБанковскогоСчета();
	#КонецУдаления

	Если Параметры.Свойство("ЭлектроннаяВыпискаБанка") Тогда
		ЭлектроннаяВыпискаБанка = Параметры.ЭлектроннаяВыпискаБанка;
	КонецЕсли;

	Если Элементы.ГруппаСтраницы.ТекущаяСтраница = Элементы.ГруппаВыгрузка Тогда
		ДокументыНаЭкспортОбновитьСервер(Объект.ВыгружатьПлатежноеПоручение, Объект.ВыгружатьПлатежноеТребование);
	КонецЕсли;

	#Вставка
	ЭлементОформления = УсловноеОформление.Элементы.Добавить();
	ЭлементОтбора = ЭлементОформления.Отбор.Элементы.Добавить(Тип("ЭлементОтбораКомпоновкиДанных"));
	ЭлементОтбора.ЛевоеЗначение = Новый ПолеКомпоновкиДанных("ДокументыКИмпорту.ДокументРасчетов");
	ЭлементОтбора.ВидСравнения = ВидСравненияКомпоновкиДанных.Равно;
	ЭлементОтбора.ПравоеЗначение = НСТр ("ru = 'Не предусмотрено'; uk = 'Не передбачено'");
	
	ЭлементОформления.Оформление.УстановитьЗначениеПараметра("ЦветТекста", WebЦвета.Серый);
	ПолеОформления = ЭлементОформления.Поля.Элементы.Добавить();
	ПолеОформления.Поле = Новый ПолеКомпоновкиДанных("ДокументыКИмпортуДокументРасчетов");
	ПолеОформления.Использование = Истина;
	#КонецВставки
	
	УправлениеФормойНаСервере();

	ОрганизацияЗаголовок = НСтр("ru='Организация:';uk='Організація:'");

КонецПроцедуры

&НаКлиенте
Процедура СМП_ПриОткрытииПеред(Отказ)
	ЗагрузитьНастройкиДляБанковскогоСчета();
КонецПроцедуры

&НаСервере
&ИзменениеИКонтроль("ЗаполнитьДокументыНаИмпорт")
Функция СМП_ЗаполнитьДокументыНаИмпорт(ИБФайловая, ВыводитьСообщения, ТребуетсяПовторноеЧтениеФайла)
	
	#Вставка
	ИскатьВСправочникеСоответствий = СМП_ЕстьЗаписиВСправочникеСоответствий();
	#КонецВставки
	
	ТаблицаКонтрагентов.ПолучитьЭлементы().Очистить();
	ДеревоКонтрагентов  = РеквизитФормыВЗначение("ТаблицаКонтрагентов");
	
	ДвоичныеДанныеФайла = ?(ТребуетсяПовторноеЧтениеФайла, ПолучитьИзВременногоХранилища(АдресФайла), Неопределено);
	
	СтекОповещений      = Новый Массив;
	СтруктураПараметров = Новый Структура(
		"ДокументыКИмпорту, СтруктураДанныхИмпорта, ВыводитьСообщения, БанковскийСчет, Кодировка,
		|Организация, НастройкаЗаполнения, ДеревоКонтрагентов, Импорт_Заголовок, Импорт_РасчетныеСчета,
		|ДвоичныеДанныеФайла, СоздаватьНенайденныеЭлементы,
		
		#Удаление
		|СтекОповещений, ТребуетсяПовторноеЧтениеФайла",
		#КонецУдаления
		
		#Вставка
		|СтекОповещений, ТребуетсяПовторноеЧтениеФайла, СМП_ОбработкаПротокола,ИскатьВСправочникеСоответствий",
		#КонецВставки
		
		ДокументыКИмпорту.Выгрузить(), ПолучитьСтруктуруДанныхИмпорта(), ВыводитьСообщения, Объект.БанковскийСчет, Объект.Кодировка,
		Объект.Организация, НастройкаЗаполнения.Выгрузить(), ДеревоКонтрагентов, Импорт_Заголовок, Импорт_РасчетныеСчета.Выгрузить(),
		ДвоичныеДанныеФайла, Объект.СоздаватьНенайденныеЭлементы,
		
		#Удаление
		СтекОповещений, ТребуетсяПовторноеЧтениеФайла);
		#КонецУдаления
		
		#Вставка
		СтекОповещений, ТребуетсяПовторноеЧтениеФайла, Объект.СМП_УчетнаяЗаписьБанка.ПодключаемаяОбработка,ИскатьВСправочникеСоответствий);
		#КонецВставки
	
	Если ИБФайловая Тогда
		АдресХранилища = ПоместитьВоВременноеХранилище(Неопределено, УникальныйИдентификатор);
		Обработки.КлиентБанк.ФоноваяЧтениеДокументовКИмпорту(СтруктураПараметров, АдресХранилища);
		Результат = Новый Структура("ЗаданиеВыполнено", Истина);
	Иначе
		НаименованиеЗадания = НСтр("ru='Чтение данных из файла импорта банка-клиента';uk='Читання даних з файлу імпорту банку-клієнта'");
		
		Результат = ДлительныеОперации.ЗапуститьВыполнениеВФоне(
			УникальныйИдентификатор,
			"Обработки.КлиентБанк.ФоноваяЧтениеДокументовКИмпорту",
			СтруктураПараметров,
			НаименованиеЗадания);
		
		АдресХранилища = Результат.АдресХранилища;
	КонецЕсли;
	
	Если Результат.ЗаданиеВыполнено Тогда
		Результат.Вставить("СтруктураДанныхКлиента", ЗагрузитьПодготовленныеДанные(ТребуетсяПовторноеЧтениеФайла));
	КонецЕсли;   
	
	#Вставка
	ДокументыКИмпорту.Сортировать("Дата");
	#КонецВставки
	
	Возврат Результат;
	
КонецФункции

&НаКлиенте
&ИзменениеИКонтроль("ВыборФайлаДляВыгрузкиИЗагрузки")
Процедура СМП_ВыборФайлаДляВыгрузкиИЗагрузки(Элемент, Режим)
	
	ДиалогВыбора = Новый ДиалогВыбораФайла(РежимДиалогаВыбораФайла.Открытие);
	
	#Удаление
	ДиалогВыбора.Фильтр                      = НСтр("ru='XML файл';uk='XML файл'") + " (*.xml)|*.xml";   
	#КонецУдаления
	
	#Вставка
	Если Режим = НСтр("ru='загрузки';uk='завантаження'") Тогда
		ДиалогВыбора.Фильтр                      = НСтр("ru='" + Объект.СМП_РасширениеФайлаИмпорта + " файл';uk='" + Объект.СМП_РасширениеФайлаИмпорта + " файл'") + " (*." + Объект.СМП_РасширениеФайлаИмпорта + ")|*." + Объект.СМП_РасширениеФайлаИмпорта;
	Иначе
		ДиалогВыбора.Фильтр                      = НСтр("ru='" + Объект.СМП_РасширениеФайлаЭкспорта + " файл';uk='" + Объект.СМП_РасширениеФайлаЭкспорта + " файл'") + " (*." + Объект.СМП_РасширениеФайлаЭкспорта + ")|*." + Объект.СМП_РасширениеФайлаЭкспорта;
	КонецЕсли;
	#КонецВставки
	
	ДиалогВыбора.Заголовок                   = СтроковыеФункцииКлиентСервер.ПодставитьПараметрыВСтроку(
		НСтр("ru='Выберите файл для %1 данных из клиента банка';uk='Виберіть файл для %1 даних з клієнта банку'"), Режим);
	ДиалогВыбора.ПредварительныйПросмотр     = Ложь;
	
	#Удаление
	ДиалогВыбора.Расширение                  = "xml";
	#КонецУдаления
	
	#Вставка
	Если Режим = НСтр("ru='загрузки';uk='завантаження'") Тогда
		ДиалогВыбора.Расширение                  = ?(СокрЛП(Объект.СМП_РасширениеФайлаИмпорта) = "", "xml", СокрЛП(Объект.СМП_РасширениеФайлаИмпорта));
	Иначе
		ДиалогВыбора.Расширение                  = ?(СокрЛП(Объект.СМП_РасширениеФайлаЭкспорта) = "", "xml", СокрЛП(Объект.СМП_РасширениеФайлаЭкспорта));
	КонецЕсли;
	#КонецВставки
	
	ДиалогВыбора.ИндексФильтра               = 0; 
	
	#Удаление
	ДиалогВыбора.ПолноеИмяФайла              = ?(ПустаяСтрока(Элемент.ТекстРедактирования),
		?(Режим = НСтр("ru='выгрузки';uk='вивантаження'"), "1C_to_CB.xml", "CB_to_1C.xml"), Элемент.ТекстРедактирования);
	#КонецУдаления
	
	#Вставка
	Если Режим = НСтр("ru='загрузки';uk='завантаження'") Тогда
	ДиалогВыбора.ПолноеИмяФайла              = ?(ПустаяСтрока(Элемент.ТекстРедактирования),
		?(Режим = НСтр("ru='выгрузки';uk='вивантаження'"), "1C_to_CB." + ?(СокрЛП(Объект.СМП_РасширениеФайлаИмпорта) = "", "xml", СокрЛП(Объект.СМП_РасширениеФайлаИмпорта)), "CB_to_1C." + ?(СокрЛП(Объект.СМП_РасширениеФайлаИмпорта) = "", "xml", СокрЛП(Объект.СМП_РасширениеФайлаИмпорта))), Элемент.ТекстРедактирования);
	Иначе
	ДиалогВыбора.ПолноеИмяФайла              = ?(ПустаяСтрока(Элемент.ТекстРедактирования),
		?(Режим = НСтр("ru='выгрузки';uk='вивантаження'"), "1C_to_CB." + ?(СокрЛП(Объект.СМП_РасширениеФайлаЭкспорта) = "", "xml", СокрЛП(Объект.СМП_РасширениеФайлаЭкспорта)), "CB_to_1C." + ?(СокрЛП(Объект.СМП_РасширениеФайлаЭкспорта) = "", "xml", СокрЛП(Объект.СМП_РасширениеФайлаЭкспорта))), Элемент.ТекстРедактирования);
	КонецЕсли;
	#КонецВставки
	
	ДиалогВыбора.ПроверятьСуществованиеФайла = Ложь;
	
	Если ДиалогВыбора.Выбрать() Тогда
		Если Режим = НСтр("ru='загрузки';uk='завантаження'") Тогда
			Объект.ФайлЗагрузки = ДиалогВыбора.ПолноеИмяФайла;
			
			Оповестить("ВыбранФайлЗагрузки");
		Иначе
			Объект.ФайлВыгрузки = ДиалогВыбора.ПолноеИмяФайла;
		КонецЕсли;
	КонецЕсли;
	
	УправлениеФормой();
	
КонецПроцедуры

&НаКлиенте
&ИзменениеИКонтроль("ВыполнитьНастройкуКлиентБанка")
Процедура СМП_ВыполнитьНастройкуКлиентБанка()
	
	Если НЕ ЗначениеЗаполнено(Объект.Организация) Тогда
		ТекстСообщения = ОбщегоНазначенияБПКлиентСервер.ПолучитьТекстСообщения("Поле", "Заполнение", "Организация");
		ОбщегоНазначенияКлиентСервер.СообщитьПользователю(ТекстСообщения,, "Объект.Организация");
		Возврат;
	КонецЕсли;
	
	ПараметрыФормы = Новый Структура;
	
	#Удаление
	ПараметрыФормы.Вставить("Организация",                                    Объект.Организация);
	ПараметрыФормы.Вставить("БанковскийСчет",                                 Объект.БанковскийСчет);
	ПараметрыФормы.Вставить("ГруппаДляНовыхКонтрагентов",                     ГруппаДляНовыхКонтрагентов);
	ПараметрыФормы.Вставить("СтатьяДДССписаниеСРасчетногоСчета",              СтатьяДДССписаниеСРасчетногоСчета);
	ПараметрыФормы.Вставить("СтатьяДДСПоступлениеНаРасчетныйСчет",            СтатьяДДСПоступлениеНаРасчетныйСчет);
	ПараметрыФормы.Вставить("ПроводитьПриЗагрузкеСписаниеСРасчетногоСчета",   ПроводитьПриЗагрузкеСписаниеСРасчетногоСчета);
	ПараметрыФормы.Вставить("ПроводитьПриЗагрузкеПоступлениеНаРасчетныйСчет", ПроводитьПриЗагрузкеПоступлениеНаРасчетныйСчет);
	#КонецУдаления
	
	#Вставка
	Если ЗначениеЗаполнено(Объект.СМП_УчетнаяЗаписьБанка) Тогда
		СсылкаУЗБ = Объект.СМП_УчетнаяЗаписьБанка;
		ПараметрыФормы.Вставить("Ключ", СсылкаУЗБ);
	Иначе
		ПараметрыФормы.Вставить("Организация", Объект.Организация);
		ПараметрыФормы.Вставить("БанковскийСчет", Объект.БанковскийСчет);
	КонецЕсли;
	#КонецВставки
	
	ОповещениеОЗакрытии = Новый ОписаниеОповещения("ВыполнитьНастройкуКлиентБанкаЗавершение", ЭтотОбъект);
	
	#Удаление
	ОткрытьФорму("Обработка.КлиентБанк.Форма.ФормаНастройкиЗаполнения", ПараметрыФормы, ЭтотОбъект,,,, ОповещениеОЗакрытии);
	#КонецУдаления
	
	#Вставка
	ОткрытьФорму("Справочник.СМП_УчетныеЗаписиБанков.ФормаОбъекта", ПараметрыФормы, ЭтотОбъект,,,, ОповещениеОЗакрытии);
	#КонецВставки
	
КонецПроцедуры

&НаСервере
&ИзменениеИКонтроль("ЗагрузитьНастройкиДляБанковскогоСчета")
Процедура СМП_ЗагрузитьНастройкиДляБанковскогоСчета()
	
	НастройкаВыполнена     = Ложь;
	
	Если ЗначениеЗаполнено(Объект.Организация)
		И ЗначениеЗаполнено(Объект.БанковскийСчет) Тогда
		
		Настройки = Обработки.КлиентБанк.ПолучитьНастройкиПрограммыКлиентаБанка(Объект.Организация, Объект.БанковскийСчет);
		
		Объект.Программа                                = Настройки.Программа;
		
		#Вставка
		Объект.СМП_УчетнаяЗаписьБанка					= Настройки.СМП_УчетнаяЗаписьБанка;
		
		Если ЗначениеЗаполнено(Объект.СМП_УчетнаяЗаписьБанка)
			И ЗначениеЗаполнено(Объект.СМП_УчетнаяЗаписьБанка.ПодключаемаяОбработка) Тогда
			Объект.СМП_РасширениеФайлаИмпорта			= Обработки.КлиентБанк.СМП_ПолучитьФорматФайла(Объект.СМП_УчетнаяЗаписьБанка.ПодключаемаяОбработка);
			Объект.СМП_РасширениеФайлаЭкспорта			= Обработки.КлиентБанк.СМП_ПолучитьФорматФайлаЭкспорта(Объект.СМП_УчетнаяЗаписьБанка.ПодключаемаяОбработка);
		КонецЕсли;
		
		Если НастройкаЗаполнения.Количество() = 0 Тогда
			НастройкаЗаполненияСтрока 					= НастройкаЗаполнения.Добавить();
			НастройкаЗаполненияСтрока.Документ 			= "Поступление на расчетный счет";
			НастройкаЗаполненияСтрока 					= НастройкаЗаполнения.Добавить();
			НастройкаЗаполненияСтрока.Документ 			= "Списание с расчетного счета";
		КонецЕсли;
		
		НайденнаяСтрока 								= НастройкаЗаполнения.НайтиСтроки(Новый Структура("Документ", "Поступление на расчетный счет"));
		НайденнаяСтрока[0].Проводить 					= Настройки.ПроводитьПриЗагрузкеПоступлениеНаРасчетныйСчет;
		НайденнаяСтрока[0].СтатьяДДС 					= Настройки.СтатьяДДСПоступлениеНаРасчетныйСчет;
		
		НайденнаяСтрока 								= НастройкаЗаполнения.НайтиСтроки(Новый Структура("Документ", "Списание с расчетного счета"));
		НайденнаяСтрока[0].Проводить 					= Настройки.ПроводитьПриЗагрузкеСписаниеСРасчетногоСчета;
		НайденнаяСтрока[0].СтатьяДДС 					= Настройки.СтатьяДДССписаниеСРасчетногоСчета;
		
		ГруппаДляНовыхКонтрагентов						= Настройки.ГруппаДляНовыхКонтрагентов;
		#КонецВставки
		
		#Удаление
		Объект.Кодировка                                = Настройки.Кодировка;
		#КонецУдаления
		
		#Вставка
		Если ЗначениеЗаполнено(Объект.СМП_УчетнаяЗаписьБанка) Тогда
			Объект.Кодировка 							= Объект.СМП_УчетнаяЗаписьБанка.Кодировка;
		КонецЕсли;
		#КонецВставки
		
		Объект.ФайлВыгрузки                             = Настройки.ФайлВыгрузки;
		Объект.ФайлЗагрузки                             = Настройки.ФайлЗагрузки;
		Объект.ВыгружатьПлатежноеПоручение              = Настройки.Платежное_Поручение;
		Объект.ВыгружатьПлатежноеТребование             = Настройки.Платежное_Требование;
		Объект.СоздаватьНенайденныеЭлементы             = Настройки.СоздаватьНенайденныеЭлементы;
		НастройкаВыполнена                              = Настройки.НастройкиЗагружены;
		
		#Вставка
		Объект.ВыгружатьПлатежноеПоручение				= Истина;
		Объект.ВыгружатьПлатежноеТребование				= Истина;
		#КонецВставки
		
		УправлениеФормойНаСервере();
		
	КонецЕсли;
	
КонецПроцедуры

&НаСервере
&ИзменениеИКонтроль("ЗагрузитьДокументыКИмпорту")
Функция СМП_ЗагрузитьДокументыКИмпорту(ИБФайловая)

	НеобходимоЗагружатьКонтрагентов = Объект.СоздаватьНенайденныеЭлементы И ТаблицаКонтрагентов.ПолучитьЭлементы().Количество() > 0;
	Если НеобходимоЗагружатьКонтрагентов Тогда
		АдресХранилищаКонтрагентов = ПолучитьАдресВременногоХранилищаТаблицыКонтрагентов();
	КонецЕсли;
	
	#Вставка
	Для каждого НастройкаЗаполненияСтрока Из НастройкаЗаполнения Цикл
		Если НастройкаЗаполненияСтрока.Документ = "Поступление на расчетный счет" Тогда
			НастройкаЗаполненияСтрока.Проводить = Истина;
			ПроводитьПриЗагрузкеПоступлениеНаРасчетныйСчет = Истина;
			
		ИначеЕсли НастройкаЗаполненияСтрока.Документ = "Списание с расчетного счета" Тогда
			НастройкаЗаполненияСтрока.Проводить = Истина;
			ПроводитьПриЗагрузкеСписаниеСРасчетногоСчета = Истина;
			
		КонецЕсли;
	КонецЦикла;
	#КонецВставки
	
	СтекОповещений     = Новый Массив;
	ДеревоКонтрагентов = РеквизитФормыВЗначение("ТаблицаКонтрагентов");
	Если НеобходимоЗагружатьКонтрагентов Тогда
		СтруктураПараметров =
		Новый Структура("ДокументыКИмпорту, СтруктураДанныхИмпорта, ДеревоКонтрагентов, ГруппаДляНовыхКонтрагентов,
		|МассивКонтрагентов, Импорт_Заголовок, Организация, Импорт_РасчетныеСчета, ИспользоватьГраницуОбработки,
		|НастройкаЗаполнения, ДатаГраницыОбработки, БанковскийСчет, СтекОповещений",
		ПолучитьТаблицуДокументов(ДеревоКонтрагентов), ПолучитьСтруктуруДанныхИмпорта(), ДеревоКонтрагентов, ГруппаДляНовыхКонтрагентов,
		Неопределено, Импорт_Заголовок, Объект.Организация, Импорт_РасчетныеСчета.Выгрузить(), Объект.ИспользоватьГраницуОбработки,
		НастройкаЗаполнения.Выгрузить(), Объект.ДатаГраницыОбработки, Объект.БанковскийСчет,
		СтекОповещений);
		
		#Вставка
		СтруктураПараметров.Вставить("ВедениеВзаиморасчетов", ?(ЗначениеЗаполнено(Объект.СМП_УчетнаяЗаписьБанка),Объект.СМП_УчетнаяЗаписьБанка.ВедениеВзаиморасчетов, Неопределено));
		#КонецВставки
		
	Иначе
		
		#Удаление
		СтруктураПараметров = Новый Структура("ДокументыКИмпорту, Импорт_Заголовок, Организация, Импорт_РасчетныеСчета,
		#КонецУдаления
		
		#Вставка
		СтруктураПараметров = Новый Структура("ДокументыКИмпорту, СтруктураДанныхИмпорта, ДеревоКонтрагентов, Импорт_Заголовок, Организация, Импорт_РасчетныеСчета,
		#КонецВставки
		
		|ИспользоватьГраницуОбработки, НастройкаЗаполнения, ДатаГраницыОбработки, БанковскийСчет, СтекОповещений",
		
		#Удаление
		ПолучитьТаблицуДокументов(ДеревоКонтрагентов), Импорт_Заголовок, Объект.Организация, Импорт_РасчетныеСчета.Выгрузить(),
		#КонецУдаления
		
		#Вставка
		ПолучитьТаблицуДокументов(ДеревоКонтрагентов), ПолучитьСтруктуруДанныхИмпорта(), ДеревоКонтрагентов, Импорт_Заголовок, Объект.Организация, Импорт_РасчетныеСчета.Выгрузить(),
		#КонецВставки
		
		Объект.ИспользоватьГраницуОбработки, НастройкаЗаполнения.Выгрузить(), Объект.ДатаГраницыОбработки, Объект.БанковскийСчет,
		СтекОповещений);
	КонецЕсли;

	Если ИБФайловая Тогда
		АдресХранилища = ПоместитьВоВременноеХранилище(Неопределено, УникальныйИдентификатор);
		Если НеобходимоЗагружатьКонтрагентов Тогда
			Обработки.КлиентБанк.ФоноваяЗагрузкаКонтрагентовИДокументов(СтруктураПараметров, АдресХранилища);
		Иначе
			Обработки.КлиентБанк.ФоноваяЗагрузкаДокументовКИмпорту(СтруктураПараметров, АдресХранилища);
		КонецЕсли;

		Результат = Новый Структура("ЗаданиеВыполнено", Истина);
	Иначе
		ПроцедураОбработки = ?(НеобходимоЗагружатьКонтрагентов,
		"Обработки.КлиентБанк.ФоноваяЗагрузкаКонтрагентовИДокументов",
		"Обработки.КлиентБанк.ФоноваяЗагрузкаДокументовКИмпорту");
		НаименованиеЗадания = НСтр("ru='Загрузка банковских документов из обработки ""Клиент-банк""';uk='Завантаження банківських документів з обробки ""Клієнт-банк""'");
		Результат = ДлительныеОперации.ЗапуститьВыполнениеВФоне(
		УникальныйИдентификатор,
		ПроцедураОбработки,
		СтруктураПараметров, 
		НаименованиеЗадания);

		АдресХранилища = Результат.АдресХранилища;
	КонецЕсли;

	Если Результат.ЗаданиеВыполнено Тогда
		НеобходимоЗагружатьКонтрагентов = Объект.СоздаватьНенайденныеЭлементы И ТаблицаКонтрагентов.ПолучитьЭлементы().Количество() > 0;
		Результат.Вставить("СтруктураДанныхКлиента", ЗагрузитьПодготовленныеДанные(НеобходимоЗагружатьКонтрагентов));
	КонецЕсли;

	Возврат Результат;

КонецФункции

&НаКлиенте
Процедура СМП_КомандаВыгрузитьВместо(Команда)
		ОчиститьСообщения();
	Если Объект.ПлатежныеДокументы.Количество() > 0 Тогда
		
		АдресФайлаВоВременномХранилище = ВыгрузитьДокументы();
		
		Если ВозможностьВыбораФайлов Тогда
			
			// Вариант для установленного расширения для работы с файлами
			
			Если НЕ ЗначениеЗаполнено(Объект.ФайлВыгрузки) Тогда
				ОбщегоНазначенияКлиентСервер.СообщитьПользователю(
					НСтр("ru='Не указан файл данных для выгрузки из Бухгалтерии';uk='Не вказаний файл даних для вивантаження з Бухгалтерії'")
					,, "Объект.ФайлВыгрузки");
				Возврат;
			КонецЕсли;
			
			ЭтоКаталог = Ложь;
			Если Прав(СокрЛП(Объект.ФайлВыгрузки), 1) = "\"
				ИЛИ Прав(СокрЛП(Объект.ФайлВыгрузки), 1) = "/" Тогда
				ЭтоКаталог   = Истина;
			ИначеЕсли Лев(Прав(СокрЛП(Объект.ФайлВыгрузки), 4),1) <> "." Тогда
				ФайлВыгрузки = Новый Файл(Объект.ФайлВыгрузки);
				ЭтоКаталог   = ФайлВыгрузки.Существует() И ФайлВыгрузки.ЭтоКаталог();
			КонецЕсли;
			
			Если ЭтоКаталог Тогда
				ТекстСообщения = НСтр("ru='Файл данных для выгрузки из Бухгалтерии не корректен - выбран ""каталог"".
|Выберите файл выгрузки';uk='Файл даних для вивантаження з Бухгалтерії не коректний - обраний ""каталог"".
|Виберіть файл вивантаження'");
				ОбщегоНазначенияКлиентСервер.СообщитьПользователю(
					ТекстСообщения
					,, "Объект.ФайлВыгрузки");
				
				Возврат;
			КонецЕсли;
			
			ПередаваемыеФайлы = Новый Массив;
			ПереданныеФайлы   = Новый Массив;
			МассивВызовов     = Новый Массив;
			
			ОписаниеФайла = Новый ОписаниеПередаваемогоФайла(Объект.ФайлВыгрузки, АдресФайлаВоВременномХранилище);
			
			ПередаваемыеФайлы.Добавить(ОписаниеФайла);
			
			МассивВызовов.Добавить(Новый Массив);
			
			МассивВызовов[0].Добавить("ПолучитьФайлы");
			МассивВызовов[0].Добавить(ПередаваемыеФайлы);
			МассивВызовов[0].Добавить(ПереданныеФайлы);
			МассивВызовов[0].Добавить("");
			МассивВызовов[0].Добавить(Ложь);
			
			Если ЗапроситьРазрешениеПользователя(МассивВызовов) Тогда
				
				ПолучитьФайлы(ПередаваемыеФайлы, ПереданныеФайлы,, Ложь);
				ТекстЗаголовока = НСтр("ru='Данные успешно выгружены в файл';uk='Дані успішно вивантажені в файл'");
				
				#Если НЕ ВебКлиент Тогда
				ПоказатьОповещениеПользователя(
					ТекстЗаголовока, "file:///" + СтрЗаменить(СокрЛП(Объект.ФайлВыгрузки), "\", "/"),
					Объект.ФайлВыгрузки, Элементы.КомандаВыгрузить.Картинка);
				#Иначе
				ПоказатьОповещениеПользователя(
					ТекстЗаголовока,,
					Объект.ФайлВыгрузки, Элементы.КомандаВыгрузить.Картинка);
				#КонецЕсли
				
			КонецЕсли;
			
		Иначе
			// Веб клиент без расширения для работы с файлами
			Попытка
				
				ПолучитьФайл(АдресФайлаВоВременномХранилище, "1C_to_CB.xml", Истина);
				
			Исключение
				ШаблонСообщения = НСтр("ru='При записи файла возникла ошибка
|%1';uk='При записі файлу відбулася помилка
|%1'");
				ТекстСообщения = СтроковыеФункцииКлиентСервер.ПодставитьПараметрыВСтроку(ШаблонСообщения,
					КраткоеПредставлениеОшибки(ИнформацияОбОшибке()));
				
				ОбщегоНазначенияКлиентСервер.СообщитьПользователю(ТекстСообщения);
				ОписаниеОшибки = ИнформацияОбОшибке();
				
				ЗаписатьОшибкуВЖурнал(ТекстСообщения, ОписаниеОшибки);
				
			КонецПопытки;
			
		КонецЕсли;
		
		ЭкспортПроизведен = Истина;
		
	Иначе
		
		Если Объект.НачПериода = Объект.КонПериода Тогда
			ТекстПериода = Формат(Объект.НачПериода, "ДФ=dd.MM.yyyy");
		Иначе
			ТекстПериода = НСтр("ru='период с %1 по %2';uk='період з %1 до %2'");
			ТекстПериода = СтроковыеФункцииКлиентСервер.ПодставитьПараметрыВСтроку(ТекстПериода,
				Формат(Объект.НачПериода, "ДФ=dd.MM.yyyy"), 
				Формат(Объект.КонПериода, "ДФ=dd.MM.yyyy"));
		КонецЕсли;
		
		ТекстСообщения = НСтр("ru='Отсутствуют платежные поручения за %1
|по счету %2
|(%3).
|
|Попробуйте изменить период или указать другой банковский счет.';uk='Відсутні платіжні доручення за %1
|по рахунку %2
|(%3).
|
|Спробуйте змінити період або вказати інший банківський рахунок.'");
		
		ТекстСообщения = СтроковыеФункцииКлиентСервер.ПодставитьПараметрыВСтроку(
			ТекстСообщения,
			ТекстПериода,
			Объект.БанковскийСчет,
			Объект.Организация);
		
		ПоказатьПредупреждение(, ТекстСообщения);
		
		Возврат;
		
	КонецЕсли;
	
	УправлениеФормой();
	
КонецПроцедуры

&НаСервере
&Вместо("ВыгрузитьДокументы")
Функция СМП_ВыгрузитьДокументы()
	
	СтруктураПараметров = Обработки.КлиентБанк.СМП_ПолучитьНастройкиПрограммыКлиентаБанка(Объект.Организация, Объект.БанковскийСчет);
	
	Если ЗначениеЗаполнено(СтруктураПараметров.СМП_УчетнаяЗаписьБанка) И ЗначениеЗаполнено(СтруктураПараметров.СМП_УчетнаяЗаписьБанка.ПодключаемаяОбработка) тогда
		
		ИмяФайла = ПолучитьИмяВременногоФайла("epf");
		ОбработкаОткр = СтруктураПараметров.СМП_УчетнаяЗаписьБанка.ПодключаемаяОбработка.ХранилищеОбработки.Получить();
		ОбработкаОткр.Записать(ИмяФайла);
		ВнешняяОбработка = ВнешниеОбработки.Создать(ИмяФайла, Ложь);
		ПараметрыДляВыгрузки = Новый Структура;
		ПараметрыДляВыгрузки.Вставить("ТаблицаДокументов", ТаблицаДокументов.Выгрузить());
		ПараметрыДляВыгрузки.Вставить("ПлатежныеДокументы", Объект.ПлатежныеДокументы);
		ПараметрыДляВыгрузки.Вставить("Кодировка", Объект.Кодировка);
		ПараметрыДляВыгрузки.Вставить("Программа", Объект.Программа);
		ПараметрыДляВыгрузки.Вставить("БанковскийСчет", Объект.БанковскийСчет);
		ПараметрыДляВыгрузки.Вставить("ФайлВыгрузки", Объект.ФайлВыгрузки);
		ПараметрыДляВыгрузки.Вставить("Организация", Объект.Организация);
		ПараметрыДляВыгрузки.Вставить("УникальныйИдентификатор", УникальныйИдентификатор);
		
		Файла = ВнешняяОбработка.Выгрузить_Бух(ПараметрыДляВыгрузки); 
		
		УдалитьФайлы(ИмяФайла);
		Возврат Файла; 
	Иначе
		
		Возврат Обработки.КлиентБанк.ВыгрузитьXML(ТаблицаДокументов.Выгрузить(),
		Объект.ПлатежныеДокументы,
		Объект.БанковскийСчет,
		Объект.ФайлВыгрузки,
		Объект.Организация,
		УникальныйИдентификатор);
	КонецЕсли;
	
КонецФункции

&НаКлиенте
&ИзменениеИКонтроль("ОбновитьСписокДокументовНаЭкспорт")
Процедура СМП_ОбновитьСписокДокументовНаЭкспорт(ОчищатьСообщения)

	Если Элементы.ГруппаСтраницы.ТекущаяСтраница <> Элементы.ГруппаВыгрузка Тогда
		Возврат;
	КонецЕсли;

	Если ОчищатьСообщения Тогда
		ОчиститьСообщения();
	КонецЕсли;

	Объект.ПлатежныеДокументы.Очистить();

	Если НЕ ЗначениеЗаполнено(Объект.БанковскийСчет) Тогда
		Возврат;
	КонецЕсли;
	
	#Удаление
	Если НЕ Объект.ВыгружатьПлатежноеПоручение И НЕ Объект.ВыгружатьПлатежноеТребование Тогда
		ПоказатьПредупреждение(, НСтр("ru='Необходимо отметить хотя бы один из видов платежных документов.';uk='Необхідно відзначити хоча б один з видів платіжних документів.'"));
		Возврат;
	КонецЕсли;
	#КонецУдаления

	Если НЕ ЗначениеЗаполнено(Объект.БанковскийСчет) Тогда
		ТекстСообщения = ОбщегоНазначенияБПКлиентСервер.ПолучитьТекстСообщения("Поле", "Заполнение", "Банковский счет");
		ОбщегоНазначенияКлиентСервер.СообщитьПользователю(ТекстСообщения,, "Объект.БанковскийСчет");
		Возврат;
	КонецЕсли;

	Если НЕ ЗначениеЗаполнено(Объект.КонПериода) Тогда
		ТекстСообщения = ОбщегоНазначенияБПКлиентСервер.ПолучитьТекстСообщения("Поле", "Заполнение", "Конец периода выгрузки");
		ОбщегоНазначенияКлиентСервер.СообщитьПользователю(ТекстСообщения,, "Объект.КонПериода");
		Возврат;
	КонецЕсли;
	
	#Удаление
	ДокументыНаЭкспортОбновитьСервер(Объект.ВыгружатьПлатежноеПоручение, Объект.ВыгружатьПлатежноеТребование);
	#КонецУдаления
	
	#Вставка
	ДокументыНаЭкспортОбновитьСервер(Истина, Истина);
	#КонецВставки
	
КонецПроцедуры

&НаКлиенте
Процедура СМП_ДокументыКИмпортуДокументРасчетовПриИзмененииВместо(Элемент)
	
	//ТекущаяСтрока = Элементы.Загрузка.ТекущиеДанные;
	//ТекущаяСтрока.ПризнакАванса = НЕ ЗначениеЗаполнено(ТекущаяСтрока.ДокументРасчетов);
	//
	//УстановитьСпособРаспределенияОплаты();
	
КонецПроцедуры

&НаКлиенте
Процедура СМП_ДокументыКИмпортуДокументРасчетовНачалоВыбораВместо(Элемент, ДанныеВыбора, СтандартнаяОбработка)
	
	ТекущаяСтрокаТабличнойЧасти = Элементы.ДокументыКИмпорту.ТекущиеДанные;
	
	МассивПараметров = Новый Массив;
	МассивПараметров.Добавить(Новый ПараметрВыбора("Отбор.Контрагент", ТекущаяСтрокаТабличнойЧасти.Контрагент));
	МассивПараметров.Добавить(Новый ПараметрВыбора("Отбор.ДоговорКонтрагента", ТекущаяСтрокаТабличнойЧасти.Договор));
	МассивПараметров.Добавить(Новый ПараметрВыбора("Отбор.Организация", Объект.Организация));
	
	Элемент.ПараметрыВыбора = Новый ФиксированныйМассив(МассивПараметров);
	
	СтандартнаяОбработка = СМП_ПроверитьВозможностьВыбораДокумента(ТекущаяСтрокаТабличнойЧасти, НСтр("ru = 'документа расчетов'"));
	Если СтандартнаяОбработка Тогда
		СтандартнаяОбработка = СМП_ПроверитьНастройкиРасчетов(ТекущаяСтрокаТабличнойЧасти, НСтр("ru = 'документам расчетов'"), "ВедениеВзаиморасчетов");
		
		Если СтандартнаяОбработка Тогда
			СтандартнаяОбработка = Ложь;
			//СтрокаПлатеж = Элементы.РасшифровкаПлатежа.ТекущиеДанные;
			СтрокаПлатеж = ТекущаяСтрокаТабличнойЧасти;
			
			ПараметрыОбъекта = Новый Структура;
			ПараметрыОбъекта.Вставить("Дата",                  СтрокаПлатеж.ДатаДок);
			ПараметрыОбъекта.Вставить("ДоговорКонтрагента",    СтрокаПлатеж.Договор);
			ПараметрыОбъекта.Вставить("Контрагент",            СтрокаПлатеж.Контрагент);
			ПараметрыОбъекта.Вставить("Организация",           Объект.Организация);
			ПараметрыОбъекта.Вставить("ОстаткиОбороты",        ?(СтрокаПлатеж.СуммаПоступило>0,"Дт", "Кт"));
			
			Если СтрокаПлатеж.СуммаПоступило>0 Тогда
				ПараметрыОбъекта.Вставить("ТипыДокументов","Метаданные.Документы.ПоступлениеНаРасчетныйСчет.ТабличныеЧасти.РасшифровкаПлатежа.Реквизиты.Сделка.Тип");
			Иначе
				ПараметрыОбъекта.Вставить("ТипыДокументов","Метаданные.Документы.СписаниеСРасчетногоСчета.ТабличныеЧасти.РасшифровкаПлатежа.Реквизиты.Сделка.Тип");
			КонецЕсли;
			
			ПараметрыОбъекта.Вставить("СчетУчета", ПредопределенноеЗначение("ПланСчетов.Хозрасчетный.РасчетыСОтечественнымиПокупателями"));
			
			ПараметрыФормы = Новый Структура("ПараметрыОбъекта", ПараметрыОбъекта);
			ОткрытьФорму("Документ.ДокументРасчетовСКонтрагентом.ФормаВыбора", ПараметрыФормы, Элемент);
			
		КонецЕсли;
		
	КонецЕсли;
	
КонецПроцедуры

&НаКлиенте
Функция СМП_ПроверитьВозможностьВыбораДокумента(ТекущаяСтрокаТабличнойЧасти, СтрокаСНазваниемДокумента)
	
	Если ТипЗнч(ТекущаяСтрокаТабличнойЧасти.Договор) = Тип("Строка") Тогда
		
		СтандартнаяОбработка = Ложь;
		
		ТекстСообщения = НСтр("ru = 'Договор не идентифицирован, выбор %1 не возможен.'");
		ТекстСообщения = СтрЗаменить(ТекстСообщения, "%1", СтрокаСНазваниемДокумента);
		ОбщегоНазначенияКлиентСервер.СообщитьПользователю(ТекстСообщения);
		
	Иначе
		СтандартнаяОбработка = Истина;
	КонецЕсли;
	
	Возврат СтандартнаяОбработка;
	
КонецФункции

&НаКлиенте
Функция СМП_ПроверитьНастройкиРасчетов(ТекущаяСтрокаТабличнойЧасти, СтрокаСНазваниемДокумента, ИмяРеквизита)
	
	Если Не СМП_ВедениеВзаиморасчетовПоРасчетнымДокументам(ТекущаяСтрокаТабличнойЧасти.Договор, ИмяРеквизита) Тогда
		
		СтандартнаяОбработка = Ложь;
		
		ТекстСообщения = НСтр("ru = 'С контрагент не ведется учет расчетов по %1. Выбор документа не требуется.'");
		ТекстСообщения = СтрЗаменить(ТекстСообщения, "%1", СтрокаСНазваниемДокумента);
		ОбщегоНазначенияКлиентСервер.СообщитьПользователю(ТекстСообщения);
		
	Иначе
		СтандартнаяОбработка = Истина;
	КонецЕсли;
	
	Возврат СтандартнаяОбработка;
	
КонецФункции

&НаСервереБезКонтекста
Функция СМП_ВедениеВзаиморасчетовПоРасчетнымДокументам(Договор, ИмяРеквизита)
	Возврат СМП_ПолучитьРеквизитДоговора(Договор, ИмяРеквизита) = Перечисления.ВедениеВзаиморасчетовПоДоговорам.ПоРасчетнымДокументам;
КонецФункции

&НаСервереБезКонтекста
Функция СМП_ПолучитьРеквизитДоговора(Договор, Реквизит)
	Возврат Договор[Реквизит];
КонецФункции

&НаСервереБезКонтекста
Функция СМП_ЕстьЗаписиВСправочникеСоответствий()
	
	Запрос = Новый Запрос;
	Запрос.Текст = 
		"ВЫБРАТЬ ПЕРВЫЕ 1
		|	СМП_СоответствияНазначенийИРеквизитовПлатежа.Ссылка
		|ИЗ
		|	Справочник.СМП_СоответствияНазначенийИРеквизитовПлатежа КАК СМП_СоответствияНазначенийИРеквизитовПлатежа
		|ГДЕ
		|	НЕ СМП_СоответствияНазначенийИРеквизитовПлатежа.ПометкаУдаления";
	
	РезультатЗапроса = Запрос.Выполнить();
	
	Возврат Не РезультатЗапроса.Пустой();
	
КонецФункции

&НаСервере
&ИзменениеИКонтроль("ПолучитьТаблицуДокументов")
Функция СМП_ПолучитьТаблицуДокументов(ДеревоКонтрагентов)
	
	ТаблицаДокументовКИмпорту = ДокументыКИмпорту.Выгрузить();
	ТаблицаДокументовКИмпорту.Колонки.Добавить("РеквизитыКонтрагента");
	
	#Вставка
	ТаблицаДокументовКИмпорту.Колонки.Добавить("СчетУчетаРасчетовСКонтрагентом");
	ТаблицаДокументовКИмпорту.Колонки.Добавить("СубконтоДт1");
	ТаблицаДокументовКИмпорту.Колонки.Добавить("СубконтоДт2");
	ТаблицаДокументовКИмпорту.Колонки.Добавить("СубконтоДт3");
	#КонецВставки
	
	Для каждого СтрокаСекции Из ТаблицаДокументовКИмпорту Цикл
		ТипКонтрагента  = ?(СтрокаСекции.ПлательщикСчет = Объект.БанковскийСчет.НомерСчета, "ПОЛУЧАТЕЛЬ", "ПЛАТЕЛЬЩИК");
		
		ПолеПоиска       = НСтр("ru='ЕДРПОУ';uk='ЄДРПОУ'");
		ЗначениеПоиска   = СтрокаСекции[ТипКонтрагента + "ОКПО"];
		// Если ИНН контрагента в файле не задан, то ищем по имени
		Если ПустаяСтрока(ЗначениеПоиска) Тогда
			ПолеПоиска     = НСтр("ru='Наименование';uk='Найменування'");
			ЗначениеПоиска = СтрокаСекции[ТипКонтрагента];
			
			Если ПустаяСтрока(ЗначениеПоиска) Тогда
				ЗначениеПоиска = СтрокаСекции[ТипКонтрагента];
			КонецЕсли;
		КонецЕсли;
		
		СтруктураПоиска = Новый Структура("Представление, Значение", ПолеПоиска, ЗначениеПоиска);
		НайденныеЗаписиОКонтрагенте = ДеревоКонтрагентов.Строки.НайтиСтроки(СтруктураПоиска, Истина);
		
		СтрокаСекции.РеквизитыКонтрагента = Неопределено;
		
		Если НайденныеЗаписиОКонтрагенте.Количество() > 0 Тогда
			НайденнаяСтрока = НайденныеЗаписиОКонтрагенте[0];
			
			Родитель = НайденнаяСтрока.Родитель;
			Если Родитель <> Неопределено Тогда
				НайденнаяСтрока = Родитель;
			КонецЕсли;
			
			РеквизитыКонтрагента = Новый ТаблицаЗначений();
			РеквизитыКонтрагента.Колонки.Добавить("Значение");
			РеквизитыКонтрагента.Колонки.Добавить("Представление");
			РеквизитыКонтрагента.Колонки.Добавить("Реквизит");
			
			СтрокаСекции.РеквизитыКонтрагента = РеквизитыКонтрагента;
			
			Для Счет = 0 По 2 Цикл
				НовыйРеквизит = РеквизитыКонтрагента.Добавить();
				НовыйРеквизит.Представление = НайденнаяСтрока.Строки[Счет].Представление;
				НовыйРеквизит.Значение      = НайденнаяСтрока.Строки[Счет].Значение;
				НовыйРеквизит.Реквизит      = НайденнаяСтрока.Строки[Счет].Реквизит;
			КонецЦикла;
			
			Если СтрокаСекции.ВидОперации = Перечисления.ВидыОперацийПоступлениеДенежныхСредств.ОплатаПокупателя Тогда
				ВидДоговора = НСтр("ru='С покупателем';uk='З покупцем'");
			ИначеЕсли СтрокаСекции.ВидОперации <> Перечисления.ВидыОперацийСписаниеДенежныхСредств.ПеречислениеНалога Тогда
				ВидДоговора = НСтр("ru='С поставщиком';uk='З постачальником'");
			Иначе
				ВидДоговора = НСтр("ru='другой';uk='інший'");
			КонецЕсли;
			
			Для каждого Строка Из НайденнаяСтрока.Строки Цикл
				Если Строка.Представление = НСтр("ru='Счет';uk='Рахунок'") И Строка.Значение = СтрокаСекции[ТипКонтрагента + "СЧЕТ"] Тогда
					
					НовыйРеквизит = РеквизитыКонтрагента.Добавить();
					НовыйРеквизит.Представление = Строка.Представление;
					НовыйРеквизит.Значение      = Строка.Значение;
					НовыйРеквизит.Реквизит      = Строка.Реквизит;
					
					Для каждого ПодСтрока Из Строка.Строки Цикл
						НовыйРеквизит = РеквизитыКонтрагента.Добавить();
						НовыйРеквизит.Представление = ПодСтрока.Представление;
						НовыйРеквизит.Значение      = ПодСтрока.Значение;
						НовыйРеквизит.Реквизит      = ПодСтрока.Реквизит;
					КонецЦикла;
					
				КонецЕсли;
			КонецЦикла;
			
			Для каждого Строка Из НайденнаяСтрока.Строки Цикл
				Если Строка.Представление = НСтр("ru='Договор';uk='Договір'") И Строка.Значение = ВидДоговора Тогда
					
					НовыйРеквизит = РеквизитыКонтрагента.Добавить();
					НовыйРеквизит.Представление = Строка.Представление;
					НовыйРеквизит.Значение      = Строка.Значение;
					НовыйРеквизит.Реквизит      = Строка.Реквизит;
					
					Для каждого ПодСтрока Из Строка.Строки Цикл
						НовыйРеквизит = РеквизитыКонтрагента.Добавить();
						НовыйРеквизит.Представление = ПодСтрока.Представление;
						НовыйРеквизит.Значение      = ПодСтрока.Значение;
						НовыйРеквизит.Реквизит      = ПодСтрока.Реквизит;
					КонецЦикла;
					
				КонецЕсли;
			КонецЦикла;
		КонецЕсли;
	КонецЦикла;
	
	Возврат ТаблицаДокументовКИмпорту;
	
КонецФункции

&НаКлиенте
Процедура СМП_ОткрытьСправочникСоответствийНазначенийПлатежаИРеквизитовДокументовПосле(Команда)
	
	ПарамФормы = Новый Структура;
	Если ЗначениеЗаполнено(Объект.Организация) Тогда
		ПарамФормы.Вставить("Организация", Объект.Организация);
		
	КонецЕсли;
	
	ОткрытьФорму("Справочник.СМП_СоответствияНазначенийИРеквизитовПлатежа.ФормаСписка", ПарамФормы, , , , , ,
		РежимОткрытияОкнаФормы.БлокироватьОкноВладельца);
	
КонецПроцедуры

&НаСервереБезКонтекста
&ИзменениеИКонтроль("ДокументыКИмпортуКонтрагентПриИзмененииСервер")
Функция СМП_ДокументыКИмпортуКонтрагентПриИзмененииСервер(ТекущиеДанные, Знач СоздаватьНенайденныеЭлементы)
	
	Если ТипЗнч(ТекущиеДанные.СчетКонтрагента) = Тип("Строка") Тогда
		СчетКонтрагента = Справочники.БанковскиеСчета.ПустаяСсылка();
		УчетДенежныхСредствБП.УстановитьБанковскийСчет(
			СчетКонтрагента, ТекущиеДанные.Контрагент, ТекущиеДанные.ВалютаРегламентированногоУчета);
		Если СчетКонтрагента <> Справочники.БанковскиеСчета.ПустаяСсылка() Тогда
			ТекущиеДанные.СчетКонтрагента = СчетКонтрагента;
		КонецЕсли;
	Иначе
		УчетДенежныхСредствБП.УстановитьБанковскийСчет(
			ТекущиеДанные.СчетКонтрагента, ТекущиеДанные.Контрагент, ТекущиеДанные.ВалютаРегламентированногоУчета);
	КонецЕсли;
	
	СписокВидовДоговоров = УчетДенежныхСредствКлиентСервер.ОпределитьВидДоговораСКонтрагентом(ТекущиеДанные.ВидОперации);
	
	Если ТипЗнч(ТекущиеДанные.Договор) = Тип("Строка") Тогда
		ДоговорКонтрагента = Справочники.ДоговорыКонтрагентов.ПустаяСсылка();
		УстановитьДоговорКонтрагента(
			ДоговорКонтрагента, ТекущиеДанные.Контрагент, ТекущиеДанные.Организация, СписокВидовДоговоров);
		Если ДоговорКонтрагента <> Справочники.ДоговорыКонтрагентов.ПустаяСсылка() Тогда
			ТекущиеДанные.Договор = ДоговорКонтрагента;
		КонецЕсли;
	Иначе
		УстановитьДоговорКонтрагента(
			ТекущиеДанные.Договор, ТекущиеДанные.Контрагент, ТекущиеДанные.Организация, СписокВидовДоговоров);
	КонецЕсли;
	
	#Вставка
	Если ЗначениеЗаполнено(ТекущиеДанные.Контрагент) И ТипЗнч(ТекущиеДанные.Контрагент) = Тип("СправочникСсылка.Контрагенты") Тогда
		НовыйКодПоЕДРПОУ = ТекущиеДанные.Контрагент.КодПоЕДРПОУ;
		
		Если Не СокрЛП(НовыйКодПоЕДРПОУ) = "" Тогда
			
			ТекущиеДанные.Вставить(?(ТекущиеДанные.ВидДокумента = "СписаниеСРасчетногоСчета","ПолучательОКПО","ПлательщикОКПО"),
					НовыйКодПоЕДРПОУ);
					
			ТекущиеДанные.Вставить("ОКПОДляПоискаДок",	НовыйКодПоЕДРПОУ);
			ТекущиеДанные.Вставить("ОКПОКонтрагента",	НовыйКодПоЕДРПОУ);
		КонецЕсли; 
		
	КонецЕсли;
	#КонецВставки
	
	ОбновитьСостояниеСтроки(
		ТекущиеДанные.ДоговорКонтрагентаНеНайден, ТекущиеДанные.Готовность, ТекущиеДанные.Договор,
		СоздаватьНенайденныеЭлементы, ТекущиеДанные.ВидОперации, ТекущиеДанные.ОписаниеОшибок,
		ТекущиеДанные.Контрагент, ТекущиеДанные.СчетКонтрагента);
	
	Возврат ТекущиеДанные;
	
КонецФункции

&НаКлиенте
&ИзменениеИКонтроль("ДокументыКИмпортуКонтрагентПриИзменении")
Процедура СМП_ДокументыКИмпортуКонтрагентПриИзменении(Элемент)
	
	ТекущиеДанные = Элементы.ДокументыКИмпорту.ТекущиеДанные;
	
	ВходящиеПараметры = Новый Структура;
	ВходящиеПараметры.Вставить("Организация",                    Объект.Организация);
	ВходящиеПараметры.Вставить("ВидОперации",                    ТекущиеДанные.ВидОперации);
	ВходящиеПараметры.Вставить("СчетКонтрагента",                ТекущиеДанные.СчетКонтрагента);
	ВходящиеПараметры.Вставить("Контрагент",                     ТекущиеДанные.Контрагент);
	ВходящиеПараметры.Вставить("Договор",                        ТекущиеДанные.Договор);
	ВходящиеПараметры.Вставить("Готовность",                     ТекущиеДанные.Готовность);
	
	#Удаление
	ВходящиеПараметры.Вставить("ВидОперации",                    ТекущиеДанные.ВидОперации);
	#КонецУдаления
	
	#Вставка
	ВходящиеПараметры.Вставить("ВидДокумента",                   ТекущиеДанные.ВидДокумента);
	#КонецВставки
	
	ВходящиеПараметры.Вставить("ОписаниеОшибок",                 ТекущиеДанные.ОписаниеОшибок);
	ВходящиеПараметры.Вставить("ДоговорКонтрагентаНеНайден",     ТекущиеДанные.ДоговорКонтрагентаНеНайден);
	ВходящиеПараметры.Вставить("ВалютаРегламентированногоУчета", ВалютаРегламентированногоУчета);
	
	ИсходящиеПараметры = ДокументыКИмпортуКонтрагентПриИзмененииСервер(ВходящиеПараметры, Объект.СоздаватьНенайденныеЭлементы);
	ЗаполнитьЗначенияСвойств(ТекущиеДанные, ИсходящиеПараметры);
	
КонецПроцедуры