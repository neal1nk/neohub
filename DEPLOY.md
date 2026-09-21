# Деплой NeoHub на Render

## 0. Уже сделано в коде

- `/media/` отдаётся и в production ([`ghub/urls.py`](ghub/urls.py))
- `MEDIA_ROOT` создаётся автоматически
- Blueprint: [`render.yaml`](render.yaml)
- Локальный git-репозиторий инициализирован, первый коммит готов

## 1. Запушить на GitHub

1. Открой https://github.com/new
2. Имя репозитория: `neohub` (или любое), **без** README
3. Создай репозиторий и выполни в PowerShell из папки проекта:

```powershell
$git = "$env:LOCALAPPDATA\Programs\git-portable\cmd\git.exe"
cd C:\Users\kozlo\PycharmProjects\Bhub
& $git remote add origin https://github.com/ТВОЙ_ЛОГИН/neohub.git
& $git push -u origin main
```

(GitHub попросит войти / Personal Access Token.)

Или через GitHub CLI после `gh auth login`:

```powershell
gh repo create neohub --private --source=. --remote=origin --push
```

## 2. Render Blueprint

1. Зайди на https://dashboard.render.com
2. **New** → **Blueprint** → подключи GitHub-репозиторий
3. Выбери `render.yaml`
4. После создания сервиса открой Web Service → **Environment** и задай:

| Key | Value |
|-----|--------|
| `DJANGO_ALLOWED_HOSTS` | `ghub-xxxx.onrender.com` (твой URL без https) |
| `CSRF_TRUSTED_ORIGINS` | `https://ghub-xxxx.onrender.com` |

`DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DATABASE_URL` подставляются из Blueprint.

5. Дождись успешного Deploy (Build + migrate).

> Если free Postgres недоступен в регионе — создай Postgres вручную (Starter) или бесплатный Neon (https://neon.tech) и вставь `DATABASE_URL` в env.

## 3. Первый вход (Render Shell)

**Shell** у Web Service:

```bash
python manage.py bootstrap_teacher --username teacher --password 'СмениПарольСразу' --name "Кирилл"
python manage.py create_activation_code
```

Открой сайт → логин преподавателя → проверь кабинет и загрузку файла.

## 4. Важно

- Локальная SQLite **не** копируется на Render — база пустая.
- Файлы на free-плане **временные** (пропадут при редеплое). Позже — S3/R2.
- При CSRF-ошибках проверь `CSRF_TRUSTED_ORIGINS` (с `https://`).
