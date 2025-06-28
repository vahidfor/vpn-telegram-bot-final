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
         InlineKeyboardButton("🏦 اعتبار من", callback_data="my_credit_inline")], # Changed callback
        [InlineKeyboardButton("🔁 انتقال اعتبار", callback_data="transfer_credit"),
         InlineKeyboardButton("ℹ️ وضعیت من", callback_data="my_status_inline")], # Changed callback
        [InlineKeyboardButton("🌐 دریافت سرویس‌ها", callback_data="get_services"),
         InlineKeyboardButton("💳 افزایش اعتبار", callback_data="top_up_credit")],
        [InlineKeyboardButton("✉️ پیام به پشتیبانی", callback_data="message_support"),
         InlineKeyboardButton("درباره ما", callback_data="show_about")] # From previous step
    ]

    # افزودن دکمه ادمین فقط اگر کاربر ادمین باشد. این دکمه را می‌توان همچنان به عنوان یک ReplyKeyboard گذاشت
    # یا می‌توان آن را نیز به Inline Keyboard منتقل کرد. برای سادگی، به عنوان کامند یا یک دکمه جدا نگه می‌داریم
    # اگر نیاز باشد کامند /admin را نیز به Inline Button تبدیل کنیم، باید یک callback_data و Handler جدا برای آن ساخت.
    # فعلاً به درخواست قبلی (کامندها به صورت کامند بمانند) پایبندیم.

    await update.message.reply_text(
        "سلام! به ربات VPN خوش اومدی 👋\n"
        "برای دسترسی به امکانات ربات از دکمه‌های زیر استفاده کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard_main)
    )
    # اطمینان از حذف Reply Keyboard قبلی
    await update.message.reply_text("👋", reply_markup=ReplyKeyboardRemove())


# تابع جدید برای کامند /about و Callback "درباره ما"
async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    about_text = "تیم ویرا با هدف ایجاد دسترسی کامل افراد به اینترنت آزاد و بدون محدودیت شروع به کار کرد و این تیم زیر مجموعه (تیم پیوند هست )"
    if update.callback_query: # اگر از طریق دکمه شیشه‌ای صدا زده شده
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(about_text) # Reply to the message where the inline button was clicked
    else: # اگر از طریق کامند مستقیم صدا زده شده
        await update.message.reply_text(about_text)

# توابع واسط برای ConversationHandlers که از Callback Query شروع می‌شوند
async def buy_callback_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    return await buy(update, context)

async def get_app_callback_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    return await get_app(update, context)

async def activate_discount_callback_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    return await ask_discount(update, context)

async def transfer_credit_callback_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    return await ask_target(update, context)

async def get_services_callback_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    return await get_service(update, context)

async def top_up_credit_callback_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    return await ask_topup(update, context)

async def message_support_callback_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    return await message_to_support(update, context)

# توابع مستقیمی که از Callback Query شروع می‌شوند
async def my_credit_inline_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    # update.callback_query.message را به update.message تبدیل می‌کنیم تا تابع my_credit بدون تغییر کار کند
    update._message = update.callback_query.message
    await my_credit(update, context)

async def my_status_inline_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    # update.callback_query.message را به update.message تبدیل می‌کنیم تا تابع my_status بدون تغییر کار کند
    update._message = update.callback_query.message
    await my_status(update, context)


