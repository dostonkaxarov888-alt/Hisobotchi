import logging
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

import db

# ---------- Sozlamalar ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8665808945:AAGPbX7imuIlcvwwjUI0KjV4OdywqeI6Tu4")
ADMIN_IDS = [734238587]

WAITING_ORDER_TEXT = 1

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# --- Admin uchun pastdagi doimiy tugmalar paneli ---
def get_admin_reply_keyboard():
    keyboard = [
        [KeyboardButton("➕ Buyurtma qo'shish"), KeyboardButton("📋 Ochiq buyurtmalar")],
        [KeyboardButton("📁 Jami buyurtmalar"), KeyboardButton("📊 Statistika")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# ==================== START (ADMIN VA MIJOZ) ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if is_admin(user_id):
        await update.message.reply_text(
            "Assalomu alaykum, Hurmatli Admin! 👨‍💻\n\n"
            "Bot boshqaruv paneliga xush kelibsiz. Pastdagi tugmalardan foydalaning:",
            reply_markup=get_admin_reply_keyboard()
        )
    else:
        await update.message.reply_text(
            "Assalomu alaykum! 👋\n\n"
            "Bu bot orqali kerakli mahsulotlarga buyurtma qoldirishingiz mumkin "
            "(soska, butilka, o'yinchoq mashinka va h.k.).\n\n"
            "📦 Buyurtma qoldirish: /buyurtma\n"
            "📋 Buyurtmalaringiz holati: /mening_buyurtmalarim"
        )


async def buyurtma_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Kerakli mahsulotlarni yozing, har birini alohida qatorda yuboring.\n\n"
        "Masalan:\n"
        "Soska - 2 dona\n"
        "Butilka - 1 dona\n\n"
        "📸 Xohlasangiz, mahsulot rasmini ham yuborishingiz mumkin — rasmni "
        "izoh (caption) bilan birga yuboring (masalan: \"Shundan 2 ta\").\n\n"
        "Tayyor bo'lgach, xabarni yuboring. Bekor qilish uchun /bekor"
    )
    return WAITING_ORDER_TEXT


def _parse_items(text: str):
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    items = []
    for line in lines:
        if "-" in line:
            name, qty = line.rsplit("-", 1)
            items.append((name.strip(), qty.strip()))
        else:
            items.append((line.strip(), "1 ta"))
    return items


async def _finish_order(update: Update, context: ContextTypes.DEFAULT_TYPE, items, photo_file_id=None):
    user = update.effective_user
    order_id = db.create_order(user.id, user.full_name, items, photo_file_id=photo_file_id)

    lines_preview = "\n".join(f"{i}. {n} {q}".strip() for i, (n, q) in enumerate(items, start=1))
    
    if update.message:
        await update.message.reply_text(
            f"✅ Buyurtmangiz qabul qilindi! (№{order_id})\n\n{lines_preview}\n\n"
            "Bozordan olib kelib, tayyor bo'lganda xabar beramiz.",
            reply_markup=get_admin_reply_keyboard() if is_admin(user.id) else None
        )

    admin_caption = (
        f"🆕 Yangi buyurtma №{order_id}\n"
        f"Mijoz: {user.full_name}\n\n{lines_preview}\n\n"
        f"Ko'rish uchun /buyurtmalar"
    )
    for admin_id in ADMIN_IDS:
        try:
            if photo_file_id:
                await context.bot.send_photo(admin_id, photo_file_id, caption=admin_caption, reply_markup=get_admin_reply_keyboard())
            else:
                await context.bot.send_message(admin_id, admin_caption, reply_markup=get_admin_reply_keyboard())
        except Exception as e:
            logger.warning("Adminga xabar yuborilmadi (%s): %s", admin_id, e)


async def buyurtma_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    items = _parse_items(text)
    if not items:
        await update.message.reply_text("Bo'sh xabar. Qaytadan yozing yoki /bekor bosing.")
        return WAITING_ORDER_TEXT

    await _finish_order(update, context, items)
    return ConversationHandler.END


async def buyurtma_receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    caption = (update.message.caption or "").strip()

    if not caption:
        caption = "Rasmga olingan mahsulot"

    items = _parse_items(caption)
    await _finish_order(update, context, items, photo_file_id=photo.file_id)
    return ConversationHandler.END


async def buyurtma_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Buyurtma bekor qilindi.",
        reply_markup=get_admin_reply_keyboard() if is_admin(update.effective_user.id) else None
    )
    return ConversationHandler.END


