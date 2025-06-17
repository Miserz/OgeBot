import requests
import os
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
    PicklePersistence,
)

# Токен вашего Telegram-бота
TOKEN = os.getenv("API_KEY")
print(TOKEN)
# URL страницы с формой ОГЭ
URL = 'https://reports.43edu.ru/gia/p_stat9.php'
# URL баннера и стикера (должны быть доступны по HTTPS)
BANNER_URL = 'https://raw.githubusercontent.com/Miserz/OgeBot/refs/heads/main/img/banner.png'
WELCOME_STICKER = 'CAACAgIAAxkBAAEH7Z1j4OZVQWQK1uvjZl5rRT6W6L2zvgACZgADVp29CjoED0H-nNSDZiQE'

# Этапы разговора
MENU, ASK_PASS, ASK_CAPTCHA = range(3)

# Отображение эмодзи для оценки от 2 до 5
GRADE_EMOJI = {
    '5': '🌟',
    '4': '👍',
    '3': '🤔',
    '2': '❌'
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Приветственный стикер
    try:
        await update.effective_chat.send_sticker(WELCOME_STICKER)
    except:
        pass
    # Баннер
    try:
        banner_resp = requests.get(BANNER_URL)
        banner_resp.raise_for_status()
        await update.effective_message.reply_photo(
            photo=banner_resp.content,
            caption='<b>✨Добро пожаловать в <u>Бот Результатов ОГЭ</u>!✨</b>\nБыстро • Удобно • Надёжно',
            parse_mode='HTML'
        )
    except:
        await update.effective_message.reply_text(
            '<b>✨Добро пожаловать в Бот Результатов ОГЭ!✨</b>\nБыстро • Удобно • Надёжно',
            parse_mode='HTML'
        )

    # Запрос паспорта или меню
    if 'passport' not in context.user_data:
        await update.effective_message.reply_text(
            '<i>🆔 Введите серию и номер паспорта через пробел:</i>',
            parse_mode='HTML'
        )
        return ASK_PASS
    return await show_menu(update, context)

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton('🔍 Получить результаты', callback_data='get_results')],
        [InlineKeyboardButton('📝 Изменить паспортные данные', callback_data='change_passport')],
        [InlineKeyboardButton('ℹ️ Помощь', callback_data='help')]
    ]
    text = (
        '───────────────\n'
        '<b>📋 Главное меню</b>\n'
        '───────────────\n'
        'Выберите действие ниже:'
    )
    await update.effective_message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    return MENU

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'get_results':
        return await request_captcha(update, context)

    if data == 'change_passport':
        context.user_data.pop('passport', None)
        await query.message.reply_text(
            '<i>🔄 Введите новую серию и номер паспорта через пробел:</i>',
            parse_mode='HTML'
        )
        return ASK_PASS

    if data == 'help':
        await query.message.reply_text(
            '🛈 <b>Помощь:</b>\n'
            '1. Введите паспортные данные.\n'
            '2. Нажмите «Получить результаты».\n'
            '3. При необходимости обновите через «Изменить паспорт».',
            parse_mode='HTML'
        )
        return await show_menu(update, context)

    return MENU

async def receive_pass(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    passport = update.message.text.strip()
    try:
        series, number = passport.split()
    except ValueError:
        await update.message.reply_text(
            '<b>❌ Неверный формат!</b> Попробуйте снова:',
            parse_mode='HTML'
        )
        return ASK_PASS
    context.user_data['passport'] = (series, number)
    await update.message.reply_text(
        f'✅ <b>Данные сохранены:</b> {series} {number}',
        parse_mode='HTML'
    )
    return await show_menu(update, context)

async def request_captcha(update_or_query, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update_or_query.effective_message
    resp = requests.get(URL)
    resp.raise_for_status()
    context.user_data['cookies'] = resp.cookies

    soup = BeautifulSoup(resp.content, 'html.parser')
    sid = soup.find('input', {'name': 'captcha_sid'})['value']
    context.user_data['captcha_sid'] = sid

    img_tag = soup.find('img', {'src': lambda s: s and 'captcha.php' in s})
    img_data = requests.get('https://reports.43edu.ru' + img_tag['src']).content

    await message.reply_photo(
        photo=img_data,
        caption='<b>🔒 Введите символы с картинки:</b>',
        parse_mode='HTML'
    )
    return ASK_CAPTCHA

async def receive_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    captcha_text = update.message.text.strip()
    series, number = context.user_data['passport']
    sid = context.user_data['captcha_sid']

    data = {
        'y': '0',
        'passport_ser': series,
        'passport_num': number,
        'captcha_word': captcha_text,
        'captcha_sid': sid,
        'sv': 'Запрос'
    }
    resp2 = requests.post(URL, data=data, cookies=context.user_data['cookies'])
    resp2.raise_for_status()
    soup2 = BeautifulSoup(resp2.content, 'html.parser')

    raw = []
    for row in soup2.find_all('tr'):
        cells = row.find_all('td')
        texts = [td.get_text(strip=True) for td in cells]
        if 'Итоговый балл' in texts and 'Оценка' in texts:
            idx_s = texts.index('Итоговый балл')
            idx_g = texts.index('Оценка')
            subj = cells[idx_s-1].get_text(strip=True) if idx_s>0 else ''
            score = cells[idx_s+1].get_text(strip=True) if idx_s+1<len(cells) else ''
            grade = cells[idx_g+1].get_text(strip=True) if idx_g+1<len(cells) else ''
            raw.append((subj, score, grade))

    seen, results = set(), []
    for subj, score, grade in raw:
        if subj and subj not in seen:
            seen.add(subj)
            results.append((subj, score, grade))

    if results:
        lines = ['<b>📑 Результаты по предметам:</b>']
        for subj, score, grade in results:
            emoji = GRADE_EMOJI.get(grade, '❓')
            lines.append(f"{emoji} <b>{subj}</b>: балл <i>{score}</i>, оценка <i>{grade}</i>")
        text = '\n'.join(lines)
    else:
        text = '<i>Не найдено записей. Проверьте данные и попробуйте снова.</i>'

    await update.effective_message.reply_text(text, parse_mode='HTML')
    return await show_menu(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        '<i>❎ Запрос отменён.</i>',
        parse_mode='HTML'
    )
    return ConversationHandler.END


def main() -> None:
    # Настройка persistence для хранения данных между перезапусками
    persistence = PicklePersistence(filepath='tg_data.pkl')
    app = ApplicationBuilder()\
        .token(TOKEN)\
        .persistence(persistence)\
        .build()

    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MENU: [CallbackQueryHandler(menu_handler)],
            ASK_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_pass)],
            ASK_CAPTCHA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_captcha)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    print('Бот запущен...')
    app.run_polling()

if __name__ == '__main__':
    main()
