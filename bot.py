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
            f"Привіт, {user.first_name}! Твоя присутність вже схвалена, можеш користуватися ботом.\n\n"
            "Після кожного молодіжного тобі прийде опитування для оцінки заходу."
        )
    elif db.is_user_pending(user_id):
        await update.message.reply_text(
            "Твій запит уже надіслано адміністратору. Чекай схвалення!"
        )
    else:
        # Додаємо в чергу на схвалення
        db.add_pending_user(
            user_id=user_id,
            username=user.username or "",
            first_name=user.first_name or "",
            last_name=user.last_name or ""
        )
        
        await update.message.reply_text(
            "Запит на доступ надіслано адміністратору. Чекай схвалення!"
        )
        
        # Уведомляем админа
        try:
            await context.bot.send_message(
                chat_id=config.ADMIN_ID,
                text=f"🔔 Новый запрос на доступ:\n\n"
                     f"Имя: {user.first_name} {user.last_name or ''}\n"
                     f"Username: @{user.username or 'не указан'}\n"
                     f"ID: {user_id}\n\n"
                     f"Используй /pending чтобы посмотреть все запросы."
            )
        except Exception as e:
            logger.error(f"Error notifying admin: {e}")


async def admin_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список пользователей ожидающих одобрения (только для админа)"""
    if update.effective_user.id != config.ADMIN_ID:
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return
    
    pending_users = db.get_pending_users()
    
    if not pending_users:
        await update.message.reply_text("Нет пользователей ожидающих одобрения.")
        return
    
    for user in pending_users:
        user_id, username, first_name, last_name, request_date = user
        keyboard = [
            [
                InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{user_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{user_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"👤 Запрос:\n"
            f"Имя: {first_name} {last_name or ''}\n"
            f"Username: @{username or 'не указан'}\n"
            f"ID: {user_id}\n"
            f"Дата запроса: {request_date[:16]}",
            reply_markup=reply_markup
        )


async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок одобрения/отклонения"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != config.ADMIN_ID:
        await query.edit_message_text("У тебя нет доступа к этому действию.")
        return
    
    action, user_id = query.data.split('_')
    user_id = int(user_id)
    
    if action == "approve":
        db.approve_user(user_id)
        await query.edit_message_text(f"✅ Пользователь {user_id} одобрен!")
        
        # Уведомляем пользователя
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="🎉 Твой запрос одобрен! Теперь ты будешь получать опросы после молодежных встреч."
            )
        except Exception as e:
            logger.error(f"Error notifying approved user: {e}")
    
    elif action == "reject":
        db.reject_user(user_id)
        await query.edit_message_text(f"❌ Запрос пользователя {user_id} отклонен.")
        
        # Уведомляем пользователя
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="К сожалению, твой запрос на доступ был отклонен."
            )
        except Exception as e:
            logger.error(f"Error notifying rejected user: {e}")


async def admin_start_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запускает новый опрос (только для админа)"""
    if update.effective_user.id != config.ADMIN_ID:
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return
    
    # Проверяем нет ли активного опроса
    active_meeting = db.get_active_meeting()
    if active_meeting:
        await update.message.reply_text(
            "❌ Уже есть активный опрос! Сначала дождись его завершения или закрой его командой /close_survey"
        )
        return
    
    # Создаем новую встречу
    meeting_id = db.create_meeting()
    
    # Рассылаем опрос всем одобренным пользователям
    approved_users = db.get_all_approved_users()
    
    if not approved_users:
        await update.message.reply_text("❌ Нет одобренных пользователей для опроса!")
        return
    
    success_count = 0
    for user_id in approved_users:
        if user_id == config.ADMIN_ID:
            continue  # Не отправляем админу
        
        try:
            keyboard = [
                [InlineKeyboardButton("📝 Оценить", callback_data=f"rate_{meeting_id}")],
                [InlineKeyboardButton("❌ Не был на молодежном", callback_data=f"absent_{meeting_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=user_id,
                text="🙏 Привет! Пожалуйста, оцени прошедшее молодежное.\n\n"
                     f"У тебя есть {config.RATING_DEADLINE_HOURS} часов на оценку.\n"
                     "За час до окончания придет напоминание.",
                reply_markup=reply_markup
            )
            success_count += 1
        except Exception as e:
            logger.error(f"Error sending survey to user {user_id}: {e}")
    
    await update.message.reply_text(
        f"✅ Опрос запущен! ID встречи: {meeting_id}\n"
        f"Отправлено {success_count} пользователям.\n\n"
        f"Дедлайн: {config.RATING_DEADLINE_HOURS} часов\n"
        f"Напоминание будет отправлено за {config.REMINDER_BEFORE_DEADLINE_HOURS} час до конца."
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
                [InlineKeyboardButton("📝 Оценить", callback_data=f"rate_{meeting_id}")],
                [InlineKeyboardButton("❌ Не был на молодежном", callback_data=f"absent_{meeting_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=user_id,
                text=f"⏰ Напоминание: у тебя остался {config.REMINDER_BEFORE_DEADLINE_HOURS} час чтобы оценить молодежное!\n\n"
                     "Пожалуйста, не забудь оставить обратную связь.",
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
            text=f"⏱ Опрос #{meeting_id} автоматически закрыт.\n\n"
                 f"Используй /stats {meeting_id} чтобы посмотреть результаты."
        )
    except Exception as e:
        logger.error(f"Error notifying admin about closed survey: {e}")


async def admin_close_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вручную закрывает активный опрос (только для админа)"""
    if update.effective_user.id != config.ADMIN_ID:
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return
    
    active_meeting = db.get_active_meeting()
    if not active_meeting:
        await update.message.reply_text("❌ Нет активного опроса.")
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
        f"✅ Опрос #{active_meeting} закрыт вручную.\n\n"
        f"Используй /stats {active_meeting} чтобы посмотреть результаты."
    )


async def handle_rating_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Оценить'"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Проверяем что пользователь одобрен
    if not db.is_user_approved(user_id):
        await query.edit_message_text("У тебя нет доступа к этому боту.")
        return
    
    data = query.data.split('_')
    action = data[0]
    meeting_id = int(data[1])
    
    if action == "absent":
        # Пользователь не был на встрече
        db.mark_not_attended(meeting_id, user_id)
        await query.edit_message_text(
            "✅ Спасибо за ответ! Надеюсь увидим тебя на следующем молодежном! 🙏"
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
            "📊 Оцени *интересность* молодежного от 1 до 5:\n\n"
            "1 - Скучно\n"
            "5 - Очень интересно",
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
        "📊 Оцени *актуальность для тебя* от 1 до 5:\n\n"
        "1 - Совсем не актуально\n"
        "5 - Очень актуально",
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
        "📊 Оцени *полезность для духовного роста* от 1 до 5:\n\n"
        "1 - Совсем не полезно\n"
        "5 - Очень полезно",
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
        [InlineKeyboardButton("✍️ Оставить отзыв", callback_data="feedback_yes")],
        [InlineKeyboardButton("⏭ Пропустить", callback_data="feedback_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "✅ Спасибо за оценки!\n\n"
        "Хочешь оставить письменный отзыв? (3-4 предложения)",
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
            "✅ Спасибо за обратную связь! 🙏"
        )
        return ConversationHandler.END
    
    else:
        # Просим написать отзыв
        await query.edit_message_text(
            "✍️ Напиши свой отзыв (3-4 предложения):"
        )
        return WAITING_FOR_FEEDBACK


async def handle_feedback_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстового отзыва"""
    user_id = update.effective_user.id
    feedback_text = update.message.text
    
    rating_data = user_ratings.get(user_id)
    if not rating_data:
        await update.message.reply_text("Произошла ошибка. Попробуй начать оценку заново.")
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
        "✅ Спасибо за подробную обратную связь! 🙏"
    )
    return ConversationHandler.END


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику по встрече (только для админа)"""
    if update.effective_user.id != config.ADMIN_ID:
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return
    
    # Получаем ID встречи из аргументов или берем последнюю активную
    if context.args:
        try:
            meeting_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID встречи.")
            return
    else:
        meeting_id = db.get_active_meeting()
        if not meeting_id:
            await update.message.reply_text("❌ Нет активной встречи. Укажи ID: /stats <meeting_id>")
            return
    
    stats = db.get_meeting_stats(meeting_id)
    
    # Формируем текст статистики
    text = f"📊 *Статистика встречи #{meeting_id}*\n\n"
    text += f"👥 Присутствовало: {stats['total_attended']}\n"
    text += f"❌ Не было: {stats['not_attended']}\n\n"
    
    if stats['total_attended'] > 0:
        text += f"⭐️ *Средние оценки:*\n"
        text += f"Интересность: {stats['avg_interest']}/5\n"
        text += f"Актуальность: {stats['avg_relevance']}/5\n"
        text += f"Духовный рост: {stats['avg_spiritual_growth']}/5\n\n"
    
    if stats['feedbacks']:
        text += f"💬 *Отзывы ({len(stats['feedbacks'])}):*\n\n"
        for i, (feedback, date) in enumerate(stats['feedbacks'], 1):
            text += f"{i}. {feedback}\n\n"
    else:
        text += "💬 Текстовых отзывов нет.\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')


async def admin_graph(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создает график динамики оценок (только для админа)"""
    if update.effective_user.id != config.ADMIN_ID:
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return
    
    # Получаем период из аргументов (30 или 365 дней)
    if context.args and context.args[0] in ['month', 'year']:
        period = 30 if context.args[0] == 'month' else 365
    else:
        await update.message.reply_text(
            "Укажи период: /graph month или /graph year"
        )
        return
    
    stats = db.get_stats_for_period(period)
    
    if not stats:
        await update.message.reply_text("❌ Нет данных за указанный период.")
        return
    
    # Создаем график
    dates = [s['date'] for s in stats]
    interest = [s['avg_interest'] for s in stats]
    relevance = [s['avg_relevance'] for s in stats]
    spiritual = [s['avg_spiritual'] for s in stats]
    
    plt.figure(figsize=(12, 6))
    plt.plot(dates, interest, marker='o', label='Интересность', linewidth=2)
    plt.plot(dates, relevance, marker='s', label='Актуальность', linewidth=2)
    plt.plot(dates, spiritual, marker='^', label='Духовный рост', linewidth=2)
    
    plt.xlabel('Дата')
    plt.ylabel('Оценка (1-5)')
    plt.title(f'Динамика оценок за {"месяц" if period == 30 else "год"}')
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
        caption=f"📈 График за {"месяц" if period == 30 else "год"}"
    )


async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список команд для админа"""
    if update.effective_user.id != config.ADMIN_ID:
        await update.message.reply_text(
            "Доступные команды:\n"
            "/start - Начать работу с ботом"
        )
        return
    
    help_text = """
🤖 *Команды администратора:*

👥 *Управление пользователями:*
/pending - Показать запросы на доступ

📊 *Управление опросами:*
/start\\_survey - Запустить новый опрос
/close\\_survey - Закрыть активный опрос вручную

📈 *Статистика:*
/stats - Статистика по последнему опросу
/stats ID - Статистика по конкретному опросу
/graph month - График за месяц
/graph year - График за год

❓ /help - Показать это сообщение
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
    )
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", admin_help))
    application.add_handler(CommandHandler("pending", admin_pending))
    application.add_handler(CommandHandler("start_survey", admin_start_survey))
    application.add_handler(CommandHandler("close_survey", admin_close_survey))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("graph", admin_graph))
    application.add_handler(CallbackQueryHandler(handle_approval, pattern='^(approve|reject)_'))
    application.add_handler(rating_conv_handler)
    
    # Запускаем бота
    logger.info("Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
