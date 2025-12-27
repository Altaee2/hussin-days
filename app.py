import os
import subprocess
import zipfile
import sys
import shutil
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- الإعدادات الأساسية ---
TOKEN = '7830176312:AAHVY_pz-NtNa104ETa5TnYugkN72AnSnZ0'
OWNER_ID = 7769271031

ADMINS = [OWNER_ID]
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deployed_bots")
running_processes = {} # { user_id: { bot_name: process_object } }

if not os.path.exists(BASE_DIR):
    os.makedirs(BASE_DIR)

# --- دوال المساعدة والنظام ---

def get_bots_keyboard(user_id):
    """توليد قائمة الأزرار الخاصة بالمستخدم فقط"""
    user_path = os.path.join(BASE_DIR, str(user_id))
    keyboard = []
    
    if os.path.exists(user_path):
        for bot_name in os.listdir(user_path):
            p_path = os.path.join(user_path, bot_name)
            if os.path.isdir(p_path):
                # فحص الحالة
                is_running = False
                if user_id in running_processes and bot_name in running_processes[user_id]:
                    if running_processes[user_id][bot_name].poll() is None:
                        is_running = True
                    else:
                        del running_processes[user_id][bot_name]

                status = "🟢" if is_running else "🔴"
                keyboard.append([InlineKeyboardButton(f"{status} {bot_name}", callback_data=f"manage_{bot_name}")])
    
    return InlineKeyboardMarkup(keyboard) if keyboard else None

async def auto_start_projects():
    """تشغيل كافة مشاريع كل المشرفين عند إقلاع السيرفر"""
    print("🔄 جاري فحص جميع مجلدات المشرفين للتشغيل التلقائي...")
    for user_folder in os.listdir(BASE_DIR):
        if not user_folder.isdigit(): continue
        
        user_id = int(user_folder)
        user_path = os.path.join(BASE_DIR, user_folder)
        
        for bot_name in os.listdir(user_path):
            project_path = os.path.join(user_path, bot_name)
            if os.path.isdir(project_path):
                target = os.path.join(project_path, "app.py")
                if not os.path.exists(target):
                    py_files = [f for f in os.listdir(project_path) if f.endswith('.py')]
                    if py_files: target = os.path.join(project_path, py_files[0])
                
                if os.path.exists(target):
                    if user_id not in running_processes: running_processes[user_id] = {}
                    proc = subprocess.Popen([sys.executable, target], cwd=project_path)
                    running_processes[user_id][bot_name] = proc
                    print(f"✅ تم إعادة تشغيل: {bot_name} للمشرف {user_id}")

# --- الأوامر والتعامل مع الرسائل ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text("❌ أنت لست مشرفاً. اطلب من المطور إضافتك.")
        return

    markup = get_bots_keyboard(user_id)
    text = (
        "🛡️ **لوحة تحكم المشرف**\n\n"
        "👤 آيديك: `{user_id}`\n"
        "📁 لرفع ملف: أرسل .py أو .zip\n"
        "🗑️ للحذف: `/d اسم_البوت`\n"
        "⚙️ مشاريعك الخاصة تظهر أدناه:"
    ).format(user_id=user_id)
    
    await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة مشرف (للمطور الأساسي فقط)"""
    if update.effective_user.id != OWNER_ID: return
    try:
        new_id = int(context.args[0])
        if new_id not in ADMINS:
            ADMINS.append(new_id)
            await update.message.reply_text(f"✅ تمت إضافة المشرف الجديد: {new_id}")
        else:
            await update.message.reply_text("هذا المستخدم مشرف بالفعل.")
    except:
        await update.message.reply_text("⚠️ أرسل الأمر هكذا: `/add 12345678`", parse_mode="Markdown")

async def delete_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS: return
    
    if not context.args:
        await update.message.reply_text("⚠️ أرسل اسم المشروع بعد الأمر، مثال: `/d Bot123`", parse_mode="Markdown")
        return

    bot_name = context.args[0]
    project_path = os.path.join(BASE_DIR, str(user_id), bot_name)

    if os.path.exists(project_path):
        if user_id in running_processes and bot_name in running_processes[user_id]:
            running_processes[user_id][bot_name].terminate()
            del running_processes[user_id][bot_name]
        
        shutil.rmtree(project_path)
        await update.message.reply_text(f"🗑️ تم حذف المشروع '{bot_name}' بنجاح.")
        await start(update, context)
    else:
        await update.message.reply_text("❌ لم أجد مشروعاً بهذا الاسم في مجلدك.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS: return
    
    doc = update.message.document
    if doc.file_name.endswith(('.py', '.zip')):
        context.user_data['pending_file'] = doc
        context.user_data['state'] = 'WAITING_FOR_NAME'
        await update.message.reply_text("🏷️ أرسل اسماً لمشروعك الجديد:")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.user_data.get('state') == 'WAITING_FOR_NAME':
        project_name = update.message.text.strip().replace(" ", "_")
        project_path = os.path.join(BASE_DIR, str(user_id), project_name)
        
        os.makedirs(project_path, exist_ok=True)
        doc = context.user_data['pending_file']
        file_obj = await doc.get_file()
        
        if doc.file_name.endswith('.zip'):
            zip_p = os.path.join(project_path, "temp.zip")
            await file_obj.download_to_drive(zip_p)
            with zipfile.ZipFile(zip_p, 'r') as z: z.extractall(project_path)
            os.remove(zip_p)
        else:
            await file_obj.download_to_drive(os.path.join(project_path, "app.py"))

        # تثبيت المكاتب
        req_path = os.path.join(project_path, "requirements.txt")
        if os.path.exists(req_path):
            subprocess.Popen([sys.executable, "-m", "pip", "install", "-r", req_path])
        
        context.user_data['state'] = None
        
        # تشغيل تلقائي بعد الرفع
        target = os.path.join(project_path, "app.py")
        if user_id not in running_processes: running_processes[user_id] = {}
        running_processes[user_id][project_name] = subprocess.Popen([sys.executable, target], cwd=project_path)
        
        await update.message.reply_text(f"🚀 تم رفع وتشغيل '{project_name}' بنجاح!")
        await start(update, context)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    bot_name = query.data.replace("manage_", "")
    project_path = os.path.join(BASE_DIR, str(user_id), bot_name)

    if user_id not in running_processes: running_processes[user_id] = {}
    process = running_processes[user_id].get(bot_name)

    if process and process.poll() is None:
        process.terminate()
        del running_processes[user_id][bot_name]
        await query.answer(f"🛑 تم إيقاف {bot_name}")
    else:
        target = os.path.join(project_path, "app.py")
        if not os.path.exists(target):
            py_files = [f for f in os.listdir(project_path) if f.endswith('.py')]
            if py_files: target = os.path.join(project_path, py_files[0])

        if os.path.exists(target):
            proc = subprocess.Popen([sys.executable, target], cwd=project_path)
            running_processes[user_id][bot_name] = proc
            await query.answer(f"▶️ تم تشغيل {bot_name}")
        else:
            await query.answer("❌ تعذر العثور على ملف التشغيل.")

    try:
        await query.edit_message_reply_markup(reply_markup=get_bots_keyboard(user_id))
    except: pass

# --- التشغيل ---
async def post_init(application: Application):
    await auto_start_projects()

if __name__ == '__main__':
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_admin))
    app.add_handler(CommandHandler("d", delete_project))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("✅ البوت المطور يعمل الآن.. نظام الخصوصية والتشغيل التلقائي مُفعل.")
    app.run_polling()
