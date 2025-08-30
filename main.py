import json
import os
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, ContextTypes
from telegram.ext import filters

# حالات المحادثة
CHANNEL, NUMBER, TYPE, NAME, OPTIONS, DATE = range(6)

# تحميل البيانات من ملف JSON
def load_data():
    if os.path.exists('trading_data.json'):
        with open('trading_data.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"free": [], "vip": []}

# حفظ البيانات إلى ملف JSON
def save_data(data):
    with open('trading_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# بدء البوت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    welcome_message = (
        "مرحباً بك في بوت إدارة الصفقات! 🎯\n\n"
        "🎯 أوامر البوت المتاحة:\n\n"
        "/start - بدء المحادثة\n"
        "/add - إضافة عملية جديدة\n"
        "/report - عرض تقرير بالأرباح والخسائر\n"
        "/clear - مسح جميع البيانات\n"
        "/help - عرض الرسالة المساعدة\n\n"
        "📝 طريقة الاستخدام:\n"
        "1. استخدم /add لإضافة عملية جديدة\n"
        "2. اختر القناة (VIP، مجانية، أو كلاهما)\n"
        "3. اتبع الخطوات لإدخال التفاصيل\n"
        "4. استخدم /report لعرض التقرير\n"
    )
    await update.message.reply_text(welcome_message)

# مساعدة
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "🎯 أوامر البوت المتاحة:\n\n"
        "/start - بدء المحادثة\n"
        "/add - إضافة عملية جديدة\n"
        "/report - عرض تقرير بالأرباح والخسائر\n"
        "/clear - مسح جميع البيانات\n"
        "/help - عرض هذه الرسالة\n\n"
        "📝 طريقة الاستخدام:\n"
        "1. استخدم /add لإضافة عملية جديدة\n"
        "2. اختر القناة (VIP، مجانية، أو كلاهما)\n"
        "3. اتبع الخطوات لإدخال التفاصيل\n"
        "4. استخدم /report لعرض التقرير\n"
    )
    await update.message.reply_text(help_text)

# بدء إضافة عملية جديدة
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_keyboard = [['مجانية', 'VIP', 'كلاهما']]
    await update.message.reply_text(
        'أهلاً بك في إضافة عملية جديدة!\n\n'
        'اختر نوع القناة:',
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, input_field_placeholder='اختر القناة'
        ),
    )
    return CHANNEL

# معالجة اختيار القناة
async def channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['channel'] = update.message.text
    await update.message.reply_text(
        'تم اختيار القناة: ' + update.message.text + '\n\n'
        'الآن أدخل رقم الصفقة:',
        reply_markup=ReplyKeyboardRemove(),
    )
    return NUMBER

# معالجة رقم الصفقة
async def number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['number'] = update.message.text
    reply_keyboard = [['ربح', 'خساره'], ['profit', 'loss']]
    await update.message.reply_text(
        'تم حفظ رقم الصفقة.\n\n'
        'الآن اختر نوع الصفقة (ربح/خساره):',
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, input_field_placeholder='نوع الصفقة'
        ),
    )
    return TYPE

