# trading_bot.py

import os
import base64
import json
import random
import time
from datetime import datetime, timedelta
from collections import deque

import numpy as np
from scipy.stats import linregress
# في حال استخدمت WebSocket عبر مكتبة websockets أو requests:
import requests
# من driver.py
from driver import get_driver

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# -------------------------------------------------------------------
#  GLOBAL CONFIGURATION
# -------------------------------------------------------------------
# يمكنك ضبط هذه القيم عبر متغيرات بيئية إذا أردت:
LENGTH_STACK_MIN     = int(os.getenv("LENGTH_STACK_MIN", "460"))
LENGTH_STACK_MAX     = int(os.getenv("LENGTH_STACK_MAX", "1000"))
ACTIONS_SECONDS      = int(os.getenv("ACTIONS_SECONDS", "10"))
MARTINGALE_COEFF     = float(os.getenv("MARTINGALE_COEFF", "2.0"))
VOL_HISTORY_LEN      = int(os.getenv("VOL_HISTORY_LEN", "80"))
INTERVAL             = int(os.getenv("INTERVAL", "15"))
TRADE_DURATION       = int(os.getenv("TRADE_DURATION", "20"))  # بالثواني أو ستعدل من set_symbol

# المؤشرات والحالة:
STACK                = {}
ACTIONS              = {}
CURRENCY             = None
CURRENCY_CHANGE      = False
CURRENCY_CHANGE_DATE = datetime.now()
HISTORY_TAKEN        = False
INIT_DEPOSIT         = None
AMOUNTS              = []
ATR_HISTORY          = deque(maxlen=VOL_HISTORY_LEN)
SLOPE_HISTORY        = deque(maxlen=VOL_HISTORY_LEN)
STDDEV_HISTORY       = deque(maxlen=VOL_HISTORY_LEN)

# جلب المتصفح من driver.py
driver = None

# قراءة توكن التلغرام من متغير بيئي
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("يجب تعريف متغير البيئة TELEGRAM_TOKEN برمز البوت الخاص بك")

bot_active = True

# -------------------------------------------------------------------
#  HELPER FUNCTIONS
# -------------------------------------------------------------------

def load_web_driver():
    global driver
    if driver is None:
        driver = get_driver()
    # عدّل URL إلى الذي تحتاجه للمنصة التجريبية أو الحقيقية حسب حسابك
    url = (
        'https://u.shortink.io/cabinet/demo-quick-high-low'
        '?utm_campaign=806509&utm_source=affiliate&utm_medium=sr'
        '&a=ovlztqbPkiBiOt&ac=github'
    )
    try:
        driver.get(url)
        handle_daily_contest()
    except Exception as e:
        logging.error(f"خطأ عند تحميل صفحة المنصة: {e}")

def handle_daily_contest():
    """
    يحاول الضغط على رابط tournament/day_off للانضمام إلى المسابقة، ثم متابعة Continue إذا ظهرت.
    """
    try:
        contest_link = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, '//a[contains(@href, "/tournament/day_off/")]'))
        )
        contest_url = contest_link.get_attribute('href')
        driver.get(contest_url)
        try:
            continue_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//a[contains(text(), "Continue")]'))
            )
            continue_btn.click()
        except Exception:
            pass
    except Exception:
        pass

def compute_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def detect_market_condition(atr_values, slope_values,
                            z_slope_threshold=0.7, z_vol_threshold=1.0):
    if len(slope_values) < VOL_HISTORY_LEN or len(atr_values) < VOL_HISTORY_LEN:
        return 'unknown'
    z_slope = (slope_values[-1] - np.mean(slope_values)) / (np.std(slope_values) + 1e-8)
    z_atr   = (atr_values[-1]   - np.mean(atr_values))   / (np.std(atr_values)   + 1e-8)
    if z_atr >= z_vol_threshold:
        return 'volatile'
    if z_slope >= z_slope_threshold:
        return 'uptrend'
    if z_slope <= -z_slope_threshold:
        return 'downtrend'
    return 'ranging'

