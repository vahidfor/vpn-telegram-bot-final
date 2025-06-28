import os
import sqlite3
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler, CallbackQueryHandler
)

# بارگذاری توکن از .env
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID"))

# اتصال به دیتابیس
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()

# ساخت جداول دیتابیس
# جدول users
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    credit INTEGER DEFAULT 0,
    discount_used INTEGER DEFAULT 0,
    is_approved INTEGER DEFAULT 0
)
""")
# جدول codes
cursor.execute("""
CREATE TABLE IF NOT EXISTS codes (
    code TEXT PRIMARY KEY,
    value INTEGER
)
""")
# جدول services (با فیلد جدید is_file برای پشتیبانی از فایل‌ها)
cursor.execute("""
CREATE TABLE IF NOT EXISTS services (
    type TEXT PRIMARY KEY,
    content TEXT,         -- ذخیره لینک/متن کانفیگ یا Telegram file_id
    is_file INTEGER DEFAULT 0 -- 0 برای متن/لینک، 1 برای فایل
)
""")
conn.commit()

# **توجه:** اگر قبلا جدول services را ایجاد کرده‌اید و می‌خواهید فیلد is_file را اضافه کنید،
# باید این خط را یک بار به صورت دستی (نه داخل کد اصلی ربات) اجرا کنید:
# cursor.execute("ALTER TABLE services ADD COLUMN IF NOT EXISTS is_file INTEGER DEFAULT 0")
# conn.commit()


# /start - شروع مکالمه با ربات
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # افزودن کاربر به دیتابیس اگر قبلا وجود ندارد
    cursor.execute("INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)", (user.id, user.username))
    conn.commit()

    # دکمه‌های Inline (شیشه‌ای) برای تمام قابلیت‌ها
    inline_keyboard_main = [
        [InlineKeyboardButton("📥 خرید اکانت", callback_data="buy_account"),
         InlineKeyboardButton("📃 دریافت برنامه", callback_data="get_app")],
        [InlineKeyboardButton("🎁 فعال‌سازی کد تخفیف", callback_data="activate_discount"),
         InlineKeyboardButton("🏦 اعتبار من", callback_data="my_credit_inline")],
        [InlineKeyboardButton("🔁 انتقال اعتبار", callback_data="transfer_credit"),
         InlineKeyboardButton("ℹ️ وضعیت من", callback_data="my_status_inline")],
        [InlineKeyboardButton("🌐 دریافت سرویس‌ها", callback_data="get_services"),
         InlineKeyboardButton("💳 افزایش اعتبار", callback_data="top_up_credit")],
        [InlineKeyboardButton("✉️ پیام به پشتیبانی", callback_data="message_support"),
         InlineKeyboardButton("درباره ما", callback_data="show_about")]
    ]

    await update.message.reply_text(
        "سلام! به ربات VPN خوش اومدی 👋\n"
        "برای دسترسی به امکانات ربات از دکمه‌های زیر استفاده کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard_main)
    )
    # اطمینان از حذف Reply Keyboard قبلی در صورت وجود (مثلا اگر قبلا استفاده شده بود)
    await update.message.reply_text("👋", reply_markup=ReplyKeyboardRemove())


# تابع جدید برای کامند /about و Callback "درباره ما"
async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    about_text = "تیم ویرا با هدف ایجاد دسترسی کامل افراد به اینترنت آزاد و بدون محدودیت شروع به کار کرد و این تیم زیر مجموعه (تیم پیوند هست )"
    if update.callback_query: # اگر از طریق دکمه شیشه‌ای صدا زده شده
        await update.callback_query.answer()
        # ویرایش پیام اصلی برای جلوگیری از پیام‌های اضافی و نمایش متن درباره ما
        await update.callback_query.message.edit_text(about_text, reply_markup=None)
    else: # اگر از طریق کامند مستقیم صدا زده شده
        await update.message.reply_text(about_text)

# توابع واسط برای ConversationHandlers که از Callback Query شروع می‌شوند (اگر لازم باشد)
# در نسخه جدید، CallbackQueryHandler را مستقیم به تابع اصلی ConversationHandler وصل می‌کنیم
# async def buy_callback_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     await update.callback_query.answer()
#     return await buy(update, context)

# توابع مستقیمی که از Callback Query شروع می‌شوند
async def my_credit_inline_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    # ویرایش پیام برای نمایش اعتبار بجای ارسال پیام جدید
    cursor.execute("SELECT credit FROM users WHERE id=?", (update.callback_query.from_user.id,))
    credit = cursor.fetchone()[0]
    await update.callback_query.message.edit_text(f"💳 اعتبار شما: {credit} تومان", reply_markup=None)

async def my_status_inline_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user = update.callback_query.from_user
    cursor.execute("SELECT credit, discount_used, is_approved FROM users WHERE id=?", (user.id,))
    credit, discount_used, approved = cursor.fetchone()
    status_text = f"""👤 @{user.username}
