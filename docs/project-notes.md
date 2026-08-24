# RateScout — карта проекта (project-notes)

🟢 **В ПРОДЕ:** https://ratescout.ru · репозиторий: github.com/sementsul/ratescout (публичный, GitHub Pages)

Статический SEO-сайт-справочник курсов обмена крипты/валют на базе реф-программы **BestChange** (ref `p=1116359`).

## Что где
| Файл | Назначение |
|---|---|
| `build.py` | генератор статики → `dist/` (~1110 стр.), **две локали** RU (`/`) + EN (`/en/`). Типы страниц на локаль: главная · 330 валют (`/valuta/`, +живая таблица курсов, калькулятор суммы, SVG-график динамики, «похожие валюты») · ~183 пары (`/obmen/`: top.json + высокоинтентные крипта→рубли) · 6 категорийных хабов (`/kategoriya/`) · 10 банковских хабов (`/na/<банк>/`, крипта→получатель) · блог с пагинацией и сквозным поиском (`/blog/`, `/blog/page/N/`) · FAQ (`/faq/`) · редакция (`/redakciya/`) · комплаенс · 404. Разметка: WebSite/Organization/BreadcrumbList/FAQPage/Article/WebPage(dateModified)/HowTo/ItemList. Плюс sitemap(+hreflang)/robots/manifest/sw/RSS(`/blog/rss.xml`)/IndexNow-ключ/og-image. Ассеты с кеш-бастингом `?v=<md5>` |
| `fetch_rates.py` | из дампа `api.bestchange.ru/info.zip` (без ключа): синхрон `currencies.json` (bm_cy.dat) + `rates.json` (bm_rates.dat, +`generated_at`) + топ-пары `top.json` (bm_top.dat) |
| `history.py` | почасовой снимок «цены в USDT» топ-валют → `history.json` (для SVG-графиков); в CI коммитится обратно `[skip ci]` |
| `indexnow.py` | POST списка URL из sitemap в IndexNow (Яндекс/Bing) — в CI только на push, не на cron |
| `parse_catalog.py` | разовый парсер каталога из сохранённого HTML (первичный сид; дальше каталог обновляет fetch_rates) |
| `currencies.json` | каталог валют (slug→{id,name,ticker,category[,num]}); в CI обновляется в раннере |
| `data.json` | `site`: name/domain/ref/owner/owner_inn/owner_email/tagline |
| `articles/` | RU markdown-статьи блога (frontmatter title/description/date/slug); `articles/en/` — EN-переводы с теми же слагами |
| `assets/` | styles.css (тема doshaven), app.js (конвертер+фильтр), catalog.js (генерится), monitor.js (про-монитор `/monitor/`), favicon.svg (⇄), og-image.png (1200x630 баннер) |
| `assets/monitor.js` + `data/monitor.json` | страница `/monitor/` (RU+EN): SVG-терминал — много валют на одной шкале, выбор базы (умолч. доллар/USDT) и типа (линии/свечи), диапазоны, справа чекбоксы валют. Данные `monitor.json` кладёт `make_monitor_json()` в build.py. Детали — UC-107 |
| `.github/workflows/deploy.yml` | ежечасный cron: fetch_rates → history.py → build → guard(ключ не в dist) → deploy на Pages → (push) IndexNow; коммит history.json обратно (`contents:write`, `[skip ci]`) |
| `.github/workflows/keepalive.yml` | еженедельный heartbeat против 60-дн отключения cron — 🔴 пушит под PAT (секрет GH_PAT), т.к. бот-коммиты таймер НЕ сбрасывают (UC-106) |
| `.github/workflows/watchdog.yml` | ежедневный сторож автономности: тянет `history.json` из raw (без checkout), возраст свежайшей точки > 8ч → оповещение в 2 канала: **Telegram** в личный чат (`TELEGRAM_TOKEN`+`ALERT_CHAT_ID`) + **падение прогона** → письмо от GitHub. Ловит: заснувший крон (истёк PAT), сломанный BestChange, падение сборки (UC-108) |
| `.github/dependabot.yml` | еженедельно (пн) следит за версиями GitHub Actions, открывает сгруппированный PR при обновлении (UC-109) |
| `.github/workflows/dependabot-automerge.yml` | safe авто-мёрж Dependabot-PR: minor/patch — авто (`gh pr merge --auto`), major — на ручной клик (UC-109) |
| `.github/workflows/yandex-recrawl.yml` + `yandex_recrawl.py` | переобход ключевых URL в Яндекс.Вебмастере (`YANDEX_OAUTH_TOKEN`, суточная квота) + ТГ-сводка. 🔧 ТОЛЬКО `workflow_dispatch` (вручную/при ошибке обхода) — еженедельное расписание убрано (UC-110) |

