# driver.py
import os
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options

def get_driver():
    """
    تنشئ متصفح Chrome مخفي (headless) مع بعض الإعدادات لتقليل اكتشاف التشغيل الآلي.
    تتوقع أن Chrome/Chromedriver مثبتان في بيئة التشغيل (خاصة عند استخدام Docker).
    يمكنك ضبط USER_AGENT من متغير بيئي USER_AGENT لإضفاء تنوع.
    """
    # استخدم خيارات undetected-chromedriver
    options = uc.ChromeOptions()
    # headless mode
    options.add_argument("--headless=new")  # بعض الإصدارات تدعم "--headless=new"
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # إخفاء علامة الأتمتة
    options.add_argument("--disable-blink-features=AutomationControlled")
    # يمكنك إضافة User-Agent من متغير بيئي أو ترك المستخدم الافتراضي
    user_agent = os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
    options.add_argument(f"user-agent={user_agent}")
    # تعطيل الإشعارات مثلا
    options.add_argument("--disable-notifications")
    # خيارات إضافية قد تساعد في البيئات السحابية
    options.add_argument("--disable-gpu")
    # يمكنك إضافة فواصل زمنية عشوائية لاحقاً في السكربت نفسه لتجنب نمط ثابت.
    # في بعض البيئات قد تحتاج إلى ضبط المسارات يدوياً، لكن undetected-chromedriver عادة يدير Chromedriver تلقائياً.
    try:
        driver = uc.Chrome(options=options)
    except Exception as e:
        # في حال خطأ، حاول بدون undetected-chromedriver
        from selenium import webdriver
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument(f"user-agent={user_agent}")
        opts.add_argument("--disable-notifications")
        opts.add_argument("--disable-gpu")
        driver = webdriver.Chrome(options=opts)
    return driver
