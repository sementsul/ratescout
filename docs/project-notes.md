# RateScout — карта проекта (project-notes)

🟢 **В ПРОДЕ:** https://ratescout.ru · репозиторий: github.com/sementsul/ratescout (публичный, GitHub Pages)

Статический SEO-сайт-справочник курсов обмена крипты/валют на базе реф-программы **BestChange** (ref `p=1116359`).

## Что где
| Файл | Назначение |
|---|---|
| `build.py` | генератор статики → `dist/`: **две локали** RU (корень `/`) + EN (`/en/`). На каждую: главная + 330 валют (/valuta/) + 100 пар (/obmen/, из top.json) + блог (/blog/, из articles/ и articles/en/) + комплаенс. Плюс общие sitemap (обе локали, +hreflang)/robots/manifest/sw + og-image |
| `fetch_rates.py` | из дампа `api.bestchange.ru/info.zip` (без ключа): синхрон `currencies.json` (bm_cy.dat) + `rates.json` (bm_rates.dat) + топ-пары `top.json` (bm_top.dat) |
| `parse_catalog.py` | разовый парсер каталога из сохранённого HTML (первичный сид; дальше каталог обновляет fetch_rates) |
| `currencies.json` | каталог валют (slug→{id,name,ticker,category[,num]}); в CI обновляется в раннере |
| `data.json` | `site`: name/domain/ref/owner/owner_inn/owner_email/tagline |
| `articles/` | RU markdown-статьи блога (frontmatter title/description/date/slug); `articles/en/` — EN-переводы с теми же слагами |
| `assets/` | styles.css (тема doshaven), app.js (конвертер+фильтр), catalog.js (генерится), favicon.svg (⇄), og-image.png (1200x630 баннер) |
| `.github/workflows/deploy.yml` | ежечасный cron: fetch_rates → build → deploy на Pages (guard: ключ не в dist) |
| `.github/workflows/keepalive.yml` | еженедельный heartbeat против 60-дневного отключения cron |

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
- **i18n:** RU в корне, EN в `/en/` (тот же контент, локализованы UI + описания категорий + комплаенс + блог). Между версиями — `hreflang` (ru/en/x-default) и переключатель языка `.langsw` в шапке. Данные (курсы/каталог/пары) общие. Слаги статей EN совпадают с RU (стабильные кросс-ссылки).
- **Автоязык (клиент):** `LANGREDIR` — ранний inline-скрипт в `<head>`: нет `localStorage.rs_lang` → редирект на язык браузера (`ru*`→`/`, иначе→`/en/`, путь сохраняется). Клик по `.langsw` сохраняет `rs_lang` (ручной выбор перекрывает авто). Боты не редиректятся (SEO). Статика Pages серверного редиректа не умеет — только так.
- **Поиск по валютам** — DOS-бокс `#search` в сайдваре ПОД калькулятором (главная + страницы валют); фильтр по `catalog.js` в `app.js`, ссылки учитывают языковой префикс (`data-prefix`). Порядок скриптов: `catalog.js` ПЕРЕД `app.js` (иначе `window.__CATALOG__` undefined → поиск мёртв — так и было сломано).
- **Данные BestChange латиницей:** названия банков/валют в дампе на английском (`Sberbank`, не «Сбербанк») → поиск по кириллице таких имён не найдёт (ограничение источника, не баг).

## Грабли (не наступать снова)
- Парсинг: **проверять вывод ПЕРЕД удалением источника**; смотреть реальные байты (файл каталога был сохранён как DevTools-подсветка, не обычный HTML).
- `catalog.js` затирался `copy_assets()` → писать ПОСЛЕ копирования.
- CI-guard `grep -F "$KEY"` при пустом ключе матчит всё → `[ -n "$KEY" ] &&`.
- Абсолютные пути (`/assets`,`/valuta`) корректны только на корне домена (ratescout.ru), на github.io/ratescout — 404.

## Статус и что дальше
Всё живое: домен+HTTPS, аналитика (Метрика 111586112 + GA G-PPN27D6JXS), Вебмастер-verification, sitemap отправлен в GSC/Яндекс. Опционально: cookie-баннер (ЕС), доп. микроразметка, расширение браузера/macOS-приложение (из старого плана).

Живой список сценариев/радиуса — `docs/ratescout.usecases.md`.
