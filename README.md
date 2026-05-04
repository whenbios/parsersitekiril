# Work.ua Contact Enrichment MVP

Простой backend и mini web app для проверки пайплайна:

`Work.ua -> официальный сайт компании -> контакты в Google Sheet`

Теперь в проекте есть и легкий web UI:
- загрузка `.xlsx`/`.csv`
- запуск enrichment без Google Sheets
- таблица с `best contact / backup / Work.ua fallback`
- раскрытие полной карточки компании по клику

## Что умеет MVP

- принимает строки с `company_name` и `workua_url`;
- открывает страницу Work.ua;
- пытается найти официальный сайт компании;
- обходит ограниченный набор страниц сайта;
- собирает email, Telegram, телефоны, соцсети и прочие явные контактные ссылки;
- возвращает результат в плоском формате, удобном для Google Sheet.

## Локальный запуск backend

1. Создай `.env.local` рядом с `pyproject.toml`:

```env
WORKUA_DB_PATH=:memory:
ZYTE_API_KEY=your_zyte_key
PORT=8000
```

Можно взять шаблон из [.env.example](/d:/project/parsersitekiril/.env.example).

```bash
python -m pip install -e .[dev]
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

Если задан `ZYTE_API_KEY`, backend будет ходить через Zyte API. Если ключа нет, используется обычный HTTP fetch с тем же интерфейсом.

После запуска открой:

`http://127.0.0.1:8000/`

Там будет web UI для загрузки файла или вставки `Work.ua` ссылок.

## API

- `POST /companies/enrich`
- `POST /jobs/start`
- `POST /jobs/upload`
- `GET /jobs/{job_id}/status`
- `GET /jobs/{job_id}/results`

Пример `POST /companies/enrich`:

```json
{
  "company_name": "Acme",
  "workua_url": "https://www.work.ua/jobs/by-company/1/"
}
```

## Web UI

Главная таблица в UI показывает:
- `Company`
- `Website`
- `Best contact`
- `Backup contact`
- `Work.ua fallback`
- `Status`

Карточка компании по клику показывает:
- лучшие контакты
- все найденные контакты сайта
- fallback-контакты из `Work.ua`
- технические заметки

## Google Sheets

Скрипт лежит в [apps_script/ContactEnrichment.gs](/d:/project/parsersitekiril/apps_script/ContactEnrichment.gs).

1. Создай Google Sheet с колонками:
   - `company_name`
   - `workua_url`
   - `website`
   - `email_1`
   - `email_2`
   - `email_3`
   - `telegram_1`
   - `telegram_2`
   - `telegram_3`
   - `phone_1`
   - `phone_2`
   - `phone_3`
   - `instagram`
   - `facebook`
   - `linkedin`
   - `other_links`
   - `status`
   - `error`
   - `last_checked`
2. Открой `Extensions -> Apps Script`.
3. Вставь содержимое `apps_script/ContactEnrichment.gs`.
4. Замени `API_BASE_URL` на адрес развернутого backend.
5. Обнови таблицу и используй меню `Contact Enrichment`.

Рекомендуемые колонки для более полезного outreach-результата:
- `general_email`
- `marketing_email`
- `manager_email`
- `whatsapp`
- `viber`
- `main_phone`

## Ограничения первой версии

- Zyte browser fallback включается только когда обычный fetch страницы падает;
- staged crawl сначала проверяет `contacts/contact`, затем `about`, затем дополнительные страницы;
- job-ы обрабатываются синхронно внутри запроса `/jobs/start`;
- нет deep crawl, ranking и confidence score;
- при большом количестве найденных значений сохраняются только первые 3 email, 3 Telegram и 3 телефона.

## Vercel Deploy

По официальной документации Vercel, FastAPI можно деплоить без сложной конфигурации, если экспортируется корневой `app` entrypoint и статика лежит в `public/`.

Что сделать:
1. Залить проект в GitHub.
2. Импортировать репозиторий в Vercel.
3. В Environment Variables задать:
   - `ZYTE_API_KEY`
   - `WORKUA_DB_PATH=:memory:`
4. Нажать Deploy.

Источники:
- https://vercel.com/docs/frameworks/backend/fastapi
- https://vercel.com/docs/project-configuration/vercel-json

Примечание:
- текущая версия использует in-memory хранилище как самый простой вариант для демо;
- для постоянных job-ов и истории на Vercel лучше позже вынести storage в Postgres/Redis.