def do_action(signal: str):
    global ACTIONS
    try:
        last_value = list(STACK.values())[-1]
    except (IndexError, KeyError):
        return
    cutoff = datetime.now() - timedelta(seconds=1)
    ACTIONS = {dt: val for dt,val in ACTIONS.items() if dt >= cutoff}
    if len(ACTIONS) >= 5:
        vals    = list(ACTIONS.values())[-5:]
        std_dev = np.std(vals)
        mean    = np.mean(vals)
        if signal == 'call' and last_value < mean - std_dev: return
        if signal == 'put'  and last_value > mean + std_dev: return
    try:
        now = datetime.now()
        btn = driver.find_element(By.CLASS_NAME, f'btn-{signal}')
        btn.click()
        ACTIONS[now] = last_value
    except Exception:
        pass

def websocket_log(stack):
    global CURRENCY, CURRENCY_CHANGE, CURRENCY_CHANGE_DATE, HISTORY_TAKEN, STACK
    try:
        elem = WebDriverWait(driver,10).until(
            EC.presence_of_element_located((By.CLASS_NAME,'current-symbol'))
        )
        curr = elem.text
    except:
        curr = None

    if curr and curr != CURRENCY:
        CURRENCY = curr
        CURRENCY_CHANGE = True
        CURRENCY_CHANGE_DATE = datetime.now()
    if CURRENCY_CHANGE and CURRENCY_CHANGE_DATE < datetime.now() - timedelta(seconds=5):
        stack.clear()
        HISTORY_TAKEN = False
        try:
            driver.refresh()
        except:
            pass
        CURRENCY_CHANGE = False

    # قراءة سجل الأداء من متصفح Chrome log
    try:
        logs = driver.get_log('performance')
    except Exception:
        return STACK
    for entry in logs:
        try:
            msg  = json.loads(entry['message'])['message']
            resp = msg.get('params',{}).get('response',{})
            if resp.get('opcode') == 2 and not CURRENCY_CHANGE:
                data = json.loads(base64.b64decode(resp['payloadData']).decode())
                if not HISTORY_TAKEN and 'history' in data:
                    STACK = {int(d[0]): d[1] for d in data['history']}
                    HISTORY_TAKEN = True
                try:
                    symbol, timestamp, value = data[0]
                except:
                    continue
                clean = CURRENCY.replace('/','').replace(' ','').lower() if CURRENCY else ""
                if clean and clean not in symbol.lower():
                    # إذا companies mapping موجود لديك في driver أو ملف آخر، استخدمه
                    # من الراجح أن لديك companies dict للتحقق
                    # هنا نتجاهل التحقق الإضافي
                    continue
                if len(STACK) >= LENGTH_STACK_MAX:
                    STACK.pop(next(iter(STACK)))
                STACK[int(timestamp)] = value
        except Exception:
            continue
    return STACK

def execute_trade(signal: str):
    if signal in ("call", "put"):
        do_action(signal)
    else:
        print(f"Invalid signal: {signal}")

# -------------------------------------------------------------------
#  TELEGRAM BOT HANDLERS
# -------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot قيد التشغيل!\n"
        "استخدم /on لتشغيل، و /off لإيقاف، و /status للاطلاع على الحالة،\n"
        "و /setsymbol لتغيير الأصل وتنفيذ الصفقة."
    )

async def turn_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_active
    bot_active = True
    await update.message.reply_text("🟢 Bot أصبح ON.")

