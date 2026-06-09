"""
🏠 Бот для агента по недвижимости
- Квалификация лидов (семейная ипотека, дедлайн 1 июля)
- Рассылка по базе
- Уведомления агенту о новых лидах

Установка:
    pip install aiogram==3.3.0

Запуск:
    1. Создай бота через @BotFather → получи TOKEN
    2. Узнай свой Telegram ID через @userinfobot → вставь в AGENT_ID
    3. python realty_bot.py
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ─── НАСТРОЙКИ ───────────────────────────────────────────────
BOT_TOKEN = "8829263710:AAF1WiPwCtczXva6o5f4IJ978KK9B0SUeGo"   # Токен от @BotFather
AGENT_ID  = 478038092              # Твой Telegram ID
# ─────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

# База лидов (в памяти; для продакшена замени на SQLite/PostgreSQL)
leads: dict = {}


# ══════════════════════════════════════════════════════════════
#  СОСТОЯНИЯ FSM
# ══════════════════════════════════════════════════════════════
class Qualify(StatesGroup):
    has_child    = State()
    child_age    = State()
    has_mortgage = State()
    budget       = State()
    timeline     = State()
    name         = State()
    phone        = State()

class Broadcast(StatesGroup):
    message = State()


# ══════════════════════════════════════════════════════════════
#  СТАРТ
# ══════════════════════════════════════════════════════════════
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, есть ребёнок", callback_data="child_yes")
    kb.button(text="❌ Нет детей",         callback_data="child_no")
    kb.adjust(1)

    await message.answer(
        "👋 Привет! Я помогу вам разобраться с семейной ипотекой.\n\n"
        "⚠️ *Важно:* с 1 июля ставка вырастет с 6% до 12%.\n"
        "Осталось совсем мало времени!\n\n"
        "У вас есть ребёнок до 18 лет?",
        parse_mode="Markdown",
        reply_markup=kb.as_markup()
    )
    await state.set_state(Qualify.has_child)


# ══════════════════════════════════════════════════════════════
#  КВАЛИФИКАЦИЯ
# ══════════════════════════════════════════════════════════════
@dp.callback_query(Qualify.has_child, F.data == "child_no")
async def no_child(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "Семейная ипотека под 6% доступна только семьям с детьми.\n\n"
        "Но у нас есть и другие программы! Напишите нам: @agent_username"
    )
    await state.clear()


@dp.callback_query(Qualify.has_child, F.data == "child_yes")
async def has_child(call: CallbackQuery, state: FSMContext):
    await state.update_data(has_child=True)
    await call.message.edit_text(
        "Отлично! Вы подходите под *семейную ипотеку 6%* 🎉\n\n"
        "До 1 июля можно успеть оформить по выгодной ставке.\n\n"
        "Вы уже рассматривали ипотеку или пока только думаете?",
        parse_mode="Markdown",
        reply_markup=_kb([
            ("🔥 Готов(а) оформлять", "mortgage_ready"),
            ("🤔 Изучаю варианты",    "mortgage_thinking"),
            ("❓ Первый раз слышу",   "mortgage_new"),
        ])
    )
    await state.set_state(Qualify.has_mortgage)


@dp.callback_query(Qualify.has_mortgage)
async def mortgage_status(call: CallbackQuery, state: FSMContext):
    await state.update_data(mortgage=call.data)
    await call.message.edit_text(
        "Хорошо! Какую сумму рассматриваете?\n\n"
        "Это поможет подобрать подходящие варианты 👇",
        reply_markup=_kb([
            ("до 3 млн ₽",    "budget_3"),
            ("3–6 млн ₽",     "budget_6"),
            ("6–10 млн ₽",    "budget_10"),
            ("от 10 млн ₽",   "budget_10plus"),
        ])
    )
    await state.set_state(Qualify.budget)


@dp.callback_query(Qualify.budget)
async def budget_chosen(call: CallbackQuery, state: FSMContext):
    await state.update_data(budget=call.data)
    await call.message.edit_text(
        "Когда планируете купить квартиру?",
        reply_markup=_kb([
            ("🔥 Срочно, до 1 июля", "timeline_asap"),
            ("В этом году",          "timeline_year"),
            ("Пока присматриваюсь",  "timeline_later"),
        ])
    )
    await state.set_state(Qualify.timeline)


@dp.callback_query(Qualify.timeline)
async def timeline_chosen(call: CallbackQuery, state: FSMContext):
    await state.update_data(timeline=call.data)
    await call.message.edit_text(
        "Отлично! Как вас зовут? (Имя и фамилия) 👇"
    )
    await state.set_state(Qualify.name)


@dp.message(Qualify.name)
async def got_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Оставьте ваш номер телефона для связи 📞")
    await state.set_state(Qualify.phone)


@dp.message(Qualify.phone)
async def got_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text)
    data = await state.get_data()

    # Сохраняем лид
    leads[message.from_user.id] = {
        "name":     data.get("name"),
        "phone":    data.get("phone"),
        "budget":   data.get("budget"),
        "timeline": data.get("timeline"),
        "mortgage": data.get("mortgage"),
        "user_id":  message.from_user.id,
    }

    # Уведомление агенту
    budget_map   = {"budget_3": "до 3 млн", "budget_6": "3–6 млн",
                    "budget_10": "6–10 млн", "budget_10plus": "от 10 млн"}
    timeline_map = {"timeline_asap": "🔥 Срочно до 1 июля",
                    "timeline_year": "В этом году", "timeline_later": "Присматривается"}
    mortgage_map = {"mortgage_ready": "Готов оформлять",
                    "mortgage_thinking": "Изучает варианты", "mortgage_new": "Первый раз слышит"}

    await bot.send_message(
        AGENT_ID,
        f"🏠 *Новый лид!*\n\n"
        f"👤 Имя: {data.get('name')}\n"
        f"📞 Телефон: {data.get('phone')}\n"
        f"💰 Бюджет: {budget_map.get(data.get('budget', ''), '—')}\n"
        f"📅 Срок: {timeline_map.get(data.get('timeline', ''), '—')}\n"
        f"📊 Статус: {mortgage_map.get(data.get('mortgage', ''), '—')}\n"
        f"🆔 TG ID: {message.from_user.id}",
        parse_mode="Markdown"
    )

    await message.answer(
        f"✅ {data.get('name')}, спасибо!\n\n"
        "Наш агент свяжется с вами в течение 30 минут и подберёт лучший вариант.\n\n"
        "⏰ Напоминаем: до 1 июля ставка 6% — действуйте быстрее!"
    )
    await state.clear()


# ══════════════════════════════════════════════════════════════
#  РАССЫЛКА (только для агента)
# ══════════════════════════════════════════════════════════════
@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != AGENT_ID:
        return
    if not leads:
        await message.answer("📭 База лидов пока пустая.")
        return
    await message.answer(
        f"📨 Напиши текст рассылки.\n"
        f"Получат: {len(leads)} человек(а)"
    )
    await state.set_state(Broadcast.message)


@dp.message(Broadcast.message)
async def do_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != AGENT_ID:
        return
    text = message.text
    sent = 0
    for uid in leads:
        try:
            await bot.send_message(uid, text)
            sent += 1
        except Exception:
            pass
    await message.answer(f"✅ Рассылка отправлена: {sent} из {len(leads)}")
    await state.clear()


@dp.message(Command("leads"))
async def cmd_leads(message: Message):
    """Список лидов для агента"""
    if message.from_user.id != AGENT_ID:
        return
    if not leads:
        await message.answer("📭 Лидов пока нет.")
        return
    text = "📋 *Список лидов:*\n\n"
    for i, (_, lead) in enumerate(leads.items(), 1):
        text += f"{i}. {lead['name']} — {lead['phone']}\n"
    await message.answer(text, parse_mode="Markdown")


# ══════════════════════════════════════════════════════════════
#  ХЕЛПЕР
# ══════════════════════════════════════════════════════════════
def _kb(buttons: list[tuple[str, str]]):
    kb = InlineKeyboardBuilder()
    for label, data in buttons:
        kb.button(text=label, callback_data=data)
    kb.adjust(1)
    return kb.as_markup()


# ══════════════════════════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════════════════════════
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
