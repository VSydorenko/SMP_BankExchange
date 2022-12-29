# BankExchange - підсистема інтеграції із системами Клієнт-Банк

Розширення для нативної інтеграції механізмів по роботі із клієнт банком в конфігурації на платформі 1С:Підприємство/BAF

На даний час, практично монополістом на ринку є обробка [Bank Data Converter][1] від Conto.
Її всі знають, всі використовують, але вона дуже не зручна в використанні та адмініструванні.

Основні недоліки, які вирішені в даному рішенні:

- Неможливо завантажити виписку за період, а тільки за конкретний день. В рішенні виписка завантажується за період, який вказаний в самій виписці, тому нема необхідності вказувати за яку дату проводиться завантаження. Для деяких банків підтримується завантаження часу проведення документа;
- Зберігання обробки читання форматів в каталогзі на диску з відповідними проблемами, при багатокористувацькому режимі роботи. В рішенні обробки читання теж зовнішні, але вони зберігаються в довіднику Зовнішніх обробок та невід'ємні від бази - при переносі бази в інше місце не потрібно додатково проводити переналаштування;
- Налаштування обробки зберігається в розрізі користувачів: новий користувач, нове налаштування. В рішенні налаштування проводяться для банківського рахунку, тому, всі, в кого є доступ до роботи із банківськими документами, відразу працюють із потрібними налаштуваннями.

## Нове у версії 1.0.2.5 для BAS for accounting

1. Додано механізм налаштування підбору виду операції та статті ДДС, в залежності від призначення платежу та організації.
2. Додано можливість вказувати значення за замовчуванням для виду операції Поступления от продаж по платежным картам и банковским кредитам.т Договір підбирається для Організації та Контрагента з видом Прочее, якщо такий договір один.
3. При створенні документа з видом операції Поступления от продаж по платежным картам и банковским кредитам, для строчки з рахунком розрахунків, враховується налаштування бази по підстановці цього рахунку. Потрібно провести налаштування для договору на рахунок 333.
4. Додано можливість вказувати значення за замовчуванням для виду операції Прочее списание (Рахунок Дебета та його субконто).
5. Додано обробку часу документів із файлу.
6. Додано можливість проводити налаштування читання виписки платежу по організації, якщо вона вказана в налаштуваннях. Якщо не вказана - це налаштування враховується для всіх організацій

## Розробка

Вивантаження на github проводилось на платформі 8.3.22.1923 та EDT версії 8.3.22.
Актуальний реліз розширення в форматі .cfe можна отримати в розділі Релізи.
Актуальні версії обробок читання форматів розміщені в папці ExtDataProcessors, а в підпапці /src/ - вихідний код кожної обробки.

## Додавання в конфігурацію користувача

В даному репозиторії розміщена підсистема для конфігурації BAS for accounting 2.1.x., підходить також для версії PROF та AGRO.
Розширення розроблялось для конфігурації BAS for accounting 2.1.x
Для роботи розширення, потрібно зняти галочку Безпечний режим та Захист від небезпечних дій, оскільки присутня взаємодія із зовнішніми системами, зрокрема, файлами виписок.

Є більше розширене рішення для конфігурації BAS for small company, для їх отримання - звертайтесь в [телеграм][2].

## Налаштування роботи після встановлення

Після додавання розширення в конфігурацію, потрібно також додати зовнішню обробку та налаштувати обліковий запис.
Більш детально про налаштування - читайте сторінку Wiki.

## Обговорення та pull request-и

Рішення поставляється як є, не гарантується робота в будь яких базах користувачів.
Всі модулі відкриті та вільні для власних допрацювань.
Приходьте до нас в [телеграм][2] - там можна задати питання та отримати відповіді.

pull request-и вітаються

[1]: https://conto.com.ua/ua/solutions/bank-data-sonverter/
[2]: https://t.me/simplySOFTnews