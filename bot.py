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

# ---------------------- Настройка логирования ----------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------------- Глобальные хранилища данных ----------------------
# Расписание: ключ – день недели (например, "Понедельник") или точная дата "YYYY-MM-DD"
schedule_data = {}
# События: список событий (dict: date, description, chat_id)
events = []
# Вопросы (Входящие)
questions = []

# Зависимости:
phone_usage = {}      # Ключ: дата (YYYY-MM-DD), значение: список часов (float)
sweets_entries = []   # Список записей: {"date": "YYYY-MM-DD", "item": описание}
bad_words_entries = []  # Список записей: {"date": "YYYY-MM-DD", "word": слово}

# ---------------------- Состояния для ConversationHandler ----------------------
SCHEDULE_INPUT = 1         # Ввод расписания (add/edit)
EXACT_DATE_INPUT = 2       # Ввод точной даты при выборе "Дата"
EVENT_DATE, EVENT_DESCRIPTION = range(10, 12)  # Для событий
QUESTION_INPUT = 20        # Для вопросов
PHONE_INPUT, SWEETS_INPUT, BADWORDS_INPUT = range(100, 103)

# ---------------------- Главное меню ----------------------
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("📅 Расписание", callback_data="menu_schedule"),
         InlineKeyboardButton("📌 События", callback_data="menu_events")],
        [InlineKeyboardButton("📥 Входящие", callback_data="menu_questions"),
         InlineKeyboardButton("🚭 Зависимости", callback_data="menu_dependencies")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("<b>Главное меню</b>\nВыберите раздел:", parse_mode="HTML", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text("<b>Главное меню</b>\nВыберите раздел:", parse_mode="HTML", reply_markup=reply_markup)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await main_menu(update, context)

# ---------------------- Расписание ----------------------
async def schedule_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Обратите внимание: исправил "Пончик" на "Понедельник" и добавил префикс "day_"
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

async def day_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data  # Формат: "day_Понедельник", "day_Дата" и т.д.
    # Если выбрана "Дата", работа переходит в другой ConversationHandler
    if data == "day_Дата":
        # Запускаем отдельный диалог для ввода точной даты
        await exact_date_input_entry(update, context)
        return
    # Иначе обрабатываем как обычный день
    _, day = data.split("_", 1)
    context.user_data["selected_day"] = day
    if day in schedule_data and schedule_data[day].strip() != "":
        keyboard = [
            [InlineKeyboardButton("Просмотреть", callback_data=f"view_{day}"),
             InlineKeyboardButton("Изменить", callback_data=f"edit_{day}")],
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

async def view_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    _, day = query.data.split("_", 1)
    text = schedule_data.get(day, "Нет расписания.")
    keyboard = [[InlineKeyboardButton("Назад", callback_data="menu_schedule")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"Расписание на {day}:\n\n{text}", reply_markup=reply_markup)

async def schedule_input_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data  # Формат: "add_Понедельник" или "edit_Понедельник" (также для точных дат)
    _, day = data.split("_", 1)
    context.user_data["selected_day"] = day
    if data.startswith("add_"):
        prompt = f"Введите расписание для {day}:"
    else:
        current = schedule_data.get(day, "(пусто)")
        prompt = f"Введите новое расписание для {day}.\nТекущее: {current}\nВведите новый текст:"
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

# ConversationHandler для обработки "Дата" (точной даты)
async def exact_date_input_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
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
            [InlineKeyboardButton("Просмотреть", callback_data=f"view_{date_str}"),
             InlineKeyboardButton("Изменить", callback_data=f"edit_{date_str}")],
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

# ---------------------- Входящие (Вопросы) ----------------------
async def questions_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Добавить вопрос", callback_data="ques_add")],
         [InlineKeyboardButton("Просмотреть входящие", callback_data="ques_view")],
        [InlineKeyboardButton("Назад", callback_data="back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("Входящие:", reply_markup=reply_markup)

async def question_input_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите ваш вопрос:")
    return QUESTION_INPUT

async def question_input_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    questions.append(text)
    await update.message.reply_text("Вопрос добавлен.")
    await main_menu(update, context)
    return ConversationHandler.END

async def questions_view_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not questions:
        await query.edit_message_text("Нет входящих вопросов.")
        return
    msg = "Входящие:\n"
    for i, q in enumerate(questions, start=1):
        msg += f"{i}. {q}\n"
    keyboard = [[InlineKeyboardButton("Назад", callback_data="menu_questions")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(msg, reply_markup=reply_markup)

# ---------------------- Зависимости ----------------------
async def dependencies_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Телефон", callback_data="dep_phone_menu")],
        [InlineKeyboardButton("Сладкое", callback_data="dep_sweets_menu")],
        [InlineKeyboardButton("Плохие слова", callback_data="dep_badwords_menu")],
        [InlineKeyboardButton("Назад", callback_data="back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("Меню зависимостей:", reply_markup=reply_markup)

# ----- Телефон -----
async def dep_phone_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Добавить запись", callback_data="dep_phone_add")],
        [InlineKeyboardButton("Просмотреть отчёт", callback_data="dep_phone_view")],
        [InlineKeyboardButton("Назад", callback_data="menu_dependencies")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("Телефон: выберите действие:", reply_markup=reply_markup)

async def dep_phone_input_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Введите количество часов использования телефона за сегодня (например, 3.5):")
    return PHONE_INPUT

async def dep_phone_input_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logging.info("Вошли в dep_phone_input_received")
    text = update.message.text.strip()
    try:
        hours = float(text)
    except ValueError:
        await update.message.reply_text("Ошибка: введите число (например, 3.5). Попробуйте ещё раз:")
        return PHONE_INPUT
    today = datetime.date.today().strftime("%Y-%m-%d")
    phone_usage.setdefault(today, []).append(hours)
    await update.message.reply_text(f"Записано: {hours} часов за {today}.")
    await main_menu(update, context)
    return ConversationHandler.END

async def dep_phone_view_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    today = datetime.date.today()
    week_entries = {}
    month_entries = {}
    for date_str, hours_list in phone_usage.items():
        try:
            d = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            continue
        if (today - d).days < 7:
            week_entries[date_str] = sum(hours_list)
        if (today - d).days < 30:
            month_entries[date_str] = sum(hours_list)
    report = "<b>Телефон - Отчёт за неделю:</b>\n"
    if week_entries:
        for d, total in sorted(week_entries.items()):
            report += f"{d}: {total} часов\n"
    else:
        report += "Нет записей за неделю.\n"
    report += "\n<b>Отчёт за месяц:</b>\n"
    if month_entries:
        for d, total in sorted(month_entries.items()):
            report += f"{d}: {total} часов\n"
    else:
        report += "Нет записей за месяц."
    keyboard = [[InlineKeyboardButton("Назад", callback_data="dep_phone_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(report, parse_mode="HTML", reply_markup=reply_markup)

# ----- Сладкое -----
async def dep_sweets_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Добавить запись", callback_data="dep_sweets_add")],
        [InlineKeyboardButton("Просмотреть записи", callback_data="dep_sweets_view")],
        [InlineKeyboardButton("Назад", callback_data="menu_dependencies")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("Сладкое: выберите действие:", reply_markup=reply_markup)

async def dep_sweets_input_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Введите, что именно вы съели (например, \"шоколадка Milka\"):")
    return SWEETS_INPUT

async def dep_sweets_input_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    today = datetime.date.today().strftime("%Y-%m-%d")
    sweets_entries.append({"date": today, "item": text})
    await update.message.reply_text(f"Записано: {text} за {today}.")
    await main_menu(update, context)
    return ConversationHandler.END

async def dep_sweets_view_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    today = datetime.date.today()
    entries = [entry for entry in sweets_entries
               if (today - datetime.datetime.strptime(entry["date"], "%Y-%m-%d").date()).days < 7]
    if not entries:
        report = "Нет записей по сладкому за последние 7 дней."
    else:
        report = "<b>Сладкое - записи за неделю:</b>\n"
        for entry in entries:
            report += f"{entry['date']}: {entry['item']}\n"
    keyboard = [[InlineKeyboardButton("Назад", callback_data="dep_sweets_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(report, parse_mode="HTML", reply_markup=reply_markup)

# ----- Плохие слова -----
async def dep_badwords_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Добавить запись", callback_data="dep_badwords_add")],
        [InlineKeyboardButton("Просмотреть записи", callback_data="dep_badwords_view")],
        [InlineKeyboardButton("Назад", callback_data="menu_dependencies")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("Плохие слова: выберите действие:", reply_markup=reply_markup)

async def dep_badwords_input_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Введите плохое слово, которое вы сказали:")
    return BADWORDS_INPUT

async def dep_badwords_input_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    today = datetime.date.today().strftime("%Y-%m-%d")
    bad_words_entries.append({"date": today, "word": text})
    await update.message.reply_text(f"Записано: \"{text}\" за {today}.")
    await main_menu(update, context)
    return ConversationHandler.END

async def dep_badwords_view_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    today = datetime.date.today()
    entries = [entry for entry in bad_words_entries
               if (today - datetime.datetime.strptime(entry["date"], "%Y-%m-%d").date()).days < 7]
    if not entries:
        report = "Нет записей по плохим словам за последние 7 дней."
    else:
        report = "<b>Плохие слова - записи за неделю:</b>\n"
        for entry in entries:
            report += f"{entry['date']}: {entry['word']}\n"
    keyboard = [[InlineKeyboardButton("Назад", callback_data="dep_badwords_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(report, parse_mode="HTML", reply_markup=reply_markup)

# ---------------------- Обработчики "Назад" ----------------------
async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await main_menu(update, context)

async def back_to_dependencies_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await dependencies_menu(update, context)

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
    
    # Меню разделов
    app.add_handler(CallbackQueryHandler(schedule_menu, pattern="^menu_schedule$"))
    app.add_handler(CallbackQueryHandler(events_menu, pattern="^menu_events$"))
    app.add_handler(CallbackQueryHandler(questions_menu, pattern="^menu_questions$"))
    app.add_handler(CallbackQueryHandler(dependencies_menu, pattern="^menu_dependencies$"))
    
    # Расписание: выбор дня (для дней, не равных "Дата")
    app.add_handler(CallbackQueryHandler(day_selected, pattern="^day_(?!Дата$).*"))
    # ConversationHandler для обработки "Дата"
    exact_date_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(exact_date_input_entry, pattern="^day_Дата$")],
        states={
            EXACT_DATE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_exact_date_input)]
        },
        fallbacks=[CommandHandler("cancel", back_to_main)]
    )
    app.add_handler(exact_date_conv)
    
    # Просмотр и изменение расписания
    app.add_handler(CallbackQueryHandler(view_schedule, pattern="^view_"))
    app.add_handler(CallbackQueryHandler(schedule_input_entry, pattern="^(add_|edit_)"))
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
    
    # Зависимости - Телефон
    app.add_handler(CallbackQueryHandler(dep_phone_menu, pattern="^dep_phone_menu$"))
    app.add_handler(CallbackQueryHandler(lambda u, c: dep_phone_view_report(u, c), pattern="^dep_phone_view$"))
    phone_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(dep_phone_input_entry, pattern="^dep_phone_add$")],
        states={
            PHONE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, dep_phone_input_received)]
        },
        fallbacks=[CommandHandler("cancel", back_to_dependencies_menu)]
    )
    app.add_handler(phone_conv)
    
    # Зависимости - Сладкое
    app.add_handler(CallbackQueryHandler(dep_sweets_menu, pattern="^dep_sweets_menu$"))
    app.add_handler(CallbackQueryHandler(lambda u, c: dep_sweets_view_report(u, c), pattern="^dep_sweets_view$"))
    sweets_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(dep_sweets_input_entry, pattern="^dep_sweets_add$")],
        states={
            SWEETS_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, dep_sweets_input_received)]
        },
        fallbacks=[CommandHandler("cancel", back_to_dependencies_menu)]
    )
    app.add_handler(sweets_conv)
    
    # Зависимости - Плохие слова
    app.add_handler(CallbackQueryHandler(dep_badwords_menu, pattern="^dep_badwords_menu$"))
    app.add_handler(CallbackQueryHandler(lambda u, c: dep_badwords_view_report(u, c), pattern="^dep_badwords_view$"))
    badwords_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(dep_badwords_input_entry, pattern="^dep_badwords_add$")],
        states={
            BADWORDS_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, dep_badwords_input_received)]
        },
        fallbacks=[CommandHandler("cancel", back_to_dependencies_menu)]
    )
    app.add_handler(badwords_conv)
    
    app.run_polling()

if __name__ == '__main__':
    main()