# مرحله اول خرید اکانت: انتخاب نوع اکانت
async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT is_approved FROM users WHERE id=?", (user_id,))
    approved = cursor.fetchone()[0]
    if not approved:
        # اگر از طریق callback_query آمده، باید به پیام اصلی پاسخ دهد
        if update.callback_query:
            await update.callback_query.message.reply_text("⛔ شما هنوز توسط ادمین تأیید نشده‌اید. لطفاً منتظر تأیید بمانید یا درخواست افزایش اعتبار ارسال کنید.")
        else:
            await update.message.reply_text("⛔ شما هنوز توسط ادمین تأیید نشده‌اید. لطفاً منتظر تأیید بمانید یا درخواست افزایش اعتبار ارسال کنید.")
        return ConversationHandler.END

    options = [["1 ماهه", "3 ماهه"], ["ویژه ❤️", "اکسس پوینت 🏠"]]
    # پاسخ با ReplyKeyboardMarkup برای انتخاب گزینه‌ها در مکالمه
    reply_markup = ReplyKeyboardMarkup(options, resize_keyboard=True, one_time_keyboard=True)
    if update.callback_query:
        await update.callback_query.message.reply_text("لطفاً نوع اکانت را انتخاب کنید:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("لطفاً نوع اکانت را انتخاب کنید:", reply_markup=reply_markup)
    return 1 # حالت برای انتظار پاسخ کاربر

# مرحله دوم خرید اکانت: ارسال درخواست به ادمین (با دکمه ارسال اکانت)
async def confirm_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    requested_account_type = update.message.text # e.g., "1 ماهه"

    # کاربر را به حالت انتظار تأیید برمی‌گردانیم (برای نمایش در لیست "تأیید کاربران" و جلوگیری از درخواست‌های بعدی تا ادمین رسیدگی کند)
    cursor.execute("UPDATE users SET is_approved = 0 WHERE id=?", (user.id,))
    conn.commit()

    # ایجاد دکمه اینلاین برای ادمین جهت ارسال اکانت
    inline_keyboard_admin = [
        [InlineKeyboardButton("✅ ارسال اکانت", callback_data=f"send_acc_to_{user.id}_{requested_account_type}")]
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
    await update.message.reply_text("✅ درخواست خرید شما به ادمین ارسال شد. لطفاً منتظر دریافت اکانت باشید.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END # پایان مکالمه

# مرحله اول دریافت برنامه: انتخاب دستگاه
async def get_app(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["📱 اندروید", "🍏 آیفون"], ["🖥 ویندوز", "❓ راهنمای اتصال"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    if update.callback_query:
        await update.callback_query.message.reply_text("دستگاه خود را انتخاب کنید:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("دستگاه خود را انتخاب کنید:", reply_markup=reply_markup)
    return 2 # حالت برای انتظار پاسخ کاربر

# مرحله دوم دریافت برنامه: ارسال لینک یا راهنمای اتصال
async def send_app_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # مسیر پایه برای تصاویر راهنما
    # **مهم:** این مسیر را به مسیر واقعی تصاویر خود تغییر دهید.
    BASE_IMAGE_PATH = "/home/Vahidfor/Image/"

    links = {
        "📱 اندروید": "https://play.google.com/store/apps/details?id=net.openvpn.openvpn",
        "🍏 آیفون": "https://apps.apple.com/app/openvpn-connect/id590379981",
        "🖥 ویندوز": "https://openvpn.net/client-connect-vpn-for-windows/",
        "❓ راهنمای اتصال": {
            "type": "guide_photos",
            "files": [
                f"{BASE_IMAGE_PATH}photo1.jpg",
                f"{BASE_IMAGE_PATH}photo2.jpg",
                f"{BASE_IMAGE_PATH}photo3.jpg",
                f"{BASE_IMAGE_PATH}photo4.jpg",
                f"{BASE_IMAGE_PATH}photo5.jpg",
                f"{BASE_IMAGE_PATH}photo6.jpg",
                f"{BASE_IMAGE_PATH}photo7.jpg",
                f"{BASE_IMAGE_PATH}photo8.jpg",
                f"{BASE_IMAGE_PATH}photo9.jpg",
                f"{BASE_IMAGE_PATH}photo10.jpg",
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

    selected_option = update.message.text

    if selected_option == "❓ راهنمای اتصال":
        guide_info = links[selected_option]
        if guide_info["type"] == "guide_photos":
            media = []
            for i, file_path in enumerate(guide_info["files"]):
                try:
                    with open(file_path, 'rb') as photo_file:
                        caption = guide_info["captions"][i] if i < len(guide_info["captions"]) else f"راهنما - عکس {i+1}"
                        media.append(InputMediaPhoto(media=photo_file.read(), caption=caption))
                except FileNotFoundError:
                    await update.message.reply_text(f"خطا: فایل راهنمای {file_path} پیدا نشد. لطفاً از وجود فایل‌ها در مسیر صحیح مطمئن شوید.")
                    return ConversationHandler.END
                except Exception as e:
                    await update.message.reply_text(f"خطا در بارگذاری عکس {file_path}: {e}")
                    return ConversationHandler.END

            if media:
                try:
                    await update.message.reply_media_group(media=media) # ارسال آلبوم تصاویر
                    if "additional_note" in guide_info:
                        await update.message.reply_text(guide_info["additional_note"]) # ارسال متن نکته جداگانه
                except Exception as e:
                    await update.message.reply_text(f"خطا در ارسال گروهی تصاویر: {e}\nممکن است تصاویر خیلی بزرگ باشند یا مشکلی در API تلگرام رخ داده باشد.")
            else:
                await update.message.reply_text("هیچ عکسی برای راهنما یافت نشد.")

        else:
            await update.message.reply_text("فرمت راهنما نامعتبر است.")
    else:
        await update.message.reply_text(links.get(selected_option, "❌ گزینه نامعتبر"))

    await update.message.reply_text("👋", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# مرحله اول دریافت سرویس‌ها: انتخاب سرویس
async def get_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT is_approved FROM users WHERE id=?", (user_id,))
    approved = cursor.fetchone()[0]
    if not approved:
        if update.callback_query:
            await update.callback_query.message.reply_text("⛔ شما هنوز توسط ادمین تأیید نشده‌اید. لطفاً منتظر تأیید بمانید.")
        else:
            await update.message.reply_text("⛔ شما هنوز توسط ادمین تأیید نشده‌اید. لطفاً منتظر تأیید بمانید.")
        return ConversationHandler.END

    keyboard = [["🔐 OpenVPN", "🛰 V2Ray"], ["📡 Proxy تلگرام"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    if update.callback_query:
        await update.callback_query.message.reply_text("کدام سرویس را می‌خواهید؟", reply_markup=reply_markup)
    else:
        await update.message.reply_text("کدام سرویس را می‌خواهید؟", reply_markup=reply_markup)
    return 3 # حالت برای انتظار پاسخ کاربر

# مرحله دوم دریافت سرویس: ارسال سرویس به کاربر
async def send_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute("SELECT is_approved FROM users WHERE id=?", (user_id,))
    approved = cursor.fetchone()[0]
    if not approved:
        await update.message.reply_text("⛔ در انتظار تأیید توسط ادمین هستید.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    text = update.message.text
    mapping = {
        "🔐 OpenVPN": "openvpn",
        "🛰 V2Ray": "v2ray",
        "📡 Proxy تلگرام": "proxy"
    }
    key = mapping.get(text)
    if not key:
        await update.message.reply_text("❌ سرویس نامعتبر", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    # خواندن content و is_file از دیتابیس
    cursor.execute("SELECT content, is_file FROM services WHERE type=?", (key,))
    row = cursor.fetchone()
    if row:
        content, is_file = row[0], row[1]
        if is_file == 1: # اگر محتوا یک فایل باشد (file_id)
            try:
                # ارسال فایل با استفاده از file_id ذخیره شده
                await context.bot.send_document(chat_id=update.message.chat_id, document=content, caption="✅ فایل سرویس شما:")
                await update.message.reply_text("توجه: وضعیت شما به 'در انتظار تأیید' تغییر کرد. برای درخواست‌های بعدی منتظر تأیید ادمین باشید.", reply_markup=ReplyKeyboardRemove())
                cursor.execute("UPDATE users SET is_approved = 0 WHERE id=?", (user_id,))
                conn.commit()
            except Exception as e:
                await update.message.reply_text(f"❌ خطا در ارسال فایل سرویس: {e}\nلطفاً با پشتیبانی تماس بگیرید.", reply_markup=ReplyKeyboardRemove())
        else: # اگر محتوا متن/لینک باشد
            await update.message.reply_text(f"✅ لینک/فایل سرویس شما:\n{content}", reply_markup=ReplyKeyboardRemove())
            await update.message.reply_text("توجه: وضعیت شما به 'در انتظار تأیید' تغییر کرد. برای درخواست‌های بعدی منتظر تأیید ادمین باشید.", reply_markup=ReplyKeyboardRemove())
            cursor.execute("UPDATE users SET is_approved = 0 WHERE id=?", (user_id,))
            conn.commit()
    else:
        await update.message.reply_text("⛔ سرویس فعلاً تنظیم نشده.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# مرحله اول فعال‌سازی کد تخفیف
async def ask_discount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.message.reply_text("لطفاً کد تخفیف را وارد کنید:", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("لطفاً کد تخفیف را وارد کنید:", reply_markup=ReplyKeyboardRemove())
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
    await update.message.reply_text(f"💳 اعتبار شما: {credit} تومان") # No ReplyKeyboardRemove needed here, as it's a direct info


# مرحله اول انتقال اعتبار: پرسیدن ID دریافت‌کننده
async def ask_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.message.reply_text("لطفاً ID عددی دریافت‌کننده را وارد کنید:", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("لطفاً ID عددی دریافت‌کننده را وارد کنید:", reply_markup=ReplyKeyboardRemove())
    return 5 # حالت برای انتظار پاسخ کاربر

# مرحله دوم انتقال اعتبار: پرسیدن مقدار اعتبار
async def ask_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["target_id"] = int(update.message.text)
    await update.message.reply_text("چه مقدار اعتبار منتقل شود؟", reply_markup=ReplyKeyboardRemove())
    return 6 # حالت برای انتظار پاسخ کاربر

# مرحله سوم انتقال اعتبار: انجام انتقال
async def do_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
""") # No ReplyKeyboardRemove needed here, as it's a direct info


# مرحله اول افزایش اعتبار: پرسیدن جزئیات پرداخت
async def ask_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.message.reply_text("مقدار و توضیحات پرداخت خود را وارد کنید:\nمثال: 100000 - کارت به کارت به 6274xxxxxxxxxxxx", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("مقدار و توضیحات پرداخت خود را وارد کنید:\nمثال: 100000 - کارت به کارت به 6274xxxxxxxxxxxx", reply_markup=ReplyKeyboardRemove())
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

# پنل ادمین
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: # بررسی دسترسی ادمین
        return
    keyboard = [
        ["🧾 تأیید کاربران", "➕ افزودن کد تخفیف"],
        ["🛰 افزودن سرویس V2Ray", "🔐 افزودن OpenVPN"],
        ["📡 افزودن Proxy تلگرام", "💰 شارژ کاربر"],
        ["📢 پیام همگانی"]
    ]
    await update.message.reply_text("🎛 پنل مدیریت:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

# نمایش کاربران در انتظار تأیید
async def list_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT id, username FROM users WHERE is_approved=0")
    users = cursor.fetchall()
    if not users:
        await update.message.reply_text("✅ کاربر در انتظار تأیید وجود ندارد.")
        return
    for uid, uname in users:
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("✅ تأیید", callback_data=f"approve_{uid}")]])
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"درخواست از: @{uname} | ID: {uid}", reply_markup=btn)

# تأیید کاربر توسط ادمین
async def approve_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = int(query.data.split("_")[1])
    cursor.execute("UPDATE users SET is_approved=1 WHERE id=?", (uid,))
    conn.commit()
    await query.edit_message_text("✅ کاربر تأیید شد.")
    await context.bot.send_message(chat_id=uid, text="اکانت شما توسط ادمین تأیید شد. اکنون می‌توانید از خدمات استفاده کنید.")

# مرحله اول افزودن سرویس (توسط ادمین)
async def ask_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    mapping = {
        "🛰 افزودن سرویس V2Ray": "v2ray",
        "🔐 افزودن OpenVPN": "openvpn",
        "📡 افزودن Proxy تلگرام": "proxy"
    }
    key = mapping.get(text)
    if not key:
        return
    context.user_data["servicetype"] = key # ذخیره نوع سرویس در context
    await update.message.reply_text("لطفاً لینک، متن سرویس را وارد کنید یا **فایل مربوطه را ارسال نمایید:**", reply_markup=ReplyKeyboardRemove())
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

# مرحله اول افزودن کد تخفیف (توسط ادمین)
async def ask_discount_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("کد و مقدار را وارد کن (مثال: vip50 5000):", reply_markup=ReplyKeyboardRemove())
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

# مرحله اول شارژ کاربر (توسط ادمین)
async def ask_charge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ID کاربر و مبلغ (مثال: 123456789 10000):", reply_markup=ReplyKeyboardRemove())
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

# مرحله اول پیام همگانی (توسط ادمین)
async def ask_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("پیام همگانی را ارسال کنید:", reply_markup=ReplyKeyboardRemove())
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
    if update.callback_query:
        await update.callback_query.message.reply_text("لطفاً پیام خود را برای پشتیبانی ارسال کنید:", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("لطفاً پیام خود را برای پشتیبانی ارسال کنید:", reply_markup=ReplyKeyboardRemove())
    return 12 # حالت برای انتظار پاسخ کاربر

# مرحله دوم پیام به پشتیبانی: ارسال پیام به ادمین
async def send_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    support_message = update.message.text
    msg_for_admin = f"✉️ پیام جدید از پشتیبانی:\nکاربر: @{user.username} (ID: {user.id})\nپیام: {support_message}"

    await context.bot.send_message(chat_id=ADMIN_ID, text=msg_for_admin)
    await update.message.reply_text("✅ پیام شما به پشتیبانی ارسال شد. لطفاً منتظر پاسخ باشید.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END # پایان مکالمه

# **جدید: توابع و ثابت‌ها برای جریان ارسال اکانت توسط ادمین**
SENDING_ACCOUNT_DETAILS = 13 # ثابت برای حالت مکالمه ادمین

# New admin function to start sending account details
async def start_send_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Extract user ID and requested account type from callback_data
    # callback_data format: "send_acc_to_<user_id>_<account_type>"
    parts = query.data.split('_')
    target_user_id = int(parts[3])
    # Reconstruct account type, as it might contain spaces
    requested_account_type = " ".join(parts[4:])

    # Store in context.user_data for the next state
    context.user_data['target_user_id_for_account'] = target_user_id
    context.user_data['requested_account_type'] = requested_account_type

    await query.message.reply_text(
        f"لطفاً مشخصات اکانت (مثلاً: لینک کانفیگ، یوزرنیم، پسورد) را برای کاربر ID: {target_user_id} (نوع: {requested_account_type}) ارسال کنید:",
        reply_markup=ReplyKeyboardRemove() # Remove keyboard if any
    )
    # Edit the inline button message to show it's being processed
    # Also remove the button to prevent multiple clicks
    await query.edit_message_reply_markup(reply_markup=None)
    # Append a confirmation to the original message for admin's clarity
    await query.message.edit_text(query.message.text + "\n\n✅ شما در حال آماده‌سازی اکانت برای کاربر هستید.")

    return SENDING_ACCOUNT_DETAILS # Go to the next state to receive account details

# New admin function to send the account details to the user
async def send_account_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user_id = context.user_data.get('target_user_id_for_account')
    requested_account_type = context.user_data.get('requested_account_type')
    account_details_from_admin = update.message.text # Admin's message containing account details

    if not target_user_id:
        await update.message.reply_text("خطا: شناسه کاربر مقصد یافت نشد. لطفاً دوباره تلاش کنید.")
        return ConversationHandler.END

    try:
        # Send account details to the user
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"✨ اکانت {requested_account_type} شما آماده شد!:\n\n{account_details_from_admin}\n\n"
                  "با آرزوی استفاده عالی از سرویس ما!"
        )
        # Inform admin
        await update.message.reply_text(f"✅ مشخصات اکانت با موفقیت به کاربر ID: {target_user_id} ارسال شد.", reply_markup=ReplyKeyboardRemove())

        # Clear user_data for next interaction
        if 'target_user_id_for_account' in context.user_data:
            del context.user_data['target_user_id_for_account']
        if 'requested_account_type' in context.user_data:
            del context.user_data['requested_account_type']

    except Exception as e:
        await update.message.reply_text(f"❌ خطا در ارسال اکانت به کاربر ID: {target_user_id}: {e}", reply_markup=ReplyKeyboardRemove())

    return ConversationHandler.END # End the conversation


# تابع اصلی
def main():
    application = Application.builder().token(TOKEN).build()

    # ConversationHandlers (با entry_points جدید برای CallbackQuery)
    buy_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(buy_callback_entry, pattern="^buy_account$")],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_purchase)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(get_app_callback_entry, pattern="^get_app$")],
        states={
            2: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_app_link)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    service_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(get_services_callback_entry, pattern="^get_services$")],
        states={
            3: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_service)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    discount_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(activate_discount_callback_entry, pattern="^activate_discount$")],
        states={
            4: [MessageHandler(filters.TEXT & ~filters.COMMAND, apply_discount)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    transfer_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(transfer_credit_callback_entry, pattern="^transfer_credit$")],
        states={
            5: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_amount)],
            6: [MessageHandler(filters.TEXT & ~filters.COMMAND, do_transfer)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    topup_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(top_up_credit_callback_entry, pattern="^top_up_credit$")],
        states={
            7: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_topup_request)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    admin_add_service_conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^(🛰 افزودن سرویس V2Ray|🔐 افزودن OpenVPN|📡 افزودن Proxy تلگرام)$") & filters.User(ADMIN_ID), ask_service)
        ],
        states={
            8: [MessageHandler((filters.TEXT | filters.Document) & ~filters.COMMAND, save_service)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    admin_add_discount_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ افزودن کد تخفیف$") & filters.User(ADMIN_ID), ask_discount_admin)],
        states={
            9: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_discount_code)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    admin_charge_user_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💰 شارژ کاربر$") & filters.User(ADMIN_ID), ask_charge)],
        states={
            10: [MessageHandler(filters.TEXT & ~filters.COMMAND, do_charge)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    admin_broadcast_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📢 پیام همگانی$") & filters.User(ADMIN_ID), ask_broadcast)],
        states={
            11: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_broadcast)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    support_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(message_support_callback_entry, pattern="^message_support$")],
        states={
            12: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_support_message)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    # **جدید: ConversationHandler برای ارسال اکانت توسط ادمین**
    send_account_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_send_account, pattern=r"^send_acc_to_")], # Using regex for dynamic callback data
        states={
            SENDING_ACCOUNT_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_account_to_user)],
        },
        fallbacks=[CommandHandler("start", start)],
    )


    # افزودن CommandHandlers (این‌ها تغییری نکردند)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin))
    application.add_handler(CommandHandler("about", about))
    application.add_handler(CommandHandler("score", my_credit))
    application.add_handler(CommandHandler("myinfo", my_status))

    # افزودن CallbackQueryHandlers برای دکمه‌های شیشه‌ای مستقل
    application.add_handler(CallbackQueryHandler(my_credit_inline_handler, pattern="^my_credit_inline$"))
    application.add_handler(CallbackQueryHandler(my_status_inline_handler, pattern="^my_status_inline$"))
    application.add_handler(CallbackQueryHandler(about, pattern="^show_about$")) # Using 'about' function for callback as well

    # Handlers مربوط به پنل ادمین (که از MessageHandler استفاده می‌کنند و نیازی به تغییر به CallbackQueryHandler ندارند)
    application.add_handler(MessageHandler(filters.Regex("^🧾 تأیید کاربران$") & filters.User(ADMIN_ID), list_pending))
    application.add_handler(CallbackQueryHandler(approve_user, pattern="^approve_"))


    # افزودن ConversationHandlers
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
    application.add_handler(send_account_conv_handler) # **اضافه کردن Handler جدید**


    # اجرای ربات (polling)
    print("Bot started...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
