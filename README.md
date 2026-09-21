# NeoHub

Платформа для персональной работы преподавателя с учениками: теория, домашние задания, практика и зачёты. 100-балльная рейтинговая система.

## Стек

- Django 5 + Django Auth
- Шаблоны + HTMX/Alpine + кастомный CSS
- SQLite локально, PostgreSQL в проде
- Gunicorn + WhiteNoise

## Запуск в PyCharm

1. Interpreter: `.venv` проекта.
2. Установите зависимости (если ещё не стоят):

```bash
.\.venv\Scripts\pip.exe install -r requirements.txt
```

3. Скопируйте `.env.example` → `.env` (для локальной разработки достаточно значений по умолчанию).
4. Миграции и аккаунт преподавателя:

```bash
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py bootstrap_teacher --username teacher --password teacher123 --name "Кирилл"
```

5. Run Configuration в PyCharm:
   - Script path: `manage.py`
   - Parameters: `runserver`
   - Working directory: корень проекта

6. Откройте http://127.0.0.1:8000/  
   Логин преподавателя: `teacher` / `teacher123`

## Как пользоваться

**Преподаватель**
- Создаёт ученика (ФИО, логин, пароль) и передаёт данные лично.
- Открывает карточку ученика → вкладки Теория / Домашки / Практика / Зачёты.
- Выдаёт материалы и задания с дедлайном, проверяет сдачи и ставит оценку.

**Ученик**
- Входит по выданному логину.
- Смотрит теорию, сдаёт задания, видит оценки и комментарии.

## Деплой на Render

1. Создайте репозиторий и запушьте проект.
2. На [Render](https://render.com) используйте `render.yaml` (Blueprint) или создайте Web Service + PostgreSQL вручную.
3. Env-переменные:
   - `DJANGO_SECRET_KEY` — длинная случайная строка
   - `DJANGO_DEBUG=False`
   - `DJANGO_ALLOWED_HOSTS=your-app.onrender.com`
   - `CSRF_TRUSTED_ORIGINS=https://your-app.onrender.com`
   - `DATABASE_URL` — из Render Postgres
4. Build:

```bash
pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate
```

5. Start: `gunicorn ghub.wsgi:application`
6. После деплоя один раз выполните в Shell Render:

```bash
python manage.py bootstrap_teacher --username teacher --password 'СменитеПароль'
```

## Railway (альтернатива)

1. New Project → Deploy from GitHub.
2. Добавьте PostgreSQL plugin (подставит `DATABASE_URL`).
3. Задайте те же env-переменные, что выше.
4. Start command: `gunicorn ghub.wsgi:application`

## Важно про файлы

Локально файлы хранятся в `media/`. На бесплатном Render диск эфемерный — для постоянных загрузок позже подключите S3/R2 или persistent disk.
