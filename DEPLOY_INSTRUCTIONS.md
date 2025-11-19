# Инструкция по деплою бота на Render

## Шаг 1: Узнай свой Telegram ID
1. Открой Telegram
2. Найди бота @userinfobot
3. Нажми Start
4. Скопируй свой ID (число)

## Шаг 2: Создай репозиторий на GitHub
1. Зайди на github.com и войди в свой аккаунт
2. Нажми зеленую кнопку "New" (или "New repository")
3. Название репозитория: youth-feedback-bot
4. Выбери "Public" (публичный)
5. НЕ добавляй README, .gitignore или license (они уже есть)
6. Нажми "Create repository"

## Шаг 3: Загрузи файлы на GitHub
GitHub покажет инструкции. Тебе нужен вариант "uploading an existing file":

1. Нажми "uploading an existing file"
2. Перетащи ВСЕ файлы из папки youth_feedback_bot:
   - bot.py
   - database.py
   - config.py
   - requirements.txt
   - Procfile
   - README.md
   - .gitignore
3. В поле "Commit changes" напиши: "Initial commit"
4. Нажми "Commit changes"

## Шаг 4: Деплой на Render
1. Зайди на render.com
2. Войди через GitHub аккаунт (Sign in with GitHub)
3. Нажми "New +" в правом верхнем углу
4. Выбери "Background Worker" (не Web Service!)
5. Найди свой репозиторий youth-feedback-bot и нажми "Connect"

## Шаг 5: Настройка на Render
1. Name: youth-feedback-bot
2. Region: выбери ближайший (например Frankfurt для Украины)
3. Branch: main
4. Root Directory: оставь пустым
5. Runtime: Python 3
6. Build Command: `pip install -r requirements.txt`
7. Start Command: `python bot.py`

## Шаг 6: Environment Variables (Переменные окружения)
Нажми "Add Environment Variable" и добавь ДВЕ переменные:

1. Первая переменная:
   - Key: BOT_TOKEN
   - Value: ***REVOKED_TOKEN***

2. Вторая переменная:
   - Key: ADMIN_ID
   - Value: [ТВОЙ TELEGRAM ID - УЗНАЙ ЧЕРЕЗ @userinfobot]

## Шаг 7: Выбор плана
1. Instance Type: выбери "Free" (бесплатный)
2. Нажми "Create Background Worker"

## Шаг 8: Ожидание деплоя
Render начнет деплой. Это займет 2-5 минут.
Ты увидишь логи - должно появиться "Bot started!"

## Шаг 9: Проверка работы
1. Открой Telegram
2. Найди своего бота @KBC_Youth_Feedback_Bot
3. Напиши /start
4. Бот должен ответить!

## Возможные проблемы:

**Бот не отвечает:**
- Проверь что на Render статус "Running" (зеленый)
- Проверь что BOT_TOKEN правильный
- Посмотри логи на Render (вкладка Logs)

**Бот отвечает но команды не работают:**
- Проверь что ADMIN_ID правильный
- Попробуй узнать ID через @userinfobot еще раз

**"Free instance will spin down with inactivity":**
- Это нормально для бесплатного плана
- Бот "заснет" после 15 минут без активности
- Проснется когда кто-то напишет (может быть задержка 30 сек)

## Важные заметки:

1. На бесплатном плане Render может быть задержка в ответах
2. Если нужна стабильная работа 24/7 - переключись на платный план ($7/месяц)
3. База данных будет сбрасываться при каждом деплое на бесплатном плане
4. Для продакшна лучше использовать внешнюю БД (PostgreSQL)

## Следующие шаги после запуска:

1. Добавь себя как пользователя (напиши /start боту)
2. Одобри себя через /pending
3. Добавь других участников молодежи
4. Проведи тестовый опрос через /start_survey

Удачи! 🙏
