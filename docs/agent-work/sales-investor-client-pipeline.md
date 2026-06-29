# Pipeline продаж, инвесторов и первых клиентов

Дата подготовки: 2026-06-29  
Агент: Куратор инвесторов и клиентов  
Роль: `investor_client_curator`  
Статус: операционный документ для ручной проверки и первых касаний

Назначение: зафиксировать, кому продавать первые подписки Kolibri AI Platform,
как квалифицировать ранних клиентов, как вести инвесторский pipeline, какие
роли нужны агентам продаж, какие сообщения можно использовать и какие
обещания запрещены без подтверждений.

Граница работы: этот документ не отправляет внешние письма, не содержит
выдуманных контактов и не заменяет юридическую, инвестиционную или
комплаенс-проверку. Любой реальный контакт должен быть подтверждён источником,
ручной проверкой или тёплой интродукцией до внесения в CRM.

## 1. Рабочая рамка

Kolibri продаётся не как "ещё один AI-чат", а как проверяемый workflow для
строительных смет, коммерческих предложений и связанных документов.

Первые продажи должны проверять три гипотезы:

- клиент готов платить за сокращение времени подготовки сметы и пакета
  документов;
- клиент ценит повторяемость расчётов, audit fingerprint и human QA больше,
  чем магическую генерацию без контроля;
- подписочная модель Solo, Team или Studio понятна покупателю и может быть
  внедрена без enterprise-интеграции на первом шаге.

Для инвесторов Kolibri позиционируется как agent runtime с первым вертикальным
wedge в строительных сметах. Для клиентов Kolibri позиционируется как рабочий
инструмент сметчика, отдела продаж или проектной команды.

## 2. ICP первых клиентов

### Primary ICP: подрядчики и ремонтные команды

Кому подходит:

- малые и средние подрядчики, ремонтные бригады и строительные компании;
- команды, которые регулярно готовят сметы, КП, договоры, акты и счета;
- владельцы, руководители продаж, сметчики или project managers, которым нужно
  быстрее выпускать документы для клиента;
- русскоязычные команды, работающие с понятными типовыми работами и готовые
  дать один обезличенный реальный сценарий для demo;
- команды без сложного enterprise-procurement на первом этапе.

Боль:

- смета и КП собираются вручную, долго и каждый раз немного по-разному;
- ошибки в объёмах, формулах, коэффициентах и итогах дорого стоят;
- менеджеры продаж зависят от одного перегруженного сметчика;
- документы приходится переносить между Excel, Word, PDF и мессенджерами;
- нет простого audit trail для объяснения клиенту, откуда взялась сумма.

Почему Kolibri может быть куплен:

- ускоряет черновик сметы и пакета документов;
- показывает структуру расчёта и audit fingerprint;
- даёт повторяемый результат для одинаковых вводных;
- оставляет человеку финальное решение перед отправкой клиенту;
- продаётся как подписка, а не как тяжёлая интеграция.

Критерии квалификации:

| Критерий | Хороший сигнал | Красный флаг |
| --- | --- | --- |
| Частота смет | 10+ смет или КП в месяц | Разовая смета раз в квартал |
| Владелец боли | Есть руководитель, сметчик или sales lead | Никто не отвечает за процесс |
| Данные для demo | Есть обезличенный пример | Нельзя показать даже типовой кейс |
| Готовность платить | Понимают подписку как операционный расход | Ждут бесплатный bespoke-проект |
| Риск | Документы проходят human review | Хотят полностью автономную отправку клиенту |

### Secondary ICP: проектные бюро и sales departments

Кому подходит:

- проектные и дизайн-бюро, которые часто готовят первичные коммерческие
  предложения;
- отделы продаж строительных и ремонтных компаний;
- команды, которым нужен аккуратный документный пакет, а не только таблица;
- руководители, которые хотят стандартизировать формат ответа клиенту.

Как продавать:

- фокус на скорости подготовки, едином формате и снижении ручной сборки
  документов;
- demo лучше строить вокруг "до/после": исходный запрос, черновик сметы,
  КП/PDF, human QA, финальный документ;