## Запуск / деплой
```bash
python3 build.py                 # локальная сборка в dist/
python3 -m http.server 8000 -d dist   # локальное превью (на github.io ассеты 404 — абсолютные пути; на домене ОК)
```
Прод: пуш в `main` → GitHub Actions собирает и деплоит. Пуш локально:
`git push https://<token>@github.com/sementsul/ratescout.git HEAD:main` (ветка бывает detached из-за heartbeat-коммитов бота).

## Ключевые решения
- **Автообновление на этапе сборки** (Actions), не в браузере → совместимо с Pages. Курсы + список валют синхронятся с BestChange ежечасно, **без API-ключа** (публичный дамп).
- **Категории** валют — из поля 5 `bm_cy.dat` (0=Крипта,1=Digital,2=Bank cards,3=Online banking,4=Money transfers,5=Cash), сверено 1:1.
- **Deep-links:** существующие — слаг `/<a>-to-<b>.html?p=`; новые (флаг `num`) — числовой `index.php?from=&to=&p=`.
- **330 страниц валют** вместо ~109k пар: на каждой валюте — все направления ссылками.
- **Правовой статус — информационный ресурс** (ОРД/ERID НЕ применяем): нейтральный тон, оценочные слова вычищены, AML-блок справочный (без кнопки оплаты). Оператор: самозанятый (НПД) Семенцул М.Г., ИНН 381616884622.
- **Ключ BestChange** (если использовать партнёрский API вместо дампа) — только `.env`/GitHub Secret, guard в CI не пускает в `dist`.
- **i18n:** RU в корне, EN в `/en/` (тот же контент, локализованы UI + описания категорий + комплаенс + блог). Данные (курсы/каталог/пары) общие. **Асимметрия покрытия:** EN-направления рендерятся только для `PAIR_PAGES` (714), RU — ещё `PAIR_PAGES_RU` (всего 19 190); наборы статей блога RU/EN тоже различаются (в т.ч. из-за дрип-релизов по датам). Поэтому `hreflang`/переключатель/автоязык **условны** (см. ниже) — не рекламируем версию, которой нет.
- **Реестр отсутствующих переводов:** `NO_EN`/`NO_RU` (в build.py после `ARTS`) — множества путей без версии на данном языке (RU-only направления ∪ RU-only статьи; плюс `/404`). `hreflangs(path)` пропускает отсутствующий язык и ставит корректный `x-default`; `header()` прячет кнопку `.langsw`, если версии на другом языке нет. 🔴 Иначе — 18 476 битых `hreflang="en"` + мёртвая кнопка «EN» → 404 (был симптом, чинили).
- **Автоязык (клиент):** `LANGREDIR` — ранний inline-скрипт в `<head>`: нет `localStorage.rs_lang` → редирект на язык браузера (`ru*`→`/`, иначе→`/en/`, путь сохраняется). Клик по `.langsw` сохраняет `rs_lang` (ручной выбор перекрывает авто). Боты не редиректятся (SEO). 🔴 **Стоп-редирект:** на странице без версии на др. языке `head()` ставит `window.RS_NOTR=1` ПЕРЕД скриптом, и `LANGREDIR` сразу `return` — иначе EN-браузер на RU-only направлении жёстко редиректился в 404. Статика Pages серверного редиректа не умеет — только так.
- **Поиск по валютам** — DOS-бокс `#search` в сайдваре ПОД калькулятором (главная + страницы валют); фильтр по `catalog.js` в `app.js`, ссылки учитывают языковой префикс (`data-prefix`). Порядок скриптов: `catalog.js` ПЕРЕД `app.js` (иначе `window.__CATALOG__` undefined → поиск мёртв — так и было сломано).
- **Поиск по блогу** — поле `#bq` на `/blog/` (DOS-бокс `.dosblue.dosborder`, единый стиль); `app.js` фильтрует `<li>` списка `#bloglist` по атрибуту `data-search` (заголовок+описание+слаг), пустой результат → блок `#bnores`. Без индекса — фильтрация уже отрендеренного DOM (статей мало).
- **Мобильная раскладка:** на ≤760px `#main` → flex-column, `#sidebar{order:-1}` — калькулятор+поиск поднимаются НАД каталогом (в разметке sidebar идёт после content, иначе уезжал в самый низ). Десктоп (floats) не затронут.
- **Кеш-бастинг ассетов:** к `styles.css`/`app.js`/`catalog.js` в ссылках добавлен `?v=<md5-хеш содержимого>` (`VER` в build.py, заполняется в `main()` до рендера). Путь файла стабильный → браузер/Pages кешируют; хеш меняется только при правке файла и заставляет подхватить новую версию. 🔴 Без этого правки JS/CSS «не видны» из-за кеша (был симптом «поиск не работает / не по дизайну» — на самом деле старый app.js/styles.css из кеша).
- **Данные BestChange латиницей:** названия банков/валют в дампе на английском (`Sberbank`, не «Сбербанк») → поиск по кириллице таких имён не найдёт (ограничение источника, не баг).

