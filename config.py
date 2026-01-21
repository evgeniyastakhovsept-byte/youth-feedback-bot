import os

# Токен бота - будет браться из переменной окружения на Render
BOT_TOKEN = os.getenv('BOT_TOKEN', '8436930061:AAENovndUoU78XH1OxcTEJYwUlrNPvWFqTw')

# ID администратора (твой Telegram ID)
ADMIN_ID = int(os.getenv('ADMIN_ID', '1125355606'))

# Время на оценку (в часах)
RATING_DEADLINE_HOURS = 18

# Время напоминания до дедлайна (в часах)
REMINDER_BEFORE_DEADLINE_HOURS = 1

# База данных
DATABASE_NAME = '/var/data/youth_feedback.db'