- техническую фабрику агентов показывать только после интереса к продукту.

### Strategic ICP: банки, маркетплейсы и интеграторы

Кому подходит:

- банки и fintech-команды, обслуживающие SMB, подрядчиков или строителей;
- marketplace услуг ремонта и строительства;
- интеграторы, которые собирают enterprise workflow вокруг документов;
- construction software или PropTech-команды, где AI-сметы могут стать
  модулем партнёрского продукта.

Как продавать:

- фокус на AI document workflow, лидогенерации, подписках и API-ready
  направлении;
- не обещать enterprise readiness без security review и пилотной архитектуры;
- не раскрывать внутренние server paths, private IP, логи, секреты и сырые
  артефакты.

### Anti-ICP

Сейчас не приоритизировать:

- частных лиц с одной бытовой сметой без повторяемой потребности;
- команды, которым нужен гарантированный нормативный расчёт для госэкспертизы
  или тендера без отдельной методологии и юридической проверки;
- enterprise-клиентов, требующих SOC 2, on-prem, SSO, DPA и security audit до
  любого demo;
- покупателей, которые требуют обещания "AI заменит сметчика";
- рынки, где нет русскоязычных шаблонов, pricebook и документной базы;
- контакты без подтверждённого источника или с неясным правом на обращение.

## 3. Кому продавать подписки

Подписки нужно продавать не "компании вообще", а конкретной роли с бюджетом,
болью и ответственностью за документы.

| Роль покупателя | Что ей важно | Вероятный тариф | Первый ask |
| --- | --- | --- | --- |
| Владелец подрядной компании | Быстрее выпускать КП и не терять сделки | Team или Studio | Demo на реальном обезличенном кейсе |
| Руководитель отдела продаж | Стандартизировать КП и разгрузить сметчика | Team | Проверить 3 типовых сценария |
| Сметчик | Меньше ручной сборки, больше контроля строк | Solo или Team | Сравнить результат с текущей сметой |
| Project manager | Быстро объяснить клиенту объём и стоимость | Team | Получить PDF-пакет для review |
| Дизайн-бюро | Аккуратно оформить первичное предложение | Solo или Team | Demo на типовом ремонте |
| Интегратор | Добавить AI workflow в клиентский процесс | Studio | Discovery по API и границам пилота |

### Solo

Кому продавать:

- индивидуальный сметчик;
- небольшой подрядчик;
- дизайнер или project manager, который сам готовит первые расчёты.

Смысл продажи: личная производительность, быстрые черновики, проверяемая
структура, аккуратный PDF.

Не обещать: что Solo заменит эксперта, даст юридически безошибочные документы
или закроет все региональные прайсбуки.

### Team

Кому продавать:

- отдел продаж;
- малая строительная или ремонтная команда;
- бюро с несколькими менеджерами и одним сметчиком.

Смысл продажи: единый формат, общая очередь документов, меньше ручной
пересборки, контроль итогов и human QA.

Не обещать: автоматическую интеграцию с CRM, 1С, ERP или телефонией без
отдельного scope.

### Studio

Кому продавать:

- строительная компания с несколькими направлениями;
- интегратор;
- marketplace или партнёрская экосистема;
- команда, которой нужен custom onboarding и пилотный контур.

Смысл продажи: пилотный операционный контур, документный workflow,
интеграционная рамка и расширяемость агентной фабрики.

Не обещать: production-grade enterprise SLA, on-prem, compliance certification,
финансовую точность или эксклюзивность без подписанного договора.

## 4. Investor Pipeline

Инвесторский pipeline нужен не для массовой рассылки, а для последовательной
проверки thesis, доказательной базы и fundraising readiness.

### Сегменты инвесторов

| Сегмент | Почему релевантен | Что показывать первым |
| --- | --- | --- |
| AI-native funds | Понимают agentic systems, infra и devtools | EN one-pager, runtime thesis, demo evidence |
| B2B SaaS funds | Оценивают подписки, retention, CAC/LTV | ICP, pricing, первые метрики, roadmap |
| Vertical AI investors | Ищут прикладные AI workflows | Construction estimate wedge, QA, document pack |
| ConstructionTech / PropTech | Понимают рынок смет, тендеров и ремонтов | RU/EN demo, sample estimate, partner angle |
| Fintech / marketplace strategics | Видят каналы и SMB-монетизацию | subscription flow, lead capture, integration note |
| Angels / operators | Могут дать интро, feedback и первые сделки | короткий thesis, ask, конкретный next step |

