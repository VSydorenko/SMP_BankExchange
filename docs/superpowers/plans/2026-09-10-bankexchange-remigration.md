# Повторна міграція SMP_BankExchange на v8storagekit 1.0

Дата: 2026-09-10. Форма: **двошарова** — gitsync-вивантаження (§5.1) під напівмігрованим 0.6.0 (§5.2).
Скіл перечитано з `R:\github\SMP_V8StorageKit` (dev, не кеш), включно з правками `d3e96f8`,
які додали саме розділ про двошарову форму й розкладку кроків на кілька джерел.

## Рішення користувача (зафіксовані)

| Питання | Рішення |
|---|---|
| Гілки переходу | **Не створювати.** Усе на `main` — §5.1 крок 2: «Нових гілок для історії немає» |
| `migrate/v8storagekit-0.6.0` | видалити локально й на `origin` |
| Архів 82 комітів 0.6.0 | **лише bundle-файл, без тега** |
| Перенести з 82 комітів | `docs/` + консолідація `epf/`; docs потім ревізувати на актуальність |
| Глибина реплею | продовжити з `VERSION+1` |
| AUTHORS | різати `-MaxVersions` по межах (§5.3 дослівно) |
| `epf/dist/*.epf` | **не тримати в git**, додати `dist/` у `.gitignore` |
| Ключі дев-баз | `devUNF` / `devUNFru` / `devACC` |

> Тег `legacy/gitsync-2025-02` на `dca2f8a` — це **інше** і лишається: він частина процедури §5.1
> (крок 2), і на нього посилається хвіст (`git show legacy/gitsync-2025-02:<шлях>`). Рішення
> «без тега» стосувалось архіву 0.6.0, не межі gitsync.

## Вхідні дані

| Продукт | EDT-тека на `dca2f8a` | Файлів | `VERSION` | `-FromVersion` | Сховище |
|---|---|---|---|---|---|
| `SMP_BankExchange_SMB` | `BAS small business` | 207 | 23 | 24 | `R:\СховищаРозширень_1С\СМП_BankExchange_SMB` |
| `SMP_BankExchange_ACC` | `BAS for accounting` | 73 | 35 | 36 | `R:\СховищаРозширень_1С\СМП_BankExchange_BP` |
| `SMP_BankExchange_SMBru` | `SMB` | 137 | 15 | 16 | `R:\СховищаРозширень_1С\СМП_BankExchange_SMBru` |
| `epf` (`bank_formats`) | `ExtDataProcessors` (вже Designer) | 72 | — | — | `truth: git` |

Пастки §5.2 перевірені — **жодна не спрацьовує**: `name:` == `extensionName` == `<Name>` у всіх трьох;
`infobase:` у локальних файлах немає (лише `devInfobase:`), база агента не підмінена;
цілі `rename-edt` різні. Розбіжність `storagePath` `…_BP` ↔ ім'я `…_ACC` — очікувана (§5.2).

## ✅ Фаза 0 — ВИКОНАНО (нічого не змінила)

- 0.1 `check-environment` — усе `[+]`: PowerShell 7.5.4, git 2.53.0, платформа 8.3.27.1644,
  `powershell-yaml` 0.4.12, Pester 6.1.0, unica 0.12.3.
- 0.2 **Bundle:** `R:\github\SMP_BankExchange.pre-remigration-2026-09-10.bundle`, 3,6 МБ,
  `git bundle verify` → *«The bundle records a complete history»*, 19 refs (обидві гілки, origin, 13 тегів).
  **Це єдина копія 82 комітів** — лежить поза репозиторієм і поза scratchpad навмисно.
- 0.3 Перелік роботи вище `dca2f8a` — нижче.
- 0.4 Усі три теки сховищ існують, `1cv8ddb.1CD` на місці. Повна проба (звіт) — у фазі 2, після маніфесту.
- 0.5 Усі 13 тегів — до `dca2f8a`, жоден не осиротіє.

### Що народилось вище `dca2f8a` і куди дінеться