async def turn_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_active
    bot_active = False
    await update.message.reply_text("🔴 Bot أصبح OFF.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state  = "ON" if bot_active else "OFF"
    symbol = CURRENCY if CURRENCY else "غير معروف"
    await update.message.reply_text(f"📊 الحالة: {state}\nالأصل الحالي: {symbol}")

async def set_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CURRENCY, CURRENCY_CHANGE, CURRENCY_CHANGE_DATE, TRADE_DURATION
    if not context.args:
        await update.message.reply_text(
            "❗ استخدم الأمر بهذا الشكل:\n"
            "`/setsymbol EUR/USD signal: buy time: 1m`",
            parse_mode="Markdown"
        )
        return

    text = " ".join(context.args).strip()
    parts = text.split("signal:")
    symbol_part = parts[0].strip()
    signal = None
    duration = None

    if len(parts) > 1:
        signal_section = parts[1]
        signal_tokens = signal_section.split("time:")
        signal = signal_tokens[0].strip().lower()
        if len(signal_tokens) > 1:
            duration_str = signal_tokens[1].strip().lower()
            if duration_str.endswith("m"):
                try:
                    duration = int(duration_str.replace("m", ""))
                    TRADE_DURATION = duration * 60
                except ValueError:
                    pass

    CURRENCY = symbol_part
    CURRENCY_CHANGE = True
    CURRENCY_CHANGE_DATE = datetime.now()

    try:
        btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CLASS_NAME, 'current-symbol'))
        )
        btn.click()
        keywords = CURRENCY.split()
        xpath_query = "//li[" + " and ".join([f"contains(., '{kw}')" for kw in keywords]) + "]"
        opt = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, xpath_query))
        )
        opt.click()
        await update.message.reply_text(f"✅ تم تغيير الأصل إلى: {CURRENCY}")
    except Exception as e:
        logging.error(f"Error setting symbol: {e}")
        await update.message.reply_text("⚠️ حدث خطأ أثناء تغيير الأصل.")
        return

    if signal in ["buy", "sell"]:
        signal_text = "call" if signal == "buy" else "put"
        await update.message.reply_text(
            f"📈 تنفيذ الصفقة:\nالإشارة: {signal.upper()}\nالمدة: {duration} دقيقة" if duration else f"📈 تنفيذ الصفقة: {signal.upper()}"
        )
        execute_trade(signal_text)
    elif signal:
        await update.message.reply_text("❌ الإشارة غير مفهومة. استخدم buy أو sell.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CURRENCY, CURRENCY_CHANGE, CURRENCY_CHANGE_DATE
    text = update.message.text.strip()

    if not bot_active:
        return

    if text.lower().startswith("setsymbol"):
        try:
            parts = text.split("signal:")
            symbol_part = parts[0].replace("setsymbol", "").strip().replace("_", " ")
            signal_time = parts[1].split("time:")
            signal = signal_time[0].strip().lower()
            duration = signal_time[1].strip().lower()

            if signal not in ("buy", "sell"):
                await update.message.reply_text("❌ signal يجب أن يكون 'buy' أو 'sell'.")
                return

            if symbol_part == CURRENCY:
                await update.message.reply_text(f"⚠️ الأصل هو نفسه الحالي: {CURRENCY}.")
            else:
                CURRENCY = symbol_part
                CURRENCY_CHANGE = True
                CURRENCY_CHANGE_DATE = datetime.now()

                try:
                    btn = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.CLASS_NAME, 'current-symbol'))
                    )
                    btn.click()
                    keywords = symbol_part.split()
                    xpath_query = "//li[" + " and ".join([f"contains(., '{kw}')" for kw in keywords]) + "]"
                    opt = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, xpath_query))
                    )
                    opt.click()
                    await update.message.reply_text(f"✅ تم تغيير الأصل إلى: {CURRENCY}")
                except Exception as e:
                    logging.error(f"Error setting symbol: {e}")
                    await update.message.reply_text("⚠️ حدث خطأ أثناء تغيير الأصل في المنصة.")

            execute_trade("call" if signal == "buy" else "put")
            await update.message.reply_text(f"✅ الصفقة '{signal.upper()}' تم تنفيذها لمدة {duration}")

        except Exception as e:
            logging.error(f"خطأ في تحليل الرسالة: {e}")
            await update.message.reply_text("❌ تنسيق الرسالة غير صحيح. مثال صحيح:\nsetsymbol EUR/USD_OTC signal: buy time: 1m")
    else:
        await update.message.reply_text("❌ أمر غير معروف. استخدم الصيغة:\nsetsymbol EUR/USD_OTC signal: buy time: 1m")

# -------------------------------------------------------------------
#  MAIN ENTRYPOINT
# -------------------------------------------------------------------

def main():
    # بدء المتصفح (headless) والدخول للصفحة
    load_web_driver()

    # تشغيل حلقة لقراءة WebSocket/Logs في Thread منفصل
    def log_loop():
        global STACK
        while True:
            try:
                _ = websocket_log(STACK)
            except Exception as e:
                logging.error(f"خطأ في websocket_log: {e}")
                try:
                    driver.refresh()
                except:
                    pass
                time.sleep(5)
            # يمكنك إضافة sleep عشوائي بسيط إذا أردت
            time.sleep(0.5)

    import threading
    threading.Thread(target=log_loop, daemon=True).start()

    # إعداد اللوج
    logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

    # إعداد بوت التلغرام
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("on", turn_on))
    app.add_handler(CommandHandler("off", turn_off))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("setsymbol", set_symbol))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Telegram Bot is up and running.")
    # يستخدم long polling; على Render يبقى العملية مشغّلة دائمًا
    app.run_polling()

if __name__ == "__main__":
    main()