### Стадии pipeline

| Стадия | Вход | Выход | Следующий шаг |
| --- | --- | --- | --- |
| Research | Есть сегмент, но нет подтверждённого контакта | Найден источник и thesis fit | Ручная верификация |
| Verified | Контакт и канал подтверждены | Можно писать или просить intro | Подготовить персональное сообщение |
| Intro requested | Есть тёплый путь | Получен intro или отказ | Discovery или закрыть |
| First touch ready | Есть источник, сообщение и opt-out footer | Отправка разрешена владельцем | Ручная отправка |
| Replied | Инвестор ответил | Зафиксирован интерес/объект | Discovery call |
| Discovery | Проведён звонок | Понятны метрики и objections | Отправить evidence pack |
| Evidence review | Инвестор смотрит материалы | Есть next ask или no-fit | Follow-up |
| Partner meeting | Запрошен второй разговор | Согласован фокус | Deck/data room readiness |
| Closed/no-fit | Нет текущего интереса | Причина записана | Не продолжать без нового повода |

### Investor qualification

Перед первым касанием заполнить:

- сегмент инвестора;
- thesis fit: agentic AI, devtools, vertical AI, B2B SaaS,
  ConstructionTech, PropTech, fintech или marketplace;
- публичный источник, тёплый intro или событие;
- язык сообщения;
- причина, почему Kolibri релевантен именно этому получателю;
- какой evidence pack можно отправить без раскрытия секретов;
- compliance status: `not_checked`, `ok_to_contact`, `needs_consent`,
  `do_not_contact` или `counsel_review`.

Не писать инвестору, если:

- нет подтверждённого канала;
- контакт был угадан;
- фонд публично не инвестирует в эту стадию, регион или категорию;
- нет честного ответа, что именно просим на первом шаге;
- сообщение содержит terms, valuation, обещание доходности или непроверенные
  traction claims.

## 5. Роли агентов продаж

### Куратор инвесторов и клиентов

Отвечает за весь контур:

- держит ICP, pipeline и messaging;
- проверяет, что контакт не выдуман и не угадан;
- выбирает сегмент, evidence pack и next step;
- следит за запретами на неподтверждённые обещания;
- готовит owner-facing отчёт без персональных данных сверх необходимого.

### Research agent

Задача: найти релевантные компании, фонды, категории и источники без
заполнения неподтверждённых персональных контактов.

Выход:

- название компании или фонда;
- публичная ссылка на источник;
- thesis fit;
- предполагаемый сегмент;
- пометка, что person/email пустые до ручной проверки.

Запрет: генерировать имена людей, email-адреса или LinkedIn URL без источника.

### Contact verification agent

Задача: проверить, что контакт существует, роль актуальна и канал обращения
разрешён.

Выход:

- подтверждённое имя и роль;
- источник и дата проверки;
- канал: public email, form, warm intro, event, inbound или existing
  relationship;
- compliance status;
- красные флаги: bounced, do-not-contact, private-only, outdated role.

### Message drafter

Задача: подготовить персональное сообщение на русском или английском.

Выход:

- subject;
- версия сообщения;
- evidence to send;
- одно конкретное действие: 20-минутное demo, 30-минутный discovery call,
  intro request или permission to send one-pager.

Запрет: отправлять сообщение самостоятельно без явного разрешения владельца.

### CRM operator

Задача: поддерживать pipeline в чистом состоянии.

Выход:

- статус записи;
- next step;
- краткое резюме ответа;
- objections;
- requested artifacts;
- opt-out или do-not-contact отметка.

Запрет: хранить секреты, чувствительные личные данные, приватные документы,
сырые логи и неподтверждённые слухи.

### Demo coordinator

Задача: подготовить безопасный demo-пакет.

Выход:

- обезличенный сценарий;
- список артефактов: estimate JSON, PDF, screenshots, короткое видео;
- human QA disclaimer;
- список известных ограничений.

Запрет: использовать реальные клиентские документы без разрешения и редактуры.

## 6. Шаблоны сообщений

Шаблоны ниже являются черновиками. Они не должны отправляться автоматически.
Перед отправкой нужно проверить контакт, сегмент, язык, источник и право на
обращение.

### RU: первый клиент, подрядчик или ремонтная команда

Subject A: Kolibri для смет и КП в строительных проектах  
Subject B: Быстрое demo AI-сметчика на вашем обезличенном кейсе

Здравствуйте, {first_name}.

Я готовлю первую волну клиентов для Kolibri AI Platform. Это рабочий AI-сервис
для строительных смет и связанных документов: смета, КП, договор, акт, счёт и
PDF-пакет.

Сейчас мы проверяем не абстрактный "AI вместо сметчика", а более практичный
сценарий: быстрее собрать черновик, пересчитать итоги вне модели, показать
audit fingerprint и отдать человеку документ на проверку перед отправкой
клиенту.

Ищу несколько команд, которые готовы дать один реальный, но обезличенный
сметный сценарий и честно сказать, экономит ли это время.

Будет ли уместно показать 20-минутное demo на следующей неделе?

С уважением,  
{sender_name}

Optional footer:  
Коммерческое сообщение. Если это неактуально, ответьте "не писать", и я не
буду обращаться повторно.

### EN: first customer or construction operator

Subject A: Kolibri demo for construction estimates and document packs  
Subject B: Quick demo on one anonymized estimating workflow

Hi {first_name},

I am preparing the first customer wave for Kolibri AI Platform. Kolibri is an
AI workflow product for construction estimates and related documents:
estimates, commercial proposals, contracts, completion acts, invoices and PDF
packs.

The goal is not to claim that AI replaces an estimator. The practical workflow
is simpler: draft the estimate faster, recompute totals outside the model,
show an audit fingerprint and keep a human review step before anything goes to
a client.

I am looking for a small number of teams willing to test one real, anonymized
estimating scenario and give direct feedback on whether this saves time.

Would a 20-minute demo next week be relevant?

Best,  
{sender_name}

Optional footer:  
Commercial outreach. If this is not relevant, reply "do not contact", and I
will not follow up.

### RU: investor intro

Subject A: Kolibri AI: agent runtime + первый вертикальный рынок  
Subject B: Вопрос по agentic AI и строительным workflow

Здравствуйте, {first_name}.

Я строю Kolibri AI Platform: управляемый agent runtime с первым коммерческим
wedge в строительных сметах и документах.

Гипотеза такая: бизнесу нужен не только чат поверх модели, а воспроизводимый
workflow с артефактами, audit trail, подпиской и human QA. Kolibri объединяет
SPA/PWA, Control Plane, агентную фабрику, inter-agent feed, детерминированный
сметный слой и проверяемые document packs.

Я не отправляю инвестиционные условия и не делаю массовую fundraising-рассылку.
Ищу 30-минутный discovery call с инвесторами, которым близки agentic systems,
vertical AI или B2B SaaS.

Будет ли уместно созвониться на следующей неделе?

С уважением,  
{sender_name}

Optional footer:  
Инвесторское/коммерческое сообщение. Если это неактуально, ответьте "не
писать", и я не буду обращаться повторно.

### EN: investor intro

Subject A: Kolibri AI: controllable agent runtime + first vertical wedge  
Subject B: Quick question on agentic AI workflows

Hi {first_name},

I am building Kolibri AI Platform: a controllable agent runtime with a first
commercial wedge in construction estimates and document workflows.

The thesis is that businesses need more than a chat layer on top of a model.
They need reproducible workflows with artifacts, audit trails, subscriptions
and human QA. Kolibri combines a SPA/PWA, Control Plane, agent factory,
inter-agent feed, deterministic estimating layer and verifiable document
packs.