🆔 {user.id}
💳 اعتبار: {credit} تومان
🎁 کد تخفیف: {"استفاده شده" if discount_used else "فعال نشده"}
✅ وضعیت تأیید: {"تأیید شده" if approved else "در انتظار تأیید"}
"""
    await update.callback_query.message.edit_text(status_text, reply_markup=None)


# مرحله اول خرید اکانت: انتخاب نوع اکانت (حالا با دکمه‌های شیشه‌ای)
async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT is_approved FROM users WHERE id=?", (user_id,))
    approved = cursor.fetchone()[0]
    if not approved:
        source_message = update.callback_query.message if update.callback_query else update.message
        await source_message.reply_text("⛔ شما هنوز توسط ادمین تأیید نشده‌اید. لطفاً منتظر تأیید بمانید یا درخواست افزایش اعتبار ارسال کنید.")
        return ConversationHandler.END

    options = [[InlineKeyboardButton("1 ماهه", callback_data="buy_type_1_month"),
                InlineKeyboardButton("3 ماهه", callback_data="buy_type_3_month")],
               [InlineKeyboardButton("ویژه ❤️", callback_data="buy_type_special"),
                InlineKeyboardButton("اکسس پوینت 🏠", callback_data="buy_type_access_point")]]
    reply_markup = InlineKeyboardMarkup(options)
    source_message = update.callback_query.message if update.callback_query else update.message
    await source_message.reply_text("لطفاً نوع اکانت را انتخاب کنید:", reply_markup=reply_markup)
    return 1 # حالت برای انتظار پاسخ کاربر

# مرحله دوم خرید اکانت: ارسال درخواست به ادمین (با دکمه ارسال اکانت)
async def confirm_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    # Extract requested account type from callback_data
    # Callback data format: "buy_type_<type>"
    requested_account_type = query.data.replace("buy_type_", "").replace("_", " ")

    cursor.execute("UPDATE users SET is_approved = 0 WHERE id=?", (user.id,))
    conn.commit()

    # Generalizing the callback_data for item sending
    # Format: "send_item_to_<user_id>_<item_type>_<item_name>"
    inline_keyboard_admin = [
        [InlineKeyboardButton("✅ ارسال اکانت", callback_data=f"send_item_to_{user.id}_account_{requested_account_type}")]
    ]
    reply_markup_admin = InlineKeyboardMarkup(inline_keyboard_admin)

    msg_to_admin = (
        f"🛒 درخواست خرید اکانت جدید:\n"
        f"کاربر: @{user.username} (ID: {user.id})\n"
        f"نوع اکانت درخواستی: {requested_account_type}\n"
        f"لطفاً اکانت را ارسال کنید:"
    )
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=msg_to_admin,
        reply_markup=reply_markup_admin
    )
    await query.message.edit_text("✅ درخواست خرید شما به ادمین ارسال شد. لطفاً منتظر دریافت اکانت باشید.", reply_markup=None) # Edit message to remove buttons
    return ConversationHandler.END # پایان مکالمه

# مرحله اول دریافت برنامه: انتخاب دستگاه (حالا با دکمه‌های شیشه‌ای)
async def get_app(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("📱 اندروید", callback_data="app_type_android"),
                 InlineKeyboardButton("🍏 آیفون", callback_data="app_type_iphone")],
                [InlineKeyboardButton("🖥 ویندوز", callback_data="app_type_windows"),
                 InlineKeyboardButton("❓ راهنمای اتصال", callback_data="app_type_guide")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("دستگاه خود را انتخاب کنید:", reply_markup=reply_markup)
    return 2 # حالت برای انتظار پاسخ کاربر

# مرحله دوم دریافت برنامه: ارسال لینک یا راهنمای اتصال (حالا با CallbackQuery)
async def send_app_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected_option_data = query.data.replace("app_type_", "")

    # مسیر پایه برای تصاویر راهنما
    # **مهم:** این مسیر را به مسیر واقعی تصاویر خود تغییر دهید.
    BASE_IMAGE_PATH = "/home/Vahidfor/Image/"

    links = {
        "android": "https://play.google.com/store/apps/details?id=net.openvpn.openvpn",
        "iphone": "https://apps.apple.com/app/openvpn-connect/id590379981",
        "windows": "https://openvpn.net/client-connect-vpn-for-windows/",
        "guide": {
            "type": "guide_photos",
            "files": [
                f"{BASE_IMAGE_PATH}photo1.jpg", f"{BASE_IMAGE_PATH}photo2.jpg",
                f"{BASE_IMAGE_PATH}photo3.jpg", f"{BASE_IMAGE_PATH}photo4.jpg",
                f"{BASE_IMAGE_PATH}photo5.jpg", f"{BASE_IMAGE_PATH}photo6.jpg",
                f"{BASE_IMAGE_PATH}photo7.jpg", f"{BASE_IMAGE_PATH}photo8.jpg",
                f"{BASE_IMAGE_PATH}photo9.jpg", f"{BASE_IMAGE_PATH}photo10.jpg",
            ],
            "captions": [
                "1. برنامه OpenVPN را از استور نصب کنید و با زدن دکمه تایید وارد برنامه شوید پس از نصب، برنامه را باز کنید.",
                "2. روی تب file کلیک کنید .",
                "3. روی browse کلیک کنید .",
                "4. پوشه ای که فایل دریافتی را ذخیره کرده اید بروید.",
                "5. فایل دریافتی را انتخاب و وارد برنامه کنید.",
                "6. روی ok کلیک کنید.",
                "7. username و password دریافتی را درقسمت مشخص شده وارد کنید.",
                "8. درخواست اتصال را تایید کنید.",
                "9.اگر به متصل نشد روی دکمه کنار فایل کلیک کنید و منتظر بمانید .",
                "10.پس از اتصال موفقیت‌آمیز، وضعیت را سبز ببینید\nبرای قطع اتصال، دکمه را دوباره فشار دهید\nدر صورت بروز مشکل، ابتدا برنامه را ببندید و دوباره باز کنید\nاگر مشکل ادامه داشت، با پشتیبانی تماس بگیرید\n با آرزوی استفاده عالی از سرویس ما!",
            ],
            "additional_note": "نکته : در دستگاه های آیفون(ios) و برخی دستگاه های با اندروید قدیمی لازم است تا ابتدا فایل را باز کرده و با زدن دکمه share و انتخاب نام برنامه آن را وارد برنامه کنید و باقی مراحل را طی کنید.\nدر صورت وجود مشکل با پشتیبانی تماس بگیرید"
        }
    }

    if selected_option_data == "guide":
        guide_info = links[selected_option_data]
        if guide_info["type"] == "guide_photos":
            media = []
            for i, file_path in enumerate(guide_info["files"]):
                try:
                    with open(file_path, 'rb') as photo_file:
                        caption = guide_info["captions"][i] if i < len(guide_info["captions"]) else f"راهنما - عکس {i+1}"
                        media.append(InputMediaPhoto(media=photo_file.read(), caption=caption))
                except FileNotFoundError:
                    await query.message.reply_text(f"خطا: فایل راهنمای {file_path} پیدا نشد. لطفاً از وجود فایل‌ها در مسیر صحیح مطمئن شوید.")
                    return ConversationHandler.END
                except Exception as e:
                    await query.message.reply_text(f"خطا در بارگذاری عکس {file_path}: {e}")
                    return ConversationHandler.END

            if media:
                try:
                    await query.message.reply_media_group(media=media)
                    if "additional_note" in guide_info:
                        await query.message.reply_text(guide_info["additional_note"])
                except Exception as e:
                    await query.message.reply_text(f"خطا در ارسال گروهی تصاویر: {e}\nممکن است تصاویر خیلی بزرگ باشند یا مشکلی در API تلگرام رخ داده باشد.")
            else:
                await query.message.reply_text("هیچ عکسی برای راهنما یافت نشد.")

        else:
            await query.message.reply_text("فرمت راهنما نامعتبر است.")
    else:
        await query.message.reply_text(links.get(selected_option_data, "❌ گزینه نامعتبر"))

    await query.message.edit_reply_markup(reply_markup=None) # Remove buttons after selection
    return ConversationHandler.END

# مرحله اول دریافت سرویس‌ها: انتخاب سرویس (حالا با دکمه‌های شیشه‌ای)
async def get_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    cursor.execute("SELECT is_approved FROM users WHERE id=?", (user_id,))
    approved = cursor.fetchone()[0]
    if not approved:
        await query.message.reply_text("⛔ شما هنوز توسط ادمین تأیید نشده‌اید. لطفاً منتظر تأیید بمانید.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton("🔐 OpenVPN", callback_data="service_type_OpenVPN"),
                 InlineKeyboardButton("🛰 V2Ray", callback_data="service_type_V2Ray")],
                [InlineKeyboardButton("📡 Proxy تلگرام", callback_data="service_type_Proxy_Telegram")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("کدام سرویس را می‌خواهید؟", reply_markup=reply_markup)
    return 3 # حالت برای انتظار پاسخ کاربر

# مرحله دوم دریافت سرویس: ارسال درخواست به ادمین (مشابه خرید اکانت)
async def send_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    selected_service_type = query.data.replace("service_type_", "").replace("_", " ")

    cursor.execute("SELECT is_approved FROM users WHERE id=?", (user.id,))
    approved = cursor.fetchone()[0]
    if not approved:
        await query.message.reply_text("⛔ در انتظار تأیید توسط ادمین هستید.")
        return ConversationHandler.END

    # Set user to pending approval for this service request
    cursor.execute("UPDATE users SET is_approved = 0 WHERE id=?", (user.id,))
    conn.commit()

    # Notify admin to send the service
    inline_keyboard_admin = [
        [InlineKeyboardButton("✅ ارسال سرویس", callback_data=f"send_item_to_{user.id}_service_{selected_service_type}")]
    ]
    reply_markup_admin = InlineKeyboardMarkup(inline_keyboard_admin)

    msg_to_admin = (
        f"⚙️ درخواست دریافت سرویس جدید:\n"
        f"کاربر: @{user.username} (ID: {user.id})\n"
        f"نوع سرویس درخواستی: {selected_service_type}\n"
        f"لطفاً سرویس را ارسال کنید:"
    )
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=msg_to_admin,
        reply_markup=reply_markup_admin
    )
    await query.message.edit_text(f"✅ درخواست سرویس '{selected_service_type}' شما به ادمین ارسال شد. لطفاً منتظر دریافت سرویس باشید.", reply_markup=None)
    return ConversationHandler.END

# مرحله اول فعال‌سازی کد تخفیف
async def ask_discount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("لطفاً کد تخفیف را وارد کنید:", reply_markup=ReplyKeyboardRemove())
    return 4 # حالت برای انتظار پاسخ کاربر

# مرحله دوم فعال‌سازی کد تخفیف
async def apply_discount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    code = update.message.text.strip()

    cursor.execute("SELECT discount_used FROM users WHERE id=?", (user_id,))
    if cursor.fetchone()[0]:
        await update.message.reply_text("⛔ شما قبلاً از کد تخفیف استفاده کرده‌اید.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    cursor.execute("SELECT value FROM codes WHERE code=?", (code,))
    row = cursor.fetchone()
    if row:
        value = row[0]
        cursor.execute("UPDATE users SET credit = credit + ?, discount_used = 1 WHERE id=?", (value, user_id))
        conn.commit()
        await update.message.reply_text(f"✅ {value} تومان اعتبار اضافه شد.", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("❌ کد تخفیف نامعتبر است.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# نمایش اعتبار کاربر (مربوط به /score و دکمه شیشه‌ای اعتبار من)
async def my_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT credit FROM users WHERE id=?", (update.effective_user.id,))
    credit = cursor.fetchone()[0]
    await update.message.reply_text(f"💳 اعتبار شما: {credit} تومان")


# مرحله اول انتقال اعتبار: پرسیدن ID دریافت‌کننده
async def ask_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("لطفاً ID عددی دریافت‌کننده را وارد کنید:", reply_markup=ReplyKeyboardRemove())
    return 5 # حالت برای انتظار پاسخ کاربر

# مرحله دوم انتقال اعتبار: پرسیدن مقدار اعتبار
async def ask_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["target_id"] = int(update.message.text)
        await update.message.reply_text("چه مقدار اعتبار منتقل شود؟", reply_markup=ReplyKeyboardRemove())
        return 6 # حالت برای انتظار پاسخ کاربر
    except ValueError:
        await update.message.reply_text("❌ ID کاربر نامعتبر است. لطفاً یک عدد صحیح وارد کنید.")
        return 5 # برگشت به حالت قبلی

# مرحله سوم انتقال اعتبار: انجام انتقال
async def do_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        sender = update.effective_user.id
        receiver = context.user_data["target_id"]

        cursor.execute("SELECT credit FROM users WHERE id=?", (sender,))
        current = cursor.fetchone()[0]
        if current < amount:
            await update.message.reply_text("❌ اعتبار شما کافی نیست.", reply_markup=ReplyKeyboardRemove())
        else:
            cursor.execute("UPDATE users SET credit = credit - ? WHERE id=?", (amount, sender))
            cursor.execute("UPDATE users SET credit = credit + ? WHERE id=?", (amount, receiver))
            conn.commit()
            await update.message.reply_text("✅ انتقال انجام شد.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END # پایان مکالمه
    except ValueError:
        await update.message.reply_text("❌ مقدار اعتبار نامعتبر است. لطفاً یک عدد صحیح وارد کنید.")
        return 6 # برگشت به حالت قبلی

# نمایش وضعیت کاربر (مربوط به /myinfo و دکمه شیشه‌ای وضعیت من)
async def my_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cursor.execute("SELECT credit, discount_used, is_approved FROM users WHERE id=?", (user.id,))
    credit, discount_used, approved = cursor.fetchone()
    await update.message.reply_text(f"""👤 @{user.username}
