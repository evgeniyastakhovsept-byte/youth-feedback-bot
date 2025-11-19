import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from datetime import datetime, timedelta
import asyncio
import matplotlib
matplotlib.use('Agg')  # Для работы на сервере без GUI
import matplotlib.pyplot as plt
import io

import config
from database import Database

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
WAITING_FOR_INTEREST, WAITING_FOR_RELEVANCE, WAITING_FOR_SPIRITUAL, WAITING_FOR_FEEDBACK = range(4)

# Инициализация базы данных
db = Database()

# Глобальные переменные для хранения временных данных оценки
user_ratings = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    user_id = user.id
    
    # Проверяем статус пользователя
    if db.is_user_approved(user_id):
        await update.message.reply_text(
            f"Привіт, {user.first_name}! Ти вже затверджений і можеш користуватися ботом.\n\n"
            "Після кожної молодіжки тобі прийде опитування для оцінки зустрічі."
        )
    elif db.is_user_pending(user_id):
        await update.message.reply_text(
            "Твій запит вже відправлено адміністратору. Очікуй затвердження!"
        )
    else:
        # Добавляем в очередь на одобрение
        db.add_pending_user(
            user_id=user_id,
            username=user.username or "",
            first_name=user.first_name or "",
            last_name=user.last_name or ""
        )
        
        await update.message.reply_text(
            "Запит на доступ відправлено адміністратору. Очікуй затвердження!"
        )
        
        # Уведомляем админа
        try:
            await context.bot.send_message(
                chat_id=config.ADMIN_ID,
                text=f"🔔 Новий запит на доступ:\n\n"
                     f"Ім'я: {user.first_name} {user.last_name or ''}\n"
                     f"Username: @{user.username or 'не вказано'}\n"
                     f"ID: {user_id}\n\n"
                     f"Використай /pending щоб переглянути всі запити."
            )
        except Exception as e:
            logger.error(f"Error notifying admin: {e}")


async def admin_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список пользователей ожидающих одобрения (только для админа)"""
    if update.effective_user.id != config.ADMIN_ID:
        await update.message.reply_text("У тебе немає доступу до цієї команди.")
        return
    
    pending_users = db.get_pending_users()
    
    if not pending_users:
        await update.message.reply_text("Немає користувачів, що очікують затвердження.")
        return
    
    for user in pending_users:
        user_id, username, first_name, last_name, request_date = user
        keyboard = [
            [
                InlineKeyboardButton("✅ Затвердити", callback_data=f"approve_{user_id}"),
                InlineKeyboardButton("❌ Відхилити", callback_data=f"reject_{user_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"👤 Запит:\n"
            f"Ім'я: {first_name} {last_name or ''}\n"
            f"Username: @{username or 'не вказано'}\n"
            f"ID: {user_id}\n"
            f"Дата запиту: {request_date[:16]}",
            reply_markup=reply_markup
        )


async def admin_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список одобренных пользователей для удаления (только для админа)"""
    if update.effective_user.id != config.ADMIN_ID:
        await update.message.reply_text("У тебе немає доступу до цієї команди.")
        return
    
    approved_users = db.get_all_approved_users_info()
    
    if not approved_users:
        await update.message.reply_text("Немає затверджених користувачів.")
        return
    
    # Фильтруем админа из списка
    approved_users = [u for u in approved_users if u[0] != config.ADMIN_ID]
    
    if not approved_users:
        await update.message.reply_text("Немає користувачів для видалення (крім тебе).")
        return
    
    text = "👥 *Затверджені користувачі:*\n\n"
    text += "Виберь користувача для видалення:\n\n"
    
    for user_id, username, first_name, last_name in approved_users:
        keyboard = [
            [InlineKeyboardButton("🗑 Видалити", callback_data=f"remove_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"👤 Користувач:\n"
            f"Ім'я: {first_name} {last_name or ''}\n"
            f"Username: @{username or 'не вказано'}\n"
            f"ID: {user_id}",
            reply_markup=reply_markup
        )


async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок одобрения/отклонения/удаления"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != config.ADMIN_ID:
        await query.edit_message_text("У тебе немає доступу до цієї дії.")
        return
    
    action, user_id = query.data.split('_')
    user_id = int(user_id)
    
    if action == "approve":
        db.approve_user(user_id)
        await query.edit_message_text(f"✅ Користувача {user_id} затверджено!")
        
        # Уведомляем пользователя
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="🎉 Твій запит затверджено! Тепер ти будеш отримувати опитування після молодіжних зустрічей."
            )
        except Exception as e:
            logger.error(f"Error notifying approved user: {e}")
    
    elif action == "reject":
        db.reject_user(user_id)
        await query.edit_message_text(f"❌ Запит користувача {user_id} відхилено.")
        
        # Уведомляем пользователя
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="На жаль, твій запит на доступ було відхилено."
            )
        except Exception as e:
            logger.error(f"Error notifying rejected user: {e}")
    
    elif action == "remove":
        if db.remove_user(user_id):
            await query.edit_message_text(f"🗑 Користувача {user_id} видалено зі списку!")
            
            # Уведомляем пользователя
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="Тебе було видалено зі списку учасників бота. Ти більше не будеш отримувати опитування."
                )
            except Exception as e:
                logger.error(f"Error notifying removed user: {e}")
        else:
            await query.edit_message_text(f"❌ Користувача {user_id} не знайдено.")


