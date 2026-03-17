import logging
import nest_asyncio
import os
import re # Import the re module for regular expressions
from datetime import datetime, timedelta # Import datetime and timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, JobQueue

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
HR_CHAT_ID = int(os.environ.get("HR_CHAT_ID", "0"))

if not BOT_TOKEN or HR_CHAT_ID == 0:
    raise RuntimeError(
        "Не заданы переменные окружения BOT_TOKEN и/или HR_CHAT_ID. "
        "Установите их в настройках Render."
    )

# This dictionary will store the state and collected data for each user's application
user_data = {}

# Define the conversation states
WAITING_FOR_START_BUTTON, ASK_NAME, ASK_AGE, ASK_CITY, ARMY, EDU, JOB, HEALTH, LEGAL, PHONE, END = range(11)

# Reminder interval
REMINDER_INTERVAL_MINUTES = 20

# Define the main menu keyboard
main_menu_buttons = [
    [KeyboardButton("Помощь")],
    [KeyboardButton("Закрыть")]
]
main_menu_keyboard = ReplyKeyboardMarkup(main_menu_buttons, resize_keyboard=True, one_time_keyboard=False)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Sends a message when the command /start is issued and presents the 'НАЧАТЬ' button."""
    user = update.effective_user
    welcome_message = (
        "🇷🇺Привет! 🤝\n\n"
        "Я бот, помогаю человеку 🤖. Он подключится в ближайшее время!❤️\n\n"
        "✨А пока, ответь, пожалуйста, на несколько вопросов!\n"
        "Нажмите 'НАЧАТЬ', чтобы заполнить анкету."
    )
    keyboard = [[InlineKeyboardButton("НАЧАТЬ", callback_data="start_questionnaire")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_html(welcome_message, reply_markup=reply_markup)
    user_data[user.id] = {
        'state': WAITING_FOR_START_BUTTON,
        'data': {},
        'user_info': {
            'id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'username': user.username
        },
        'last_activity': datetime.now()
    }
    return WAITING_FOR_START_BUTTON

async def button_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the 'НАЧАТЬ' button press."""
    query = update.callback_query
    await query.answer() # Acknowledge the callback query

    user_id = query.from_user.id
    if user_id not in user_data or user_data[user_id]['state'] != WAITING_FOR_START_BUTTON:
        # If user data is missing or state is incorrect, restart
        await query.edit_message_text("Пожалуйста, начни сначала с команды /start.")
        return END

    # Update last activity
    user_data[user_id]['last_activity'] = datetime.now()

    # Edit the original message to remove the inline keyboard (or just edit its text without inline_keyboard)
    await query.edit_message_text("Начинаем анкетирование! Всего будет 8 вопросов.")

    # Send a new message with the first question and the main menu keyboard
    await context.bot.send_message(chat_id=user_id, text="Как тебя зовут?🙃", reply_markup=main_menu_keyboard)
    user_data[user_id]['state'] = ASK_NAME
    return ASK_NAME

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles incoming messages based on the current state."""
    user_id = update.effective_user.id

    # Ignore messages from the HR group
    if update.effective_chat.id == HR_CHAT_ID:
        logger.info(f"Ignoring message from HR group: {update.message.text}")
        return END # End the conversation flow for this message without processing it further

    if user_id not in user_data:
        # If user data is missing (e.g., bot restarted or user started without /start)
        await update.message.reply_text("Пожалуйста, начни сначала с команды /start.")
        return END

    # Update last activity for the user
    user_data[user_id]['last_activity'] = datetime.now()

    current_state = user_data[user_id]['state']
    text = update.message.text

    # Safely get user's name if available
    user_name = user_data[user_id]['data'].get('NAME', 'Незнакомец')

    # Handle main menu buttons if they are pressed
    if text == "Помощь":
        await update.message.reply_text(
            "Если вам нужна помощь, пожалуйста, свяжитесь с нашим сотрудником @Buninil.",
            reply_markup=main_menu_keyboard # Keep the menu visible
        )
        return current_state # Stay in current state
    elif text == "Закрыть":
        return await cancel(update, context) # Call cancel and return END

    if current_state == WAITING_FOR_START_BUTTON:
        await update.message.reply_text("Пожалуйста, нажмите кнопку 'НАЧАТЬ', чтобы заполнить анкету.", reply_markup=main_menu_keyboard)
        return WAITING_FOR_START_BUTTON

    elif current_state == ASK_NAME:
        user_data[user_id]['data']['NAME'] = text
        # Update user_name immediately for subsequent messages in this turn
        user_name = text
        user_data[user_id]['state'] = ASK_AGE
        await update.message.reply_text(f"Очень приятно, {user_name}! Сколько тебе лет?📆", reply_markup=main_menu_keyboard)
        return ASK_AGE

    elif current_state == ASK_AGE:
        user_data[user_id]['data']['AGE'] = text
        user_data[user_id]['state'] = ASK_CITY
        await update.message.reply_text(f"{user_name}, где ты живёшь?🏙", reply_markup=main_menu_keyboard)
        return ASK_CITY

    elif current_state == ASK_CITY:
        user_data[user_id]['data']['CITY'] = text
        user_data[user_id]['state'] = ARMY
        await update.message.reply_text(f"Служил ли ты в армии?🫡", reply_markup=main_menu_keyboard)
        return ARMY

    elif current_state == ARMY:
        user_data[user_id]['data']['ARMY'] = text
        user_data[user_id]['state'] = EDU
        await update.message.reply_text(f"Какое у тебя образование? 👩‍🎓 Если среднее, укажи, сколько классов окончил.", reply_markup=main_menu_keyboard)
        return EDU

    elif current_state == EDU:
        user_data[user_id]['data']['EDU'] = text
        user_data[user_id]['state'] = JOB
        await update.message.reply_text(f"Отлично, {user_name}! Сейчас чем занимаешься в плане работы/учебы?👷🏽", reply_markup=main_menu_keyboard)
        return JOB

    elif current_state == JOB:
        user_data[user_id]['data']['JOB'] = text
        user_data[user_id]['state'] = HEALTH
        await update.message.reply_text(f"Хорошо! Есть какие-либо ограничения по здоровью?👨🏼‍⚕️", reply_markup=main_menu_keyboard)
        return HEALTH

    elif current_state == HEALTH:
        user_data[user_id]['data']['HEALTH'] = text
        user_data[user_id]['state'] = LEGAL
        await update.message.reply_text(f"Осталось совсем чуть-чуть, {user_name}! Проблемы с правоохранительными органами были когда-нибудь?👮🏼‍♂️", reply_markup=main_menu_keyboard)
        return LEGAL

    elif current_state == LEGAL:
        user_data[user_id]['data']['LEGAL'] = text
        user_data[user_id]['state'] = PHONE
        await update.message.reply_text(f"Твои ответы приняты, {user_name}! Оставь, пожалуйста, свой контактный телефон 📞 Наши сотрудники свяжутся с тобой и подробно проконсультируют.", reply_markup=main_menu_keyboard)
        return PHONE

    elif current_state == PHONE:
        # Validate phone number: must contain only digits
        if not re.fullmatch(r'^\d+$', text):
            await update.message.reply_text("Неверный формат! Пожалуйста, введи номер телефона, используя только цифры.🔢", reply_markup=main_menu_keyboard)
            return PHONE # Stay in the PHONE state

        user_data[user_id]['data']['PHONE'] = text

        user_session_data = user_data[user_id]
        user_info = user_session_data.get('user_info', {})
        collected_data = user_session_data.get('data', {})

        # Prepare summary for HR
        summary_for_hr = f"***Новая заявка на работу***\n\n"

        # Add user info to HR summary
        user_tg_link = f"tg://user?id={user_id}"
        summary_for_hr += f"[Ссылка на пользователя]({user_tg_link})\n"
        summary_for_hr += f"ID пользователя: {user_info.get('id')}\n"

        if user_info.get('first_name'):
            summary_for_hr += f"Имя: {user_info.get('first_name')} {user_info.get('last_name', '')}\n"
        if user_info.get('username'):
            summary_for_hr += f"Никнейм: @{user_info.get('username')}\n"
        if collected_data.get('PHONE'): # This will be the current phone number, already validated
            summary_for_hr += f"Телефон: {collected_data.get('PHONE')}\n"

        summary_for_hr += "\n***Собранные данные:***\n"
        for key, value in user_data[user_id]['data'].items():
            summary_for_hr += f"{key}: {value}\n"

        # Send summary to HR group
        try:
            await context.bot.send_message(chat_id=HR_CHAT_ID, text=summary_for_hr, parse_mode='Markdown')
            logger.info(f"Заявка от {user_data[user_id]['data'].get('NAME', 'Неизвестный')} успешно отправлена в HR группу.")
        except Exception as e:
            logger.error(f"Ошибка при отправке заявки в HR группу: {e}")
            await update.message.reply_text("Произошла ошибка при отправке твоей заявки ❌ Пожалуйста, попробуй позже.⏳", reply_markup=main_menu_keyboard)

        await update.message.reply_text(
            f"Спасибо за ответы, {user_name}! Твоя анкета отправлена в отдел кадров📨 Вскоре с тобой свяжутся.📞", reply_markup=ReplyKeyboardRemove()
        )
        # Optionally, clear user data or reset state
        del user_data[user_id]
        return END # End of conversation flow for this user

    return END # Should not reach here if states are handled correctly

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation, sending a notification to HR."""
    user = update.effective_user
    user_id = user.id
    logger.info("Пользователь %s отменил разговор.", user.first_name)

    if user_id in user_data:
        user_session_data = user_data[user_id]
        user_info = user_session_data.get('user_info', {})
        collected_data = user_session_data.get('data', {})

        # Construct HR notification message
        hr_notification_message = f"***Пользователь прервал заполнение анкеты***\n\n"
        hr_notification_message += f"Время прерывания: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"

        # Link to user chat
        user_tg_link = f"tg://user?id={user_id}"
        hr_notification_message += f"[Ссылка на пользователя]({user_tg_link})\n"
        hr_notification_message += f"ID пользователя: {user_info.get('id')}\n"

        if user_info.get('first_name'):
            hr_notification_message += f"Имя: {user_info.get('first_name')} {user_info.get('last_name', '')}\n"
        if user_info.get('username'):
            hr_notification_message += f"Никнейм: @{user_info.get('username')}\n"
        if collected_data.get('PHONE'):
            hr_notification_message += f"Телефон: {collected_data.get('PHONE')}\n"

        if collected_data:
            hr_notification_message += "\n***Собранные данные:***\n"
            for key, value in collected_data.items():
                hr_notification_message += f"{key}: {value}\n"
        else:
            hr_notification_message += "\nНачальные данные не были собраны.\n"

        # Send notification to HR group
        try:
            await context.bot.send_message(chat_id=HR_CHAT_ID, text=hr_notification_message, parse_mode='Markdown')
            logger.info(f"Уведомление HR о прерывании чата пользователем {user_id} отправлено.")
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления HR о прерывании чата: {e}")

        del user_data[user.id]

    await update.message.reply_text(
        "До свидания! Надеюсь, мы еще увидимся.", reply_markup=ReplyKeyboardRemove()
    )
    return END # End of conversation flow

