import logging
import datetime
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальные хранилища данных
schedule_data = {}  # Ключ: день недели (например, "Понедельник") или точная дата "YYYY-MM-DD"
events = []         # Список событий, каждый элемент — dict с ключами: date, description, chat_id
questions = []      # Список вопросов

# Состояния для ConversationHandler'ов
SCHEDULE_INPUT = 1         # Для ввода расписания (add/edit)
EXACT_DATE_INPUT = 2       # Для ввода точной даты (при выборе "Дата")
EVENT_DATE, EVENT_DESCRIPTION = range(10, 12)  # Для диалога событий
QUESTION_INPUT = 20        # Для диалога вопросов

# ---------------------- Главное меню ----------------------
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Расписание", callback_data="menu_schedule"),
         InlineKeyboardButton("События", callback_data="menu_events")],
        [InlineKeyboardButton("Вопросы", callback_data="menu_questions")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("Главное меню:", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text("Главное меню:", reply_markup=reply_markup)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await main_menu(update, context)

# ---------------------- Расписание ----------------------
# Меню "Расписание": 7 кнопок дней недели + кнопка "Дата"
async def schedule_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [
            InlineKeyboardButton("Понедельник", callback_data="day_Понедельник"),
            InlineKeyboardButton("Вторник", callback_data="day_Вторник"),
            InlineKeyboardButton("Среда", callback_data="day_Среда"),
            InlineKeyboardButton("Четверг", callback_data="day_Четверг")
        ],
        [
            InlineKeyboardButton("Пятница", callback_data="day_Пятница"),
            InlineKeyboardButton("Суббота", callback_data="day_Суббота"),
            InlineKeyboardButton("Воскресенье", callback_data="day_Воскресенье"),
            InlineKeyboardButton("Дата", callback_data="day_Дата")
        ],
        [
            InlineKeyboardButton("Назад", callback_data="back_main")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("Выберите день:", reply_markup=reply_markup)

# Обработка выбора дня (для дней недели)
async def day_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data  # Формат: "day_Понедельник", "day_Вторник", и т.д.
    _, day = data.split("_", 1)
    # Если выбрана "Дата", этот обработчик не вызывается – для неё действует отдельный ConversationHandler.
    context.user_data["selected_day"] = day
    if day in schedule_data and schedule_data[day].strip() != "":
        keyboard = [
            [
                InlineKeyboardButton("Просмотреть", callback_data=f"view_{day}"),
                InlineKeyboardButton("Изменить", callback_data=f"edit_{day}")
            ],
            [InlineKeyboardButton("Назад", callback_data="menu_schedule")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Для {day} установлено расписание.", reply_markup=reply_markup)
    else:
        keyboard = [
            [InlineKeyboardButton("Добавить", callback_data=f"add_{day}")],
            [InlineKeyboardButton("Назад", callback_data="menu_schedule")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Расписание для {day} отсутствует.", reply_markup=reply_markup)

# Просмотр расписания (для кнопок "Просмотреть")
async def view_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    _, day = query.data.split("_", 1)
    text = schedule_data.get(day, "Нет расписания.")
    keyboard = [[InlineKeyboardButton("Назад", callback_data="menu_schedule")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"Расписание на {day}:\n\n{text}", reply_markup=reply_markup)

# ---------- ConversationHandler для ввода расписания (для дней недели и точной даты) ----------
async def schedule_input_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data  # Формат: "add_Понедельник" или "edit_Понедельник" (или для точной даты, например "add_2025-04-17")
    _, day = data.split("_", 1)
    context.user_data["selected_day"] = day
    if data.startswith("add_"):
        prompt = f"Введите расписание для {day}:"
    else:
        current = schedule_data.get(day, "(пусто)")
        prompt = f"Введите новое расписание для {day}.\nТекущее: {current}\nВведите новый текст:"
    # Отправляем новое сообщение для ввода
    await query.message.reply_text(prompt)
    return SCHEDULE_INPUT

async def schedule_input_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    day = context.user_data.get("selected_day")
    if not day:
        await update.message.reply_text("Ошибка: день не выбран.")
        return ConversationHandler.END
    text = update.message.text.strip()
    schedule_data[day] = text
    await update.message.reply_text(f"Расписание для {day} установлено:\n\n{text}")
    await main_menu(update, context)
    return ConversationHandler.END

# ---------- ConversationHandler для обработки кнопки "Дата" ----------
async def exact_date_input_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    # Специально для кнопки "Дата"
    await query.edit_message_text("Введите точную дату в формате YYYY-MM-DD:")
    return EXACT_DATE_INPUT

async def process_exact_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        date_obj = datetime.datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        await update.message.reply_text("Неверный формат даты. Введите дату в формате YYYY-MM-DD:")
        return EXACT_DATE_INPUT
    date_str = date_obj.strftime("%Y-%m-%d")
    context.user_data["selected_day"] = date_str
    if date_str in schedule_data and schedule_data[date_str].strip() != "":
        keyboard = [
            [
                InlineKeyboardButton("Просмотреть", callback_data=f"view_{date_str}"),
                InlineKeyboardButton("Изменить", callback_data=f"edit_{date_str}")
            ],
            [InlineKeyboardButton("Назад", callback_data="menu_schedule")]
        ]
        msg = f"Для {date_str} установлено расписание."
    else:
        keyboard = [
            [InlineKeyboardButton("Добавить", callback_data=f"add_{date_str}")],
            [InlineKeyboardButton("Назад", callback_data="menu_schedule")]
        ]
        msg = f"Расписание для {date_str} отсутствует."
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(msg, reply_markup=reply_markup)
    return ConversationHandler.END
# ---------------------- События ----------------------
async def events_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Добавить событие", callback_data="events_add")],
        [InlineKeyboardButton("Просмотреть события", callback_data="events_view")],
        [InlineKeyboardButton("Назад", callback_data="back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("События:", reply_markup=reply_markup)

async def event_input_date_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите дату события в формате YYYY-MM-DD:")
    return EVENT_DATE

async def event_date_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    date_str = update.message.text.strip()
    try:
        event_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        await update.message.reply_text("Неверный формат даты. Попробуйте ещё раз (YYYY-MM-DD):")
        return EVENT_DATE
    context.user_data["event_date"] = event_date
    await update.message.reply_text("Введите описание события:")
    return EVENT_DESCRIPTION

async def event_description_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    description = update.message.text.strip()
    event_date = context.user_data.get("event_date")
    if not event_date:
        await update.message.reply_text("Ошибка: дата не задана.")
        return ConversationHandler.END
    chat_id = update.effective_chat.id
    event = {"date": event_date, "description": description, "chat_id": chat_id}
    events.append(event)
    await update.message.reply_text(f"Событие добавлено: {description} на {event_date}")
    await main_menu(update, context)
    return ConversationHandler.END

async def events_view_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not events:
        await query.edit_message_text("Нет запланированных событий.")
        return
    msg = "Запланированные события:\n"
    for event in events:
        msg += f"{event['date']}: {event['description']}\n"
    keyboard = [[InlineKeyboardButton("Назад", callback_data="menu_events")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(msg, reply_markup=reply_markup)

# ---------------------- Вопросы ----------------------
async def questions_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Добавить вопрос", callback_data="ques_add")],
        [InlineKeyboardButton("Просмотреть вопросы", callback_data="ques_view")],
        [InlineKeyboardButton("Назад", callback_data="back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("Вопросы:", reply_markup=reply_markup)

async def question_input_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите ваш вопрос:")
    return QUESTION_INPUT

async def question_input_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    question = update.message.text.strip()
    questions.append(question)
    await update.message.reply_text("Вопрос добавлен.")
    await main_menu(update, context)
    return ConversationHandler.END

async def questions_view_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not questions:
        await query.edit_message_text("Нет вопросов.")
        return
    msg = "Вопросы:\n"
    for i, q in enumerate(questions, start=1):
        msg += f"{i}. {q}\n"
    keyboard = [[InlineKeyboardButton("Назад", callback_data="menu_questions")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(msg, reply_markup=reply_markup)

# ---------------------- Обработчики "Назад" ----------------------
async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await main_menu(update, context)

async def back_to_schedule_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await schedule_menu(update, context)

async def back_to_events_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await events_menu(update, context)

async def back_to_questions_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await questions_menu(update, context)

# ---------------------- Основной запуск приложения ----------------------
def main():
    app = ApplicationBuilder().token("7570387816:AAHmvRjsdqOyjjr1iTzFhB9_yB-rVRyGyuU").build()

    # Главное меню
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_main$"))
    
    # Главное меню разделов
    app.add_handler(CallbackQueryHandler(schedule_menu, pattern="^menu_schedule$"))
    app.add_handler(CallbackQueryHandler(events_menu, pattern="^menu_events$"))
    app.add_handler(CallbackQueryHandler(questions_menu, pattern="^menu_questions$"))
    
    # Расписание: выбор дня
    app.add_handler(CallbackQueryHandler(schedule_menu, pattern="^menu_schedule$"))
    
    # Обработка выбора дня для дней недели (но не для "Дата")
    # Здесь шаблон "day_" с исключением "day_Дата" – точнее, мы зарегистрируем отдельно ConversationHandler для "day_Дата"
    app.add_handler(CallbackQueryHandler(day_selected, pattern="^day_(?!Дата$).*"))
    
    # ConversationHandler для кнопки "Дата"
    exact_date_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(exact_date_input_entry, pattern="^day_Дата$")],
        states={
            EXACT_DATE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_exact_date_input)]
        },
        fallbacks=[CommandHandler("cancel", back_to_main)]
    )
    app.add_handler(exact_date_conv)
    
    # Обработка просмотра расписания
    app.add_handler(CallbackQueryHandler(view_schedule, pattern="^view_"))
    
    # ConversationHandler для добавления/изменения расписания (как для дней недели, так и для точных дат)
    schedule_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(schedule_input_entry, pattern="^(add_|edit_)")],
        states={
            SCHEDULE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_input_received)]
        },
        fallbacks=[CommandHandler("cancel", back_to_main)]
    )
    app.add_handler(schedule_conv)
    # События
    app.add_handler(CallbackQueryHandler(events_view_handler, pattern="^events_view$"))
    event_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(event_input_date_entry, pattern="^events_add$")],
        states={
            EVENT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_date_received)],
            EVENT_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_description_received)]
        },
        fallbacks=[CommandHandler("cancel", back_to_events_menu)]
    )
    app.add_handler(event_conv)
    
    # Вопросы
    app.add_handler(CallbackQueryHandler(questions_view_handler, pattern="^ques_view$"))
    question_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(question_input_entry, pattern="^ques_add$")],
        states={
            QUESTION_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, question_input_received)]
        },
        fallbacks=[CommandHandler("cancel", back_to_questions_menu)]
    )
    app.add_handler(question_conv)
    
    app.run_polling()

if __name__ == '__main__':
    main()