I am not sending investment terms or running a broad fundraising blast. I am
looking for focused 30-minute discovery conversations with investors who
understand agentic systems, vertical AI or B2B SaaS.

Would it be worth a short call next week?

Best,  
{sender_name}

Optional footer:  
Investor/commercial outreach. If this is not relevant, reply "do not contact",
and I will not follow up.

### RU: strategic partner

Subject A: AI workflow для смет, КП и строительных документов  
Subject B: Kolibri как документный AI-слой для строительного процесса

Здравствуйте, {first_name}.

Я готовлю партнёрский контур Kolibri AI Platform. Это AI workflow для смет,
КП, договоров, актов, счетов и PDF-пакетов в строительных и ремонтных
процессах.

Для партнёров Kolibri может быть интересен как подписочный документный слой:
лидогенерация, быстрые черновики, human QA, audit fingerprint и будущий
интеграционный контур.

Сейчас не обещаю enterprise-ready внедрение или готовую сертификацию. Хочу
проверить, есть ли практический партнёрский сценарий и какие требования нужны
для пилота.

Будет ли уместен 30-минутный discovery call?

С уважением,  
{sender_name}

### EN: strategic partner

Subject A: AI workflow for estimates and construction document packs  
Subject B: Kolibri as an AI document layer for construction workflows

Hi {first_name},

I am preparing the partner track for Kolibri AI Platform. Kolibri is an AI
workflow for construction estimates, commercial proposals, contracts,
completion acts, invoices and PDF packs.

For partners, Kolibri may be relevant as a subscription-based document layer:
lead capture, fast drafts, human QA, audit fingerprints and a future
integration path.

I am not claiming enterprise-ready deployment or completed certification at
this stage. I would like to understand whether there is a practical partner
scenario and what requirements would be needed for a pilot.

Would a 30-minute discovery call be relevant?

Best,  
{sender_name}

### RU: follow-up

Subject: Re: Kolibri AI

Здравствуйте, {first_name}.

Коротко напомню про Kolibri. Я писал, потому что ваш профиль выглядит
релевантным для {reason}: строительные workflow, B2B SaaS, vertical AI или
agentic systems.

Если сейчас не момент, всё в порядке. Закрыть вопрос здесь или лучше
обратиться к другому человеку в команде?

С уважением,  
{sender_name}

### EN: follow-up

Subject: Re: Kolibri AI

Hi {first_name},

Quick follow-up on Kolibri. I reached out because your profile looked relevant
to {reason}: construction workflows, B2B SaaS, vertical AI or agentic systems.

If now is not the right time, no worries. Should I close the loop here, or is
there a better person on the team to ask?

Best,  
{sender_name}

## 7. Правила верификации контактов

Каждая CRM-запись должна иметь источник. Нельзя создавать строку с человеком,
email или ролью, если они не подтверждены.

### Разрешённые источники

- официальный сайт компании, фонда или партнёра;
- публичная страница команды;
- публичный профиль в профессиональной сети;
- профиль конференции, акселератора, демо-дня или публичного события;
- inbound-заявка, ответ на форму или сообщение владельцу;
- тёплая интродукция от известного человека;
- существующее отношение, зафиксированное владельцем.

### Минимальный набор полей

До первого касания:

- `record_type`: investor, strategic_partner, customer, advisor или other;
- `company_name`;
- `segment`;
- `source`;
- `source_date`;
- `relationship_path`;
- `compliance_status`;
- `reason_to_contact`;
- `evidence_to_send`;
- `owner`;
- `status`.

Для персонального контакта дополнительно:

- `person_name`;
- `role_title`;
- `verified_channel`;
- `verification_note`;
- `last_verified_at`.

Если `person_name`, `role_title` или `email` не подтверждены, оставить поле
пустым и вести запись на уровне компании.

### Запрещённые практики

- угадывать email по шаблону `first.last@company.com`;
- генерировать имена людей, которых нет в источнике;
- копировать закрытые базы, купленные списки и сомнительные выгрузки;
- писать на личные каналы, если они не опубликованы для деловых обращений;
- обходить opt-out, unsubscribe, bounced или do-not-contact отметки;
- хранить паспортные данные, личные телефоны, домашние адреса и лишние
  персональные данные;