async def check_inactivity_and_remind(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Checks for inactive users and sends a reminder."""
    current_time = datetime.now()
    inactive_threshold = timedelta(minutes=REMINDER_INTERVAL_MINUTES)

    # Make a copy to avoid RuntimeError: dictionary changed size during iteration
    users_to_check = list(user_data.keys())

    for user_id in users_to_check:
        if user_id in user_data: # Check if user_data[user_id] still exists (not deleted by END state)
            user_state = user_data[user_id]
            last_activity = user_state.get('last_activity')
            state = user_state.get('state')

            if last_activity and state not in [WAITING_FOR_START_BUTTON, END]:
                if current_time - last_activity >= inactive_threshold: # Changed > to >= here
                    chat_id = user_id # For private chats, user_id is the chat_id
                    try:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text="Привет! Ты не завершил заполнение анкеты. Хочешь продолжить?",
                            reply_markup=main_menu_keyboard # Include the menu in reminder
                        )
                        # Optionally, update last_activity to prevent immediate re-reminding
                        user_data[user_id]['last_activity'] = current_time
                        logger.info(f"Reminder sent to user {user_id}")
                    except Exception as e:
                        logger.error(f"Failed to send reminder to user {user_id}: {e}")

def main() -> None:
    """Start the bot via webhook (Render)."""
    application = Application.builder().token(BOT_TOKEN).job_queue(JobQueue()).build()

    job_queue = application.job_queue
    job_queue.run_repeating(
        check_inactivity_and_remind,
        interval=timedelta(minutes=REMINDER_INTERVAL_MINUTES),
        first=timedelta(minutes=REMINDER_INTERVAL_MINUTES),
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(button_start_callback, pattern="^start_questionnaire$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    port = int(os.environ.get("PORT", "8443"))
    base_url = os.environ.get("WEBHOOK_URL")
    if not base_url:
        raise RuntimeError(
            "Не задана переменная окружения WEBHOOK_URL (например, https://<service>.onrender.com)."
        )

    url_path = BOT_TOKEN
    webhook_url = f"{base_url.rstrip('/')}/{url_path}"

    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=url_path,
        webhook_url=webhook_url,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()