## Грабли (не наступать снова)
- Парсинг: **проверять вывод ПЕРЕД удалением источника**; смотреть реальные байты (файл каталога был сохранён как DevTools-подсветка, не обычный HTML).
- `catalog.js` затирался `copy_assets()` → писать ПОСЛЕ копирования.
- CI-guard `grep -F "$KEY"` при пустом ключе матчит всё → `[ -n "$KEY" ] &&`.
- Абсолютные пути (`/assets`,`/valuta`) корректны только на корне домена (ratescout.ru), на github.io/ratescout — 404.
- **Не рекламируй страницу, которой нет:** `hreflang`/переключатель/автоязык генерились безусловно для обоих языков, а EN-направлений собрано 714 из 19 190 → 18 476 битых `hreflang="en"` + мёртвая «EN» + жёсткий авто-редирект EN-браузеров в 404. Любой кросс-язык-элемент гейтить через `NO_EN`/`NO_RU`. Аналогично мёртвая ссылка `/blog/halving-bitcoin/` — статья в дрипе (`release: 2027`), линковалась безусловно; ссылки на статьи гейтить через `PUB_SLUGS`.

## Статус и что дальше
Всё живое: домен+HTTPS, аналитика (Метрика 111586112 + GA G-PPN27D6JXS), Яндекс.Вебмастер + **Google Search Console** подключены, sitemap отправлен. SEO-каркас сильно расширен (i18n RU/EN, ~1110 стр., хабы категорий/банков, блог 17 статей с пагинацией+сквозным поиском, живые таблицы/калькулятор/SVG-графики истории, HowTo/ItemList/WebPage-разметка, IndexNow, RSS, страница редакции для E-E-A-T, 404, preconnect). **Дальнейший рост — оффсайт** (ссылки/Telegram/Q&A): материалы в `dropzone/uploads/marketing-kit/` (сервер дропзоны на :8000). Оффсайт делает пользователь; ассистент готовит контент. Опционально: динамические OG-картинки, словарь терминов отдельными страницами, cookie-баннер (ЕС).

Живой список сценариев/радиуса — `docs/ratescout.usecases.md`.

- **UC-115: GEO (Generative Engine Optimization) — 2026-08-24.** `robots.txt` теперь содержит ЯВНЫЕ Allow-блоки для AI/answer-краулеров (GPTBot/OAI-SearchBot/ChatGPT-User/ClaudeBot/Claude-Web/anthropic-ai/PerplexityBot/Perplexity-User/Google-Extended/Applebot-Extended/CCBot/Amazonbot/Bytespider/YandexAdditional) — сигнал намерения для генеративных движков (раньше был только `*: Allow /`, разрешало неявно). `llms.txt` уже был (`write_llms()`), JSON-LD (Organization/WebSite/Dataset/FAQPage) на месте — заход был точечный. Проверено: `python3 build.py` EXIT 0, dist/robots.txt валиден.

- **UC-116: GEO answer-first на страницах валют.** `render_currency` теперь ведёт датированным data-абзацем `<p class="answer">` (живой курс+изм.+число направлений из HISTORY/DIRS_BY_CUR) — первый экстрактируемый факт для AI-движков. Стейблы/без истории — фолбэк без курса; EN — свой счёт пар. Пары (`render_pair`) — следующий кандидат.