async def admin_start_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запускает новый опрос (только для админа)"""
    if update.effective_user.id != config.ADMIN_ID:
        await update.message.reply_text("У тебе немає доступу до цієї команди.")
        return
    
    # Проверяем нет ли активного опроса
    active_meeting = db.get_active_meeting()
    if active_meeting:
        await update.message.reply_text(
            "❌ Вже є активне опитування! Спочатку дочекайся його завершення або закрий його командою /close_survey"
        )
        return
    
    # Создаем новую встречу
    meeting_id = db.create_meeting()
    
    # Рассылаем опрос всем одобренным пользователям
    approved_users = db.get_all_approved_users()
    
    if not approved_users:
        await update.message.reply_text("❌ Немає затверджених користувачів для опитування!")
        return
    
    success_count = 0
    for user_id in approved_users:
        if user_id == config.ADMIN_ID:
            continue  # Не отправляем админу
        
        try:
            keyboard = [
                [InlineKeyboardButton("📝 Оцінити", callback_data=f"rate_{meeting_id}")],
                [InlineKeyboardButton("❌ Не був на молодіжці", callback_data=f"absent_{meeting_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=user_id,
                text="🙏 Привіт! Будь ласка, оціни минулу молодіжку.\n\n"
                     f"У тебе є {config.RATING_DEADLINE_HOURS} годин на оцінку.\n"
                     "За годину до закінчення прийде нагадування.",
                reply_markup=reply_markup
            )
            success_count += 1
        except Exception as e:
            logger.error(f"Error sending survey to user {user_id}: {e}")
    
    await update.message.reply_text(
        f"✅ Опитування запущено! ID зустрічі: {meeting_id}\n"
        f"Відправлено {success_count} користувачам.\n\n"
        f"Дедлайн: {config.RATING_DEADLINE_HOURS} годин\n"
        f"Нагадування буде відправлено за {config.REMINDER_BEFORE_DEADLINE_HOURS} годину до кінця."
    )
    
    # Планируем напоминание и закрытие опроса
    reminder_time = config.RATING_DEADLINE_HOURS - config.REMINDER_BEFORE_DEADLINE_HOURS
    
    # Запланируем джобы
    context.job_queue.run_once(
        send_reminders,
        reminder_time * 3600,
        data={'meeting_id': meeting_id},
        name=f'reminder_{meeting_id}'
    )
    
    context.job_queue.run_once(
        close_survey_job,
        config.RATING_DEADLINE_HOURS * 3600,
        data={'meeting_id': meeting_id},
        name=f'close_{meeting_id}'
    )


async def send_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Отправляет напоминания тем, кто еще не оценил"""
    meeting_id = context.job.data['meeting_id']
    users_to_remind = db.get_users_for_reminder(meeting_id)
    
    for user_id in users_to_remind:
        if user_id == config.ADMIN_ID:
            continue
        
        try:
            keyboard = [
                [InlineKeyboardButton("📝 Оцінити", callback_data=f"rate_{meeting_id}")],
                [InlineKeyboardButton("❌ Не був на молодіжці", callback_data=f"absent_{meeting_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=user_id,
                text=f"⏰ Нагадування: у тебе залишилася {config.REMINDER_BEFORE_DEADLINE_HOURS} година щоб оцінити молодіжку!\n\n"
                     "Будь ласка, не забудь залишити зворотний зв'язок.",
                reply_markup=reply_markup
            )
            db.mark_as_reminded(meeting_id, user_id)
        except Exception as e:
            logger.error(f"Error sending reminder to user {user_id}: {e}")


async def close_survey_job(context: ContextTypes.DEFAULT_TYPE):
    """Автоматически закрывает опрос по истечении времени"""
    meeting_id = context.job.data['meeting_id']
    db.close_meeting(meeting_id)
    
    # Уведомляем админа
    try:
        stats = db.get_meeting_stats(meeting_id)
        await context.bot.send_message(
            chat_id=config.ADMIN_ID,
            text=f"⏱ Опитування #{meeting_id} автоматично закрито.\n\n"
                 f"Використай /stats {meeting_id} щоб переглянути результати."
        )
    except Exception as e:
        logger.error(f"Error notifying admin about closed survey: {e}")


async def admin_close_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вручную закрывает активный опрос (только для админа)"""
    if update.effective_user.id != config.ADMIN_ID:
        await update.message.reply_text("У тебе немає доступу до цієї команди.")
        return
    
    active_meeting = db.get_active_meeting()
    if not active_meeting:
        await update.message.reply_text("❌ Немає активного опитування.")
        return
    
    db.close_meeting(active_meeting)
    
    # Отменяем запланированные джобы
    current_jobs = context.job_queue.get_jobs_by_name(f'reminder_{active_meeting}')
    for job in current_jobs:
        job.schedule_removal()
    
    current_jobs = context.job_queue.get_jobs_by_name(f'close_{active_meeting}')
    for job in current_jobs:
        job.schedule_removal()
    
    await update.message.reply_text(
        f"✅ Опитування #{active_meeting} закрито вручну.\n\n"
        f"Використай /stats {active_meeting} щоб переглянути результати."
    )


async def handle_rating_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Оценить'"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Проверяем что пользователь одобрен
    if not db.is_user_approved(user_id):
        await query.edit_message_text("У тебе немає доступу до цього бота.")
        return
    
    data = query.data.split('_')
    action = data[0]
    meeting_id = int(data[1])
    
    if action == "absent":
        # Пользователь не был на встрече
        db.mark_not_attended(meeting_id, user_id)
        await query.edit_message_text(
            "✅ Дякуємо за відповідь! Сподіваємося побачити тебе на наступній молодіжці! 🙏"
        )
        return
    
    elif action == "rate":
        # Начинаем процесс оценки
        user_ratings[user_id] = {
            'meeting_id': meeting_id,
            'interest': None,
            'relevance': None,
            'spiritual': None
        }
        
        keyboard = [
            [InlineKeyboardButton(str(i), callback_data=f"interest_{i}") for i in range(1, 6)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📊 Оціни *цікавість* молодіжки від 1 до 5:\n\n"
            "1 - Нудно\n"
            "5 - Дуже цікаво",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return WAITING_FOR_INTEREST


async def handle_interest_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик оценки интересности"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    rating = int(query.data.split('_')[1])
    
    user_ratings[user_id]['interest'] = rating
    
    keyboard = [
        [InlineKeyboardButton(str(i), callback_data=f"relevance_{i}") for i in range(1, 6)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📊 Оціни *актуальність для тебе* від 1 до 5:\n\n"
        "1 - Зовсім не актуально\n"
        "5 - Дуже актуально",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return WAITING_FOR_RELEVANCE


async def handle_relevance_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик оценки актуальности"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    rating = int(query.data.split('_')[1])
    
    user_ratings[user_id]['relevance'] = rating
    
    keyboard = [
        [InlineKeyboardButton(str(i), callback_data=f"spiritual_{i}") for i in range(1, 6)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📊 Оціни *корисність для духовного зростання* від 1 до 5:\n\n"
        "1 - Зовсім не корисно\n"
        "5 - Дуже корисно",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return WAITING_FOR_SPIRITUAL


async def handle_spiritual_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик оценки духовного роста"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    rating = int(query.data.split('_')[1])
    
    user_ratings[user_id]['spiritual'] = rating
    
    keyboard = [
        [InlineKeyboardButton("✍️ Залишити відгук", callback_data="feedback_yes")],
        [InlineKeyboardButton("⏭ Пропустити", callback_data="feedback_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "✅ Дякуємо за оцінки!\n\n"
        "Хочеш залишити письмовий відгук? (3-4 речення)",
        reply_markup=reply_markup
    )
    return WAITING_FOR_FEEDBACK


async def handle_feedback_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора оставить отзыв или нет"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    choice = query.data.split('_')[1]
    
    if choice == "no":
        # Сохраняем оценки без отзыва
        rating_data = user_ratings.get(user_id)
        if rating_data:
            db.add_rating(
                meeting_id=rating_data['meeting_id'],
                user_id=user_id,
                interest=rating_data['interest'],
                relevance=rating_data['relevance'],
                spiritual_growth=rating_data['spiritual'],
                attended=True
            )
            del user_ratings[user_id]
        
        await query.edit_message_text(
            "✅ Дякуємо за зворотний зв'язок! 🙏"
        )
        return ConversationHandler.END
    
    else:
        # Просим написать отзыв
        await query.edit_message_text(
            "✍️ Напиши свій відгук (3-4 речення):"
        )
        return WAITING_FOR_FEEDBACK


async def handle_feedback_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстового отзыва"""
    user_id = update.effective_user.id
    feedback_text = update.message.text
    
    rating_data = user_ratings.get(user_id)
    if not rating_data:
        await update.message.reply_text("Сталася помилка. Спробуй почати оцінювання заново.")
        return ConversationHandler.END
    
    # Сохраняем оценки
    db.add_rating(
        meeting_id=rating_data['meeting_id'],
        user_id=user_id,
        interest=rating_data['interest'],
        relevance=rating_data['relevance'],
        spiritual_growth=rating_data['spiritual'],
        attended=True
    )
    
    # Сохраняем отзыв
    db.add_feedback(rating_data['meeting_id'], feedback_text)
    
    del user_ratings[user_id]
    
    await update.message.reply_text(
        "✅ Дякуємо за детальний зворотний зв'язок! 🙏"
    )
    return ConversationHandler.END


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику по встрече (только для админа)"""
    if update.effective_user.id != config.ADMIN_ID:
        await update.message.reply_text("У тебе немає доступу до цієї команди.")
        return
    
    # Получаем ID встречи из аргументов или берем последнюю активную
    if context.args:
        try:
            meeting_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Невірний формат ID зустрічі.")
            return
    else:
        # Если аргумента нет - показываем список всех встреч
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT meeting_id, start_date, is_active 
            FROM youth_meetings 
            ORDER BY start_date DESC 
            LIMIT 10
        ''')
        meetings = cursor.fetchall()
        conn.close()
        
        if not meetings:
            await update.message.reply_text("❌ Ще не було жодної молодіжки.")
            return
        
        # Формируем список встреч
        from datetime import datetime
        text = "📊 *Список молодіжних зустрічей:*\n\n"
        for meeting_id, start_date, is_active in meetings:
            date_obj = datetime.fromisoformat(start_date)
            date_str = date_obj.strftime("%d.%m.%Y %H:%M")
            status = "🟢 Активна" if is_active else "⚪️ Завершена"
            text += f"#{meeting_id} - {date_str} {status}\n"
        
        text += f"\n💡 Використай `/stats ID` щоб переглянути статистику\n"
        text += f"Наприклад: `/stats 1`"
        
        await update.message.reply_text(text, parse_mode='Markdown')
        return
    
    stats = db.get_meeting_stats(meeting_id)
    
    # Формируем текст статистики
    text = f"📊 *Статистика зустрічі #{meeting_id}*\n\n"
    text += f"👥 Були присутні: {stats['total_attended']}\n"
    text += f"❌ Не було: {stats['not_attended']}\n\n"
    
    if stats['total_attended'] > 0:
        text += f"⭐️ *Середні оцінки:*\n"
        text += f"Цікавість: {stats['avg_interest']}/5\n"
        text += f"Актуальність: {stats['avg_relevance']}/5\n"
        text += f"Духовне зростання: {stats['avg_spiritual_growth']}/5\n\n"
    
    if stats['feedbacks']:
        text += f"💬 *Відгуки ({len(stats['feedbacks'])}):*\n\n"
        for i, (feedback, date) in enumerate(stats['feedbacks'], 1):
            text += f"{i}. {feedback}\n\n"
    else:
        text += "💬 Текстових відгуків немає.\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')


async def admin_graph(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создает график динамики оценок (только для админа)"""
    if update.effective_user.id != config.ADMIN_ID:
        await update.message.reply_text("У тебе немає доступу до цієї команди.")
        return
    
    # Получаем период из аргументов (30 или 365 дней)
    if context.args and context.args[0] in ['month', 'year']:
        period = 30 if context.args[0] == 'month' else 365
    else:
        await update.message.reply_text(
            "Вкажи період: /graph month або /graph year"
        )
        return
    
    stats = db.get_stats_for_period(period)
    
    if not stats:
        await update.message.reply_text("❌ Немає даних за вказаний період.")
        return
    
    # Создаем график
    dates = [s['date'] for s in stats]
    interest = [s['avg_interest'] for s in stats]
    relevance = [s['avg_relevance'] for s in stats]
    spiritual = [s['avg_spiritual'] for s in stats]
    
    plt.figure(figsize=(12, 6))
    plt.plot(dates, interest, marker='o', label='Цікавість', linewidth=2)
    plt.plot(dates, relevance, marker='s', label='Актуальність', linewidth=2)
    plt.plot(dates, spiritual, marker='^', label='Духовне зростання', linewidth=2)
    
    plt.xlabel('Дата')
    plt.ylabel('Оцінка (1-5)')
    plt.title(f'Динаміка оцінок за {"місяць" if period == 30 else "рік"}')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.ylim(0, 5.5)
    
    # Сохраняем график в BytesIO
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150)
    buf.seek(0)
    plt.close()
    
    # Отправляем график
    await update.message.reply_photo(
        photo=buf,
        caption=f"📈 Графік за {"місяць" if period == 30 else "рік"}"
    )


async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список команд для админа"""
    if update.effective_user.id != config.ADMIN_ID:
        await update.message.reply_text(
            "Доступні команди:\n"
            "/start - Почати роботу з ботом"
        )
        return
    
    help_text = """
🤖 *Команди адміністратора:*

👥 *Управління користувачами:*
/pending - Показати запити на доступ
/remove - Видалити учасника з бота

📊 *Управління опитуваннями:*
/start\\_survey - Запустити нове опитування
/close\\_survey - Закрити активне опитування вручну

📈 *Статистика:*
/stats - Статистика по останньому опитуванню
/stats ID - Статистика по конкретному опитуванню
/graph month - Графік за місяць
/graph year - Графік за рік

❓ /help - Показати це повідомлення
    """
    
    await update.message.reply_text(help_text, parse_mode='Markdown')


def main():
    """Главная функция запуска бота"""
    # Проверяем что ADMIN_ID установлен
    if config.ADMIN_ID == 0:
        logger.error("ADMIN_ID not set! Please set your Telegram user ID in config.py")
        return
    
    # Создаем приложение
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    # Обработчик процесса оценки
    rating_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_rating_button, pattern='^(rate|absent)_')],
        states={
            WAITING_FOR_INTEREST: [CallbackQueryHandler(handle_interest_rating, pattern='^interest_')],
            WAITING_FOR_RELEVANCE: [CallbackQueryHandler(handle_relevance_rating, pattern='^relevance_')],
            WAITING_FOR_SPIRITUAL: [CallbackQueryHandler(handle_spiritual_rating, pattern='^spiritual_')],
            WAITING_FOR_FEEDBACK: [
                CallbackQueryHandler(handle_feedback_choice, pattern='^feedback_(yes|no)$'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_feedback_text)
            ],
        },
        fallbacks=[CommandHandler('start', start)],
        per_message=True,
    )
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", admin_help))
    application.add_handler(CommandHandler("pending", admin_pending))
    application.add_handler(CommandHandler("remove", admin_remove))
    application.add_handler(CommandHandler("start_survey", admin_start_survey))
    application.add_handler(CommandHandler("close_survey", admin_close_survey))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("graph", admin_graph))
    application.add_handler(CallbackQueryHandler(handle_approval, pattern='^(approve|reject|remove)_'))
    application.add_handler(rating_conv_handler)
    
    # Запускаем бота
    logger.info("Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