async def mening_buyurtmalarim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    orders = db.get_customer_orders(user.id)
    if not orders:
        await update.message.reply_text("Sizda hali buyurtmalar yo'q. /buyurtma orqali qoldiring.")
        return
        
    for order in orders:
        items = db.get_order_items(order["id"])
        holat = "✅ Tayyor" if order["status"] == "yopiq" else "⏳ Jarayonda"
        text = f"Buyurtma №{order['id']} — {holat}\n\n"
        for idx, it in enumerate(items, start=1):
            if it["bought"] == 1:
                mark = "✅"
            elif it["bought"] == 2:
                mark = "❌"
            else:
                mark = "⏳"
            text += f"{idx}. {mark} {it['product_name']} {it['quantity']}\n"

        if order.get("photo_file_id"):
            try:
                await update.message.reply_photo(order["photo_file_id"], caption=text)
                continue
            except Exception as e:
                logger.warning("Mijozga rasm yuborilmadi: %s", e)

        await update.message.reply_text(text)


# ==================== ADMIN UCHUN ====================

def build_open_orders_markup():
    orders = db.get_open_orders()
    keyboard = []
    for o in orders:
        item_count = db.count_items(o["id"])
        resolved_count = db.count_resolved_items(o["id"])
        keyboard.append([
            InlineKeyboardButton(
                f"№{o['id']} — {o['customer_name']} ({resolved_count}/{item_count})",
                callback_data=f"order:{o['id']}",
            )
        ])
    return orders, keyboard