- использовать реальные клиентские документы как demo без разрешения и
  обезличивания.

### Статусы комплаенса

| Статус | Значение | Действие |
| --- | --- | --- |
| `not_checked` | Источник ещё не проверен | Не писать |
| `ok_to_contact` | Канал подтверждён и нет opt-out | Можно готовить ручное касание |
| `needs_consent` | Нужна интродукция или разрешение | Попросить intro или не писать |
| `do_not_contact` | Есть отказ, отписка или красный флаг | Не писать |
| `counsel_review` | Есть юридический или инвестиционный риск | Ждать проверки |

### Перед отправкой сообщения

Проверить:

- контакт существует и роль актуальна;
- источник свежий или дата проверки указана;
- сообщение персонализировано по реальной причине;
- нет непроверенных claims;
- есть opt-out footer для холодного коммерческого касания;
- выбран один понятный ask;
- владелец явно разрешил отправку.

## 8. Запреты на неподтверждённые обещания

Kolibri должен звучать амбициозно, но проверяемо. Любое публичное заявление
должно опираться на demo, тест, артефакт, подписанный договор или явно
помеченную гипотезу.

### Нельзя обещать клиентам

- "AI полностью заменит сметчика";
- "смета всегда точна";
- "документ можно отправлять заказчику без проверки";
- "мы покрываем все регионы, нормы и прайсбуки";
- "интеграция с вашей CRM/ERP/1С уже готова", если она не проверена;
- "подписка активируется production-платежом", если доступен только fallback
  lead mode;
- "PDF/договор юридически безупречен";
- "данные клиента никогда не покинут контур", если это не оформлено
  архитектурно и договорно.

### Нельзя обещать инвесторам

- MRR, ARR, количество клиентов, retention, CAC/LTV без подтверждённых данных;
- valuation, доходность, terms, allocation или сроки раунда без отдельной
  юридической рамки;
- что FormulaLM уже доказан как универсально лучший подход;
- что агентная фабрика production-ready для любого масштаба;
- что GoMesh, внешние компоненты или чужой код принадлежат Kolibri;
- наличие enterprise security certifications, если их нет;
- эксклюзивные партнёрства, LOI, пилоты или revenue, если они не подписаны.

### Допустимые формулировки

- "Kolibri проверяет первый коммерческий wedge в строительных сметах".
- "Расчёты нормализуются и пересчитываются вне модели в текущем сметном
  сценарии".
- "FormulaLM является R&D-направлением, где проверяются валидный JSON,
  стабильность ответа, точные итоги и воспроизводимость".
- "Demo показывает текущие возможности и ограничения продукта".
- "Документы требуют human review перед отправкой клиенту".
- "Подписочная модель готовится вокруг Solo, Team и Studio; конкретный
  billing-status зависит от текущей интеграции".

## 9. Evidence packs

### Для первого клиента

Минимальный пакет:

- короткое описание продукта на русском;
- 3-5 screenshots или короткое demo video;
- обезличенный sample estimate;
- PDF-пакет: смета, КП, договор, акт, счёт;
- human QA disclaimer;
- текущие ограничения и что ещё не поддерживается.

Не прикладывать:

- внутренние логи;
- server paths;
- env-файлы;
- реальные документы другого клиента;
- неподтверждённые pricebook или revenue claims.

### Для инвестора

Минимальный пакет:

- one-pager RU или EN;
- короткий demo или screenshots;
- runtime thesis: SPA/PWA, Control Plane, agent factory, inter-agent feed;
- deterministic estimate evidence;
- Product QA summary;
- FormulaLM note как R&D, не как доказанный moat;
- roadmap и список метрик, которые ещё нужно собрать.

Не прикладывать на первом касании:

- full data room;
- cap table;
- securities terms;
- неотредактированные финансовые модели;
- секреты, токены, private URLs и raw logs.

## 10. CRM pipeline fields