| Що | Доля |
|---|---|
| `docs/` — 9 файлів | **перенести**, потім ревізувати на актуальність |
| `AUTHORS` (кореневий, з разовими мапінгами) | **перенести** |
| `epf/` — консолідація, у git уже як **72 × R100** + `v8project.yaml` | **відтворити** тим самим `git mv` |
| `SMP_BankExchange_*/v8project.yaml` × 3 | **перенести** (вже коректні) |
| `SMP_BankExchange_*/README.md` × 3, `cf/README.md` × 3, кореневий `README.md` | **перенести й оновити** — посилаються на команди 0.6.0 (`dump-config.ps1 -Product …`) |
| `CLAUDE.md` | **переписати** — застарів (теки `BankExchange_SMB` замість `SMP_BankExchange_SMB`) |
| `.claude/settings.json` | дозволи перенести, решту дасть `install-hooks` |
| `.gitattributes` / `.gitignore` | з шаблонів плагіна + фактичні шляхи |
| `SMP_BankExchange_*/storage.json` × 3 | **не переносити** — спадок 0.6.0, значення вже витягнуті |
| `epf/dist/*.epf` × 12 | **не переносити**, `dist/` у `.gitignore` |
| Розробка конвеєра | не переносити — живе в плагіні |

## Фаза 1 — оголити gitsync-форму

1.1. `git switch main` (зараз `migrate/v8storagekit-0.6.0`). §3.6: онбординг комітить у головну гілку.
1.2. `git reset --hard dca2f8a` на `main`. **Деструктивно, під санкцією користувача, після bundle.**
1.3. `git tag legacy/gitsync-2025-02 dca2f8a` — межа gitsync (останній gitsync-коміт: 2025-02-24).
1.4. Видалити `migrate/v8storagekit-0.6.0` локально. Видалення на `origin` — окремим підтвердженням.

## Фаза 2 — крок 1 §5.1, ОДИН раз на репозиторій

Порядок усередині фази важливий: `.gitignore` **до** появи `v8storagekit.local.yaml`
(§3.3 — властивість безпеки, репозиторій публічний).

2.1. `docs/` з bundle-стану (`git checkout <старий sha> -- docs`) + цей план у `docs/superpowers/plans/`.
2.2. `epf/`: `git mv ExtDataProcessors/<Банк>/src/*` → `epf/src/` (72 файли) + `epf/v8project.yaml`.
     Окремим комітом; очікується R100 (вміст не змінюється, підтверджено наявною історією).
2.3. Кореневий `AUTHORS`. Per-product `AUTHORS` у квартетах — до хвоста фази 4.
2.4. Три `v8project.yaml`. Теки продуктів **не перейменовувати руками** — `rename-edt` сам переносить
     `BAS small business/src` → `SMP_BankExchange_SMB/cfe/src`.
2.5. `v8storagekit.yaml` — `product: SMP_BankExchange`, 4 воркспейси, 7 джерел.
2.6. `.gitattributes` / `.gitignore` (§3.4): `-text` на `SMP_BankExchange_*/cfe/src/**` × 3 і `epf/src/**`;
     ignore на `SMP_BankExchange_*/cf/**` × 3 + `!**/cf/README.md`, плюс `dist/`.
2.7. **Аж тепер** `v8storagekit.local.yaml`: `devUNF` / `devUNFru` / `devACC`.
2.8. README продуктів + `cf/README.md` × 3 + кореневий README — перенести й оновити під 1.0.
2.9. `CLAUDE.md` — переписати під нову конвенцію.
2.10. `kit install-hooks -Apply`; `kit check`.
2.11. **ПЕРШИЙ КОМІТ** явним списком (§3.6); `<ws>/cf/README.md` — окремою командою `git add`.
      Приймальна: `git ls-files -s .githooks/` → два рядки `100755`; `kit check` без `[-]`.
2.12. **Повна проба доступу до трьох сховищ** — тепер маніфест є. Дає поточну максимальну версію
      і логін на кожну версію (потрібен для AUTHORS-нарізки).

**Ворота:** `kit check` з `[-]` → зупинка; `rename-edt` фази 3 однаково відмовить на брудній копії.

## Фаза 3 — кроки 3–6 §5.1, ВЕРТИКАЛЬНО: SMB → ACC → SMBru