async def buyurtmalar_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Bu buyruq faqat do'kon egasi uchun.")
        return
    orders, keyboard = build_open_orders_markup()
    if not orders:
        await update.message.reply_text(
            "Hozircha ochiq buyurtmalar yo'q. 🎉",
            reply_markup=get_admin_reply_keyboard(),
        )
        return
    await update.message.reply_text(
        "📋 Ochiq buyurtmalar (bozordan olib kelinishi kerak):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    text = update.message.text

    if text == "📋 Ochiq buyurtmalar":
        orders, keyboard = build_open_orders_markup()
        if not orders:
            await update.message.reply_text("Hozircha ochiq buyurtmalar yo'q. 🎉", reply_markup=get_admin_reply_keyboard())
            return
        await update.message.reply_text(
            "📋 Ochiq buyurtmalar (bozordan olib kelinishi kerak):",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif text == "➕ Buyurtma qo'shish":
        await update.message.reply_text(
            "Yangi buyurtma qo'shish uchun mahsulotlarni yozib yuboring (Masalan: Soska - 2 dona):\nBekor qilish uchun /bekor",
            reply_markup=get_admin_reply_keyboard()
        )
        return WAITING_ORDER_TEXT

    elif text == "📁 Jami buyurtmalar":
        all_orders = db.get_all_orders() if hasattr(db, "get_all_orders") else db.get_open_orders()
        keyboard = []
        for o in all_orders:
            status_emoji = "✅ Yopiq" if o["status"] == "yopiq" else "⏳ Ochiq"
            keyboard.append([
                InlineKeyboardButton(
                    f"№{o['id']} — {o['customer_name']} ({status_emoji})",
                    callback_data=f"order:{o['id']}",
                )
            ])
        if not all_orders:
            await update.message.reply_text("Hozircha bazada umuman buyurtmalar yo'q.", reply_markup=get_admin_reply_keyboard())
            return
        await update.message.reply_text(
            "📁 **Barcha buyurtmalar tarixi (Ochiq va Yopilgan):**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif text == "📊 Statistika":
        open_orders = db.get_open_orders()
        all_orders = db.get_all_orders() if hasattr(db, "get_all_orders") else open_orders
        closed_count = len(all_orders) - len(open_orders)
        
        await update.message.reply_text(
            f"📊 **Do'kon statistikasi:**\n\n"
            f"• Ochiq buyurtmalar: {len(open_orders)} ta\n"
            f"• Yopilgan (bajarilgan) buyurtmalar: {closed_count} ta\n"
            f"• Jami buyurtmalar: {len(all_orders)} ta",
            reply_markup=get_admin_reply_keyboard(),
            parse_mode="Markdown"
        )


async def show_order_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: int):
    query = update.callback_query
    order = db.get_order(order_id)
    if not order:
        await query.edit_message_text("Bu buyurtma topilmadi.")
        return
    items = db.get_order_items(order_id)

    if order.get("photo_file_id"):
        try:
            await context.bot.send_photo(
                query.message.chat_id,
                order["photo_file_id"],
                caption=f"Buyurtma №{order_id} uchun mijoz yuborgan rasm",
            )
        except Exception as e:
            logger.warning("Rasm yuborilmadi: %s", e)

    keyboard = []
    for idx, it in enumerate(items, start=1):
        keyboard.append([
            InlineKeyboardButton("✅ Xarid qilindi", callback_data=f"itemset:{it['id']}:1:{order_id}"),
            InlineKeyboardButton("❌ Yo'q", callback_data=f"itemset:{it['id']}:2:{order_id}"),
        ])

    all_resolved = all(it["bought"] != 0 for it in items) if items else False
    if all_resolved and order["status"] == "ochiq":
        keyboard.append([
            InlineKeyboardButton("✅ Buyurtmani yopish", callback_data=f"close:{order_id}")
        ])
    keyboard.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="back")])

    text = (
        f"Buyurtma №{order_id} — {order['customer_name']}\n\n"
        "Har bir mahsulot uchun ✅ Bor yoki ❌ Yo'q ni bosing — mijozga darhol xabar ketadi:"
    )
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    data = query.data

    if data == "noop":
        return

    if data == "admin_refresh" or data == "back":
        orders, keyboard = build_open_orders_markup()
        if not orders:
            await query.edit_message_text("Hozircha ochiq buyurtmalar yo'q. 🎉")
            return
        await query.edit_message_text(
            "📋 Ochiq buyurtmalar (bozordan olib kelinishi kerak):",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if data.startswith("order:"):
        order_id = int(data.split(":")[1])
        await show_order_detail(update, context, order_id)
        return

    if data.startswith("itemset:"):
        _, item_id, status, order_id = data.split(":")
        item_id, status, order_id = int(item_id), int(status), int(order_id)

        db.set_item_status(item_id, status)

        order = db.get_order(order_id)
        item = next((i for i in db.get_order_items(order_id) if i["id"] == item_id), None)
        if item and order:
            if status == 1:
                msg = f"✅ {item['product_name']} {item['quantity']} — xarid qilindi, olib kelinadi!"
            else:
                msg = f"❌ {item['product_name']} {item['quantity']} — afsuski, hozircha topilmadi."
            try:
                await context.bot.send_message(
                    order["customer_id"], f"Buyurtma №{order_id}:\n{msg}"
                )
            except Exception as e:
                logger.warning("Mijozga xabar yuborilmadi: %s", e)

        await show_order_detail(update, context, order_id)
        return

    if data.startswith("close:"):
        order_id = int(data.split(":")[1])
        db.close_order(order_id)
        order = db.get_order(order_id)
        await query.edit_message_text(f"✅ Buyurtma №{order_id} yopildi.")
        try:
            await context.bot.send_message(
                order["customer_id"],
                f"🎉 Buyurtmangiz №{order_id} tayyor! Barcha mahsulotlar olib kelindi, "
                "olib ketishingiz mumkin.",
            )
        except Exception as e:
            logger.warning("Mijozga xabar yuborilmadi: %s", e)
        return


def main():
    db.init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mening_buyurtmalarim", mening_buyurtmalarim))
    app.add_handler(CommandHandler("buyurtmalar", buyurtmalar_list))
    
    app.add_handler(MessageHandler(filters.Regex("^(➕ Buyurtma qo'shish|📋 Ochiq buyurtmalar|📁 Jami buyurtmalar|📊 Statistika)$"), admin_text_handler))

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("buyurtma", buyurtma_start),
            MessageHandler(filters.Regex("^➕ Buyurtma qo'shish$"), buyurtma_start)
        ],
        states={
            WAITING_ORDER_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, buyurtma_receive),
                MessageHandler(filters.PHOTO, buyurtma_receive_photo),
            ],
        },
        fallbacks=[CommandHandler("bekor", buyurtma_cancel)],
    )

    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
