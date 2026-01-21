import os

# Токен бота - берётся из переменной окружения на Render
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set!")

# ID администратора (твой Telegram ID)
ADMIN_ID = int(os.getenv('ADMIN_ID', '1125355606'))

# Время на оценку (в часах)
RATING_DEADLINE_HOURS = 18

# Время напоминания до дедлайна (в часах)
REMINDER_BEFORE_DEADLINE_HOURS = 1

# URL базы данных PostgreSQL
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set!")

# Fix for Render's postgres:// vs postgresql:// issue
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