🆔 {user.id}
💳 اعتبار: {credit} تومان
🎁 کد تخفیف: {"استفاده شده" if discount_used else "فعال نشده"}
✅ وضعیت تأیید: {"تأیید شده" if approved else "در انتظار تأیید"}
""")


# مرحله اول افزایش اعتبار: پرسیدن جزئیات پرداخت
async def ask_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("مقدار و توضیحات پرداخت خود را وارد کنید:\nمثال: 100000 - کارت به کارت به 6274xxxxxxxxxxxx", reply_markup=ReplyKeyboardRemove())
    return 7 # حالت برای انتظار پاسخ کاربر

# مرحله دوم افزایش اعتبار: ارسال درخواست به ادمین
async def send_topup_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # کاربر را به حالت انتظار تأیید برمی‌گردانیم
    cursor.execute("UPDATE users SET is_approved = 0 WHERE id=?", (update.effective_user.id,))
    conn.commit()

    msg = f"💳 درخواست افزایش اعتبار از:\n@{user.username}\n🆔 {user.id}\n💬 توضیح: {update.message.text}"
    await context.bot.send_message(chat_id=ADMIN_ID, text=msg) # ارسال پیام به ادمین
    await update.message.reply_text("✅ درخواست شما به ادمین ارسال شد. لطفاً منتظر تأیید ادمین بمانید.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END # پایان مکالمه

# پنل ادمین (حالا با دکمه‌های شیشه‌ای)
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: # بررسی دسترسی ادمین
        return
    keyboard = [
        [InlineKeyboardButton("🧾 تأیید کاربران", callback_data="admin_list_pending"),
         InlineKeyboardButton("➕ افزودن کد تخفیف", callback_data="admin_add_discount")],
        [InlineKeyboardButton("🛰 افزودن سرویس V2Ray", callback_data="admin_add_service_v2ray"),
         InlineKeyboardButton("🔐 افزودن OpenVPN", callback_data="admin_add_service_openvpn")],
        [InlineKeyboardButton("📡 افزودن Proxy تلگرام", callback_data="admin_add_service_proxy"),
         InlineKeyboardButton("💰 شارژ کاربر", callback_data="admin_charge_user")],
        [InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast")],
        [InlineKeyboardButton("✉️ چت با کاربر", callback_data="admin_chat_with_user")] # New button for chat
    ]
    await update.message.reply_text("🎛 پنل مدیریت:", reply_markup=InlineKeyboardMarkup(keyboard))

# نمایش کاربران در انتظار تأیید (حالا با اطلاعات کامل‌تر و از CallbackQuery)
async def list_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    cursor.execute("SELECT id, username, credit, discount_used, is_approved FROM users WHERE is_approved=0")
    users = cursor.fetchall()
    if not users:
        await query.message.reply_text("✅ کاربر در انتظار تأیید وجود ندارد.")
        return

    for uid, uname, credit, discount_used, is_approved_status in users:
        status_text = "تأیید شده" if is_approved_status else "در انتظار تأیید"
        discount_text = "استفاده شده" if discount_used else "استفاده نشده"
        message_text = (
            f"درخواست از: @{uname or 'N/A'}\n"
            f"ID: {uid}\n"
            f"اعتبار: {credit} تومان\n"
            f"وضعیت تخفیف: {discount_text}\n"
            f"وضعیت کلی: {status_text}"
        )
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("✅ تأیید", callback_data=f"approve_{uid}")]])
        await context.bot.send_message(chat_id=ADMIN_ID, text=message_text, reply_markup=btn)

# تأیید کاربر توسط ادمین
async def approve_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = int(query.data.split("_")[1])
    cursor.execute("UPDATE users SET is_approved=1 WHERE id=?", (uid,))
    conn.commit()
    await query.edit_message_text("✅ کاربر تأیید شد.")
    await context.bot.send_message(chat_id=uid, text="اکانت شما توسط ادمین تأیید شد. اکنون می‌توانید از خدمات استفاده کنید.")

# مرحله اول افزودن سرویس (توسط ادمین - حالا از CallbackQuery)
async def ask_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = query.data # e.g., admin_add_service_v2ray
    mapping = {
        "admin_add_service_v2ray": "v2ray",
        "admin_add_service_openvpn": "openvpn",
        "admin_add_service_proxy": "proxy"
    }
    key = mapping.get(text)
    if not key:
        return # Should not happen with correct callback data
    context.user_data["servicetype"] = key # ذخیره نوع سرویس در context
    await query.message.reply_text("لطفاً لینک، متن سرویس را وارد کنید یا **فایل مربوطه را ارسال نمایید:**", reply_markup=ReplyKeyboardRemove())
    return 8 # حالت برای انتظار پاسخ ادمین (فایل یا متن)

# مرحله دوم افزودن سرویس: ذخیره سرویس در دیتابیس
async def save_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s_type = context.user_data["servicetype"]
    is_file_flag = 0 # پیش‌فرض: متن/لینک
    content_to_save = None

    if update.message.document: # اگر پیام ادمین حاوی فایل بود
        content_to_save = update.message.document.file_id # ذخیره file_id تلگرام
        is_file_flag = 1
        await update.message.reply_text(f"✅ فایل شما با File ID: `{content_to_save}` ذخیره شد.", parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
    elif update.message.text: # اگر پیام ادمین حاوی متن بود
        content_to_save = update.message.text.strip()
        is_file_flag = 0
        await update.message.reply_text("✅ سرویس متنی/لینک ذخیره شد.", reply_markup=ReplyKeyboardRemove())
    else: # اگر نه فایل بود و نه متن
        await update.message.reply_text("❌ ورودی نامعتبر. لطفاً فایل یا متن/لینک ارسال کنید.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END # پایان مکالمه (می‌توانید حالت را نگه دارید تا ادمین دوباره تلاش کند)

    if content_to_save: # اگر محتوایی برای ذخیره وجود داشت
        cursor.execute("REPLACE INTO services (type, content, is_file) VALUES (?, ?, ?)", (s_type, content_to_save, is_file_flag))
        conn.commit()
    return ConversationHandler.END # پایان مکالمه

# مرحله اول افزودن کد تخفیف (توسط ادمین - حالا از CallbackQuery)
async def ask_discount_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("کد و مقدار را وارد کن (مثال: vip50 5000):", reply_markup=ReplyKeyboardRemove())
    return 9 # حالت برای انتظار پاسخ ادمین

# مرحله دوم افزودن کد تخفیف: ذخیره کد در دیتابیس
async def save_discount_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        code, val = update.message.text.strip().split()
        cursor.execute("INSERT INTO codes (code, value) VALUES (?, ?)", (code, int(val)))
        conn.commit()
        await update.message.reply_text("✅ کد اضافه شد.", reply_markup=ReplyKeyboardRemove())
    except:
        await update.message.reply_text("❌ فرمت اشتباه.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END # پایان مکالمه

# مرحله اول شارژ کاربر (توسط ادمین - حالا از CallbackQuery)
async def ask_charge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("ID کاربر و مبلغ (مثال: 123456789 10000):", reply_markup=ReplyKeyboardRemove())
    return 10 # حالت برای انتظار پاسخ ادمین

# مرحله دوم شارژ کاربر: انجام شارژ
async def do_charge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid, amount = update.message.text.strip().split()
        cursor.execute("UPDATE users SET credit = credit + ? WHERE id=?", (int(amount), int(uid)))
        conn.commit()
        await update.message.reply_text("✅ شارژ شد.", reply_markup=ReplyKeyboardRemove())
    except:
        await update.message.reply_text("❌ خطا در ورودی.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END # پایان مکالمه

# مرحله اول پیام همگانی (توسط ادمین - حالا از CallbackQuery)
async def ask_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("پیام همگانی را ارسال کنید:", reply_markup=ReplyKeyboardRemove())
    return 11 # حالت برای انتظار پاسخ ادمین

# مرحله دوم پیام همگانی: ارسال پیام به همه کاربران
async def send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    cursor.execute("SELECT id FROM users")
    for (uid,) in cursor.fetchall():
        try:
            await context.bot.send_message(chat_id=uid, text=msg)
        except Exception as e: # برای مدیریت خطاهای احتمالی (مثل بلاک کردن ربات)
            print(f"Error sending broadcast to {uid}: {e}")
            continue
    await update.message.reply_text("📢 پیام ارسال شد.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END # پایان مکالمه

# مرحله اول پیام به پشتیبانی
async def message_to_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("لطفاً پیام خود را برای پشتیبانی ارسال کنید:", reply_markup=ReplyKeyboardRemove())
    return 12 # حالت برای انتظار پاسخ کاربر

# مرحله دوم پیام به پشتیبانی: ارسال پیام به ادمین
async def send_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    support_message = update.message.text
    msg_for_admin = f"✉️ پیام جدید از پشتیبانی:\nکاربر: @{user.username} (ID: {user.id})\nپیام: {support_message}"

    await context.bot.send_message(chat_id=ADMIN_ID, text=msg_for_admin)
    await update.message.reply_text("✅ پیام شما به پشتیبانی ارسال شد. لطفاً منتظر پاسخ باشید.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END # پایان مکالمه

# **جدید/بهبود یافته: توابع و ثابت‌ها برای جریان ارسال اکانت/سرویس توسط ادمین**
SENDING_ITEM_DETAILS = 13 # ثابت برای حالت مکالمه ادمین (عمومی برای اکانت و سرویس)

async def start_send_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Extract user ID, item type, and item name from callback_data
    # callback_data format: "send_item_to_<user_id>_<item_type>_<item_name>"
    parts = query.data.split('_')
    target_user_id = int(parts[3])
    item_type = parts[4] # e.g., 'account', 'service'
    item_name = " ".join(parts[5:]) # e.g., '1 month', 'OpenVPN', 'Proxy Telegram'

    context.user_data['target_user_id_for_item'] = target_user_id
    context.user_data['item_type'] = item_type
    context.user_data['item_name'] = item_name

    await query.message.reply_text(
        f"لطفاً مشخصات {item_type} (نوع: {item_name}) را برای کاربر ID: {target_user_id} ارسال کنید:",
        reply_markup=ReplyKeyboardRemove() # Remove keyboard if any
    )
    # Edit the inline button message to show it's being processed
    # Also remove the button to prevent multiple clicks
    await query.edit_message_reply_markup(reply_markup=None)
    # Append a confirmation to the original message for admin's clarity
    await query.message.edit_text(query.message.text + f"\n\n✅ شما در حال آماده‌سازی {item_type} برای کاربر هستید.")

    return SENDING_ITEM_DETAILS # Go to the next state to receive item details

async def send_item_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user_id = context.user_data.get('target_user_id_for_item')
    item_type = context.user_data.get('item_type')
    item_name = context.user_data.get('item_name')
    item_details_from_admin = update.message.text # Admin's message containing item details

    if not target_user_id:
        await update.message.reply_text("خطا: شناسه کاربر مقصد یافت نشد. لطفاً دوباره تلاش کنید.")
        return ConversationHandler.END

    try:
        # Send item details to the user
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"✨ {item_type} {item_name} شما آماده شد!:\n\n{item_details_from_admin}\n\n"
                  "با آرزوی استفاده عالی از سرویس ما!"
        )
        # Inform admin
        await update.message.reply_text(f"✅ مشخصات {item_type} با موفقیت به کاربر ID: {target_user_id} ارسال شد.", reply_markup=ReplyKeyboardRemove())

        # Clear user_data for next interaction
        if 'target_user_id_for_item' in context.user_data:
            del context.user_data['target_user_id_for_item']
        if 'item_type' in context.user_data:
            del context.user_data['item_type']
        if 'item_name' in context.user_data:
            del context.user_data['item_name']

    except Exception as e:
        await update.message.reply_text(f"❌ خطا در ارسال {item_type} به کاربر ID: {target_user_id}: {e}", reply_markup=ReplyKeyboardRemove())

    return ConversationHandler.END # End the conversation

# **جدید: توابع و ثابت‌ها برای قابلیت چت ادمین با کاربر**
ADMIN_CHAT_TARGET_USER = 14
ADMIN_CHATTING = 15

# Admin initiates chat with a user
async def start_admin_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("لطفاً ID عددی کاربری که می‌خواهید با او چت کنید را وارد کنید:")
    return ADMIN_CHAT_TARGET_USER

# Admin specifies target user ID for chat
async def get_chat_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_user_id = int(update.message.text)
        context.user_data['admin_chat_target_user_id'] = target_user_id
        await update.message.reply_text(f"شما در حال چت با کاربر ID: {target_user_id} هستید.\nهر پیامی که اینجا بفرستید، برای او ارسال می‌شود.\nبرای خروج از حالت چت، /exit_chat را ارسال کنید.")
        return ADMIN_CHATTING
    except ValueError:
        await update.message.reply_text("❌ ID کاربر نامعتبر است. لطفاً یک عدد صحیح وارد کنید.")
        return ADMIN_CHAT_TARGET_USER

# Admin sends messages to the target user
async def admin_send_message_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user_id = context.user_data.get('admin_chat_target_user_id')
    if not target_user_id:
        await update.message.reply_text("خطا: شناسه کاربر مقصد برای چت یافت نشد. لطفاً دوباره تلاش کنید.")
        return ConversationHandler.END

    try:
        await context.bot.send_message(chat_id=target_user_id, text=f"پیام از ادمین: {update.message.text}")
        await update.message.reply_text("✅ پیام شما ارسال شد.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در ارسال پیام به کاربر: {e}")
    return ADMIN_CHATTING

# Admin exits chat mode
async def exit_admin_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'admin_chat_target_user_id' in context.user_data:
        del context.user_data['admin_chat_target_user_id']
    await update.message.reply_text("شما از حالت چت با کاربر خارج شدید.")
    return ConversationHandler.END


# تابع اصلی
def main():
    application = Application.builder().token(TOKEN).build()

    # ConversationHandlers (تمام entry_points به CallbackQueryHandler تغییر کرده‌اند)
    buy_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(buy, pattern="^buy_account$")],
        states={
            1: [CallbackQueryHandler(confirm_purchase, pattern="^buy_type_")],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(get_app, pattern="^get_app$")],
        states={
            2: [CallbackQueryHandler(send_app_link, pattern="^app_type_")],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    service_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(get_service, pattern="^get_services$")],
        states={
            3: [CallbackQueryHandler(send_service, pattern="^service_type_")],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    discount_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_discount, pattern="^activate_discount$")],
        states={
            4: [MessageHandler(filters.TEXT & ~filters.COMMAND, apply_discount)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    transfer_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_target, pattern="^transfer_credit$")],
        states={
            5: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_amount)],
            6: [MessageHandler(filters.TEXT & ~filters.COMMAND, do_transfer)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    topup_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_topup, pattern="^top_up_credit$")],
        states={
            7: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_topup_request)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    # Admin's Add Service Handler (entry point changed to CallbackQuery)
    admin_add_service_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(ask_service, pattern="^admin_add_service_v2ray$|^admin_add_service_openvpn$|^admin_add_service_proxy$")
        ],
        states={
            8: [MessageHandler((filters.TEXT | filters.Document) & ~filters.COMMAND, save_service)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    # Admin's Add Discount Handler (entry point changed to CallbackQuery)
    admin_add_discount_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_discount_admin, pattern="^admin_add_discount$")],
        states={
            9: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_discount_code)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    # Admin's Charge User Handler (entry point changed to CallbackQuery)
    admin_charge_user_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_charge, pattern="^admin_charge_user$")],
        states={
            10: [MessageHandler(filters.TEXT & ~filters.COMMAND, do_charge)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    # Admin's Broadcast Handler (entry point changed to CallbackQuery)
    admin_broadcast_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_broadcast, pattern="^admin_broadcast$")],
        states={
            11: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_broadcast)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    support_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(message_to_support, pattern="^message_support$")],
        states={
            12: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_support_message)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    # Generalize send_account_conv_handler to send_item_conv_handler
    send_item_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_send_item, pattern=r"^send_item_to_")],
        states={
            SENDING_ITEM_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_item_to_user)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    # New Admin Chat Conversation Handler
    admin_chat_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_admin_chat, pattern="^admin_chat_with_user$")],
        states={
            ADMIN_CHAT_TARGET_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_chat_user_id)],
            ADMIN_CHATTING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r"^\/exit_chat$"), admin_send_message_to_user),
                CommandHandler("exit_chat", exit_admin_chat)
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )


    # --- افزودن Handlers به Application ---
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin))
    application.add_handler(CommandHandler("about", about)) # /about command
    application.add_handler(CommandHandler("score", my_credit)) # /score command
    application.add_handler(CommandHandler("myinfo", my_status)) # /myinfo command

    # Add the new exit chat command handler (even though it's inside conv, useful if typed outside)
    application.add_handler(CommandHandler("exit_chat", exit_admin_chat))

    # General CallbackQueryHandlers for single actions (e.g. status/credit)
    application.add_handler(CallbackQueryHandler(my_credit_inline_handler, pattern="^my_credit_inline$"))
    application.add_handler(CallbackQueryHandler(my_status_inline_handler, pattern="^my_status_inline$"))
    application.add_handler(CallbackQueryHandler(about, pattern="^show_about$")) # Callback for "درباره ما"

    # Admin panel button handlers (all now CallbackQueryHandlers)
    application.add_handler(CallbackQueryHandler(list_pending, pattern="^admin_list_pending$"))
    application.add_handler(CallbackQueryHandler(approve_user, pattern="^approve_")) # This handler remains


    # افزودن تمام ConversationHandlers
    application.add_handler(buy_conv_handler)
    application.add_handler(app_conv_handler)
    application.add_handler(service_conv_handler)
    application.add_handler(discount_conv_handler)
    application.add_handler(transfer_conv_handler)
    application.add_handler(topup_conv_handler)
    application.add_handler(admin_add_service_conv_handler)
    application.add_handler(admin_add_discount_conv_handler)
    application.add_handler(admin_charge_user_conv_handler)
    application.add_handler(admin_broadcast_conv_handler)
    application.add_handler(support_conv_handler)
    application.add_handler(send_item_conv_handler) # Generalised item sending handler
    application.add_handler(admin_chat_conv_handler) # New chat handler


    # اجرای ربات (polling)
    print("Bot started...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