| Field | Type | Notes |
| --- | --- | --- |
| `record_id` | string | Внутренний ID. |
| `record_type` | enum | `investor`, `customer`, `strategic_partner`, `advisor`, `other`. |
| `company_name` | string | Компания, фонд, бюро, подрядчик или партнёр. |
| `person_name` | string | Только после проверки. |
| `role_title` | string | Только после проверки. |
| `segment` | enum | ICP или investor segment. |
| `priority` | enum | `P0`, `P1`, `P2`, `P3`. |
| `geo` | string | Регион или страна. |
| `language` | enum | `RU`, `EN`, `mixed`. |
| `source` | string | Обязательная ссылка или описание источника. |
| `source_date` | date | Когда источник проверен. |
| `relationship_path` | enum | `warm_intro`, `inbound`, `event`, `public_email`, `existing_relationship`, `manual_research`. |
| `verified_channel` | string | Email, форма, intro или другой подтверждённый канал. |
| `verification_note` | text | Кто и как подтвердил контакт. |
| `compliance_status` | enum | `not_checked`, `ok_to_contact`, `needs_consent`, `do_not_contact`, `counsel_review`. |
| `thesis_fit` | multi-select | `agentic_ai`, `devtools`, `vertical_ai`, `constructiontech`, `proptech`, `b2b_saas`, `fintech`, `marketplace`. |
| `customer_fit` | multi-select | `contractor`, `renovation_team`, `design_bureau`, `sales_department`, `integrator`, `bank`, `marketplace`. |
| `evidence_to_send` | multi-select | `one_pager`, `demo`, `screenshots`, `sample_estimate`, `pdf_pack`, `factory_note`, `billing_note`, `product_qa`. |
| `status` | enum | `research`, `verified`, `ready`, `sent_1`, `sent_2`, `replied`, `meeting_booked`, `evidence_sent`, `not_fit`, `do_not_contact`, `closed`. |
| `last_touch_at` | datetime | Последнее касание. |
| `next_step_at` | datetime | Следующий шаг. |
| `last_message_template` | enum | `customer_intro`, `investor_intro`, `strategic_partner`, `follow_up`, `custom`. |
| `reply_summary` | text | Нейтральное краткое резюме. |
| `objections` | multi-select | `too_early`, `no_budget`, `no_traction`, `needs_demo`, `needs_security`, `pricing`, `integration`, `legal`, `not_focus`. |
| `requested_artifacts` | multi-select | Что попросили прислать. |
| `consent_or_opt_out` | enum | `none`, `consented`, `unsubscribed`, `bounced`, `objected`. |
| `owner` | string | Ответственный оператор. |
| `notes_private` | text | Без секретов и лишних персональных данных. |

## 11. Недельный операционный цикл

### День 1: подготовка

- выбрать 5-10 компаний или фондов по сегменту;
- заполнить записи на уровне компании;
- не заполнять персональные контакты без источника;
- выбрать evidence pack;
- отметить, какие документы требуют обновления.

### День 2: верификация

- проверить людей, роли и каналы;
- убрать все guessed contacts;
- проставить compliance status;
- подготовить персональные причины обращения.

### День 3: сообщения

- подготовить 3-5 ручных сообщений;
- дать владельцу на review;
- не отправлять без явного разрешения;
- после разрешения фиксировать `last_touch_at`.

### День 4: discovery и demo

- проводить только короткие calls с понятным ask;
- записывать objections и requested artifacts;
- не спорить с no-fit;
- не обещать features или сроки без подтверждения команды.

### День 5: отчёт

- обновить pipeline;
- посчитать replies, meetings, objections, evidence requests;
- выписать, какие claims требуют проверки;
- предложить следующий маленький batch.

## 12. Acceptance checklist

Перед тем как использовать pipeline:

- ICP первых клиентов понятен и отделён от anti-ICP;
- подписки продаются конкретным ролям, а не абстрактному рынку;
- инвесторский pipeline не содержит выдуманных контактов;
- есть роли агентов продаж и их запреты;
- есть шаблоны сообщений на русском и английском;
- есть правила верификации контактов;
- есть запреты на неподтверждённые promises;
- external sending остаётся ручным и только после разрешения владельца;
- код, секреты, env-файлы и приватные логи не трогаются.

