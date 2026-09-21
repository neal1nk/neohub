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
4. На аккаунте уже может быть один free Postgres — Blueprint **не** создаёт вторую БД.
   Подключи существующую: Postgres → **Connect** → **Internal Database URL** → в Web Service → **Environment** → `DATABASE_URL`.
5. Также задай:

| Key | Value |
|-----|--------|
| `DJANGO_ALLOWED_HOSTS` | `ghub-xxxx.onrender.com` (твой URL без https) |
| `CSRF_TRUSTED_ORIGINS` | `https://ghub-xxxx.onrender.com` |

`DJANGO_SECRET_KEY` / `DJANGO_DEBUG` подставляются из Blueprint.

6. Дождись успешного Deploy (Build + migrate).

> Если free Postgres недоступен — Starter на Render или Neon (https://neon.tech) и вставь `DATABASE_URL`.

## 3. Первый вход (без Shell)

На free-плане **Shell недоступен**. Один раз задай в Environment:

| Key | Value |
|-----|--------|
| `BOOTSTRAP_TEACHER_USERNAME` | `teacher` |
| `BOOTSTRAP_TEACHER_PASSWORD` | свой пароль |
| `BOOTSTRAP_TEACHER_NAME` | `Кирилл` |

Сохрани → дождись redeploy → в **Build Logs** найди строки «Преподаватель создан» и «Код создан».

Потом **удали** `BOOTSTRAP_TEACHER_PASSWORD` из Environment (иначе пароль будет сбрасываться на каждый билд).

Открой сайт → логин преподавателя → проверь кабинет и загрузку файла.

## 4. Важно

- Локальная SQLite **не** копируется на Render — база пустая.
- Файлы на free-плане **временные** (пропадут при редеплое). Позже — S3/R2.
- При CSRF-ошибках проверь `CSRF_TRUSTED_ORIGINS` (с `https://`).