# معالجة نوع الصفقة
async def type_(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    trade_type = update.message.text
    # توحيد كتابة النوع
    if trade_type in ['ربح', 'profit']:
        context.user_data['type'] = 'ربح'
    else:
        context.user_data['type'] = 'خساره'
    
    await update.message.reply_text(
        'تم تحديد نوع الصفقة: ' + context.user_data['type'] + '\n\n'
        'الآن أدخل اسم العملة:',
        reply_markup=ReplyKeyboardRemove(),
    )
    return NAME

# معالجة اسم العملة
async def name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['name'] = update.message.text.upper()
    await update.message.reply_text(
        'تم حفظ اسم العملة: ' + context.user_data['name'] + '\n\n'
        'الآن أدخل المبلغ (استخدم + للربح و - للخسارة):'
    )
    return OPTIONS

# معالجة المبلغ
async def options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    options_text = update.message.text
    # التأكد من أن المبلغ يتطابق مع نوع الصفقة
    if context.user_data['type'] == 'ربح' and not options_text.startswith('+'):
        if options_text.startswith('-'):
            options_text = options_text[1:]
        options_text = '+' + options_text
    elif context.user_data['type'] == 'خساره' and not options_text.startswith('-'):
        if options_text.startswith('+'):
            options_text = options_text[1:]
        options_text = '-' + options_text
    
    context.user_data['options'] = options_text
    await update.message.reply_text(
        'تم حفظ المبلغ: ' + context.user_data['options'] + '\n\n'
        'الآن أدخل التاريخ (مثال: 15 - ابريل أو 15-4):'
    )
    return DATE

# معالجة التاريخ وتخزين البيانات
async def date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['date'] = update.message.text
    
    # تحميل البيانات الحالية
    data = load_data()
    
    # إنشاء كائن الصفقة
    trade = {
        'number': context.user_data['number'],
        'type': context.user_data['type'],
        'name': context.user_data['name'],
        'options': context.user_data['options'],
        'date': context.user_data['date']
    }
    
    # إضافة الصفقة إلى القنوات المحددة
    channel_type = context.user_data['channel']
    if channel_type == 'مجانية' or channel_type == 'كلاهما':
        data['free'].append(trade)
    if channel_type == 'VIP' or channel_type == 'كلاهما':
        data['vip'].append(trade)
    
    # حفظ البيانات
    save_data(data)
    
    await update.message.reply_text(
        'تم حفظ الصفقة بنجاح! ✅\n\n'
        'يمكنك إضافة صفقة جديدة باستخدام /add أو عرض التقرير باستخدام /report'
    )
    return ConversationHandler.END

# إلغاء المحادثة
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        'تم إلغاء العملية.', 
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

# عرض التقرير
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = load_data()
    
    if not data['free'] and not data['vip']:
        await update.message.reply_text('لا توجد صفقات مسجلة بعد.')
        return
    
    report_text = "📊 تقرير الصفقات 📊\n\n"
    
    # تحليل الصفقات المجانية
    if data['free']:
        report_text += "🟢 الصفقات المجانية:\n"
        report_text += generate_channel_report(data['free'])
    
    # تحليل الصفقات VIP
    if data['vip']:
        report_text += "\n🔵 الصفقات VIP:\n"
        report_text += generate_channel_report(data['vip'])
    
    # تقرير إجمالي
    report_text += "\n📈 التقرير الإجمالي:\n"
    
    all_trades = data['free'] + data['vip']
    total_profit = 0
    total_loss = 0
    
    for trade in all_trades:
        amount = int(trade['options'])
        if amount > 0:
            total_profit += amount
        else:
            total_loss += abs(amount)
    
    net = total_profit - total_loss
    
    report_text += f"إجمالي الأرباح: +{total_profit}\n"
    report_text += f"إجمالي الخسائر: -{total_loss}\n"
    report_text += f"صافي الربح/الخسارة: {('+' if net >= 0 else '')}{net}\n\n"
    
    # تحليل حسب العملة
    report_text += "💱 تحليل حسب العملة:\n"
    currency_stats = {}
    
    for trade in all_trades:
        currency = trade['name']
        amount = int(trade['options'])
        
        if currency not in currency_stats:
            currency_stats[currency] = {'profit': 0, 'loss': 0}
        
        if amount > 0:
            currency_stats[currency]['profit'] += amount
        else:
            currency_stats[currency]['loss'] += abs(amount)
    
    for currency, stats in currency_stats.items():
        net = stats['profit'] - stats['loss']
        report_text += f"{currency}: {('+' if net >= 0 else '')}{net} (ربح: +{stats['profit']}, خسارة: -{stats['loss']})\n"
    
    await update.message.reply_text(report_text)

# إنشاء تقرير للقناة
def generate_channel_report(trades):
    report = ""
    for trade in trades:
        report += f"#{trade['number']} {trade['name']} {trade['options']} ({trade['date']}) - {trade['type']}\n"
    return report + "\n"

# مسح جميع البيانات
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    empty_data = {"free": [], "vip": []}
    save_data(empty_data)
    await update.message.reply_text('تم مسح جميع البيانات بنجاح.')

# الدالة الرئيسية
def main() -> None:
    # استبدل 'TOKEN' بتوكن البوت الخاص بك
    application = Application.builder().token("8417227493:AAFvJ0sL4AkeRfjLMf0wn4Dj6L4e8Kz2N8Y").build()

    # معالج المحادثة لإضافة الصفقات
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('add', add)],
        states={
            CHANNEL: [MessageHandler(filters.Regex('^(مجانية|VIP|كلاهما)$'), channel)],
            NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, number)],
            TYPE: [MessageHandler(filters.Regex('^(ربح|خساره|profit|loss)$'), type_)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
            OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, options)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, date)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("report", report))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(conv_handler)

    # بدء البوت
    application.run_polling()

if __name__ == '__main__':
    main()