# Базова конфігурація — локально, не в git

Тут має лежати вивантаження конфігурації **BAS for accounting (Бухгалтерія)** у форматі
Designer platform XML, у підкаталозі `src/`.

Вміст цієї теки навмисно виключено з git: це код вендора, а репозиторій публічний.

Вивантажити:

```powershell
pwsh <корінь плагіна>/tools/dump-config.ps1 -RepoRoot . -Product BankExchange_ACC
```

Корінь плагіна показує команда `/plugin` у сесії Claude Code; типово це
`~/.claude/plugins/cache/smp-v8storagekit/v8storagekit/<версія>`.

Конфігурація потрібна тільки для операцій Unica, яким треба знати склад
конфігурації-власника: `cfe.borrow`, `cfe.diff`, `cfe.validate`. Для правок коду
й форм уже запозичених об'єктів вона не обов'язкова.