Повний цикл для одного джерела, наступне — лише після зеленої приймальної перевірки.
Причина вертикальності (позиція розробника): у кожного джерела два запобіжники —
`check-attr text` усередині `rename-edt` і звірка хешів дерев. Вертикально помилка політик git
виявляється на першому ж дереві, горизонтально — після трьох перейменувань і трьох впалих злиттів.

**3.x.1 `rename-edt`** — прев'ю, потім `-Apply`:
```
kit rename-edt -RepoRoot . -SourceRelPath "<стара тека>/src" -TargetRoot "<ws>/cfe/src" [-Apply]
```
Час: 207/73/137 файлів × 0,073 с ≈ **15/5/10 секунд**. Мовчання — норма, процес не вбивати
(убитий не виконує `catch`, відкоту не буде).
Очікувані видалення: `Forms/*/Attributes/**`, `ScheduledJobs/*/Schedule.schedule`,
`ConfigDumpInfo.xml`, `DumpFilesIndex.txt`. Перелік `Unresolved` — не чіпати.

**3.x.2 `sync`** — скибками за AUTHORS-межами. SMB (звірити зі звітом сховища з 2.12):

| Скибка | Команда | Логін → особа |
|---|---|---|
| v24 | `-FromVersion 24 -MaxVersions 1` | `Decoratorskyi_UNF_work` → PrudnikovV |
| v25 | `-MaxVersions 1` | `TakeHot_UNF_work` → PrudnikovV |
| v26–33 | `-MaxVersions 8` | — |
| v34–38 | `-MaxVersions 5` | `TakeHot_UNF_work` → PrudnikovV |
| v39 | `-MaxVersions 1` | `Clarity_UNF_work` → Yaroslav Holovatyi |
| v40 | `-MaxVersions 1` | `TakeHot_UNF_work` → PrudnikovV |
| v41→вершина | без обмеження | за фактом зупинок |

Після кожної скибки — трейлер `Storage-Version` вершини.
ACC: `-FromVersion 36`; SMBru: `-FromVersion 16`.

**Крок 4 §5.1 — перше злиття ВПАДЕ, і це правильно.** Дві підказки (`git merge storage/<ключ>`
і `kit sync … -MergeMain`) — **не виконувати**: обидві означали б злиття до коміту конверсії.
Стан відкочується самою командою.

**3.x.3 Коміт конверсії** на `main` — плоский, не злиття.

**3.x.4 Приймальна перевірка — обов'язкова, одразу:**
```
git rev-parse main:<ws>/cfe/src
git rev-parse storage/<ключ>:<ws>/cfe/src
```
Хеші **дерев**. Не збіглись → **зупинка тут**, не на `verify`.

**3.x.5** `kit sync -RepoRoot . -Source <ключ> -Apply -MergeMain`.

## Фаза 4 — хвіст

4.1. Три коміти конверсії → `.git-blame-ignore-revs`.
4.2. `CLAUDE.md`: тег межі, дата, відповідність «EDT-шлях → Designer-шлях», обидві форми запиту історії.
4.3. `kit check` + `kit verify` — зелено.
4.4. **Аж після зеленого verify** — прибрати залишки EDT одним комітом: `BAS small business/`,
     `BAS for accounting/`, `SMB/`, залишки `ExtDataProcessors/`, `DT-INF/`, `.project`, `.settings/`,
     `VERSION`, per-product `AUTHORS`, осиротілі `Unresolved`.
     Кореневий `AUTHORS` **лишається**. У повідомленні: `git show legacy/gitsync-2025-02:<шлях>`.
4.5. Ревізія `docs/` — що застаріло після нової міграції.
4.6. Пуш `main` + видалення `migrate/*` на `origin` — **окремим рішенням користувача**.

## Межі проходу

- Сховища — тільки читання. Жодних `ConfigurationRepositoryCommit/Lock/Unlock`.
- `-Apply` — лише на явне прохання, покроково.
- Нічого не пушити.
- Маркер ліцензії (`лиценз|ліценз|license|HASP`) у виводі платформи → зупинка, сказати користувачу.
