import os
import json
import requests
import math
import time
import traceback
from flask import Flask, request
from datetime import datetime

app = Flask(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN')
GOOGLE_URL = os.environ.get('GOOGLE_SCRIPT_URL')
VERIFICATION_GROUP = os.environ.get('VERIFICATION_GROUP_ID')

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def send_photo_simple(chat_id, photo, caption):
    """نبعت صورة من غير كيبورد عشان نتأكد إن المشكلة في الكيبورد"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    payload = {
        "chat_id": chat_id,
        "photo": photo,
        "caption": caption,
        "parse_mode": "HTML"
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        result = r.json()
        if result.get('ok'):
            log(f"✅ Photo sent to {chat_id}")
            return True
        else:
            log(f"❌ Telegram error: {result}")
            return False
    except Exception as e:
        log(f"❌ Exception: {e}")
        return False

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    log(f"Webhook received")
    
    if 'message' not in data:
        log("No message in data")
        return 'OK'
    
    msg = data['message']
    chat_id = msg['chat']['id']
    message_id = msg['message_id']
    
    log(f"From chat: {chat_id}, type: {msg['chat']['type']}")
    
    if msg['chat']['type'] == 'private':
        return 'OK'
    
    # ========== أي صورة (ألبوم أو صورة واحدة) ==========
    if 'photo' in msg:
        caption = msg.get('caption', '')
        log(f"Photo received. Caption: {caption[:30]}...")
        
        if '#كومنت' not in caption:
            log("No #كومنت, ignoring")
            return 'OK'
        
        # نجيب أعلى جودة
        photos = msg['photo']
        best_photo = photos[-1]['file_id']
        log(f"Photo file_id: {best_photo[:20]}...")
        
        # نParse الكابشن
        clean = caption.replace('#كومنت', '').strip()
        lines = clean.split('\n')
        name = ""
        username = ""
        for line in lines:
            line = line.strip()
            if line.startswith('@'):
                username = line
            elif line and not name:
                name = line
        
        if not name or not username:
            log(f"Parse failed: name={name}, user={username}")
            return 'OK'
        
        log(f"Parsed: name={name}, user={username}")
        
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # نبعت لجروب التأكيد (أول حاجة: من غير كيبورد عشان نتأكد)
        verify_caption = (
            f"📝 كومنت جديد\n\n"
            f"👤 الاسم: {name}\n"
            f"🔹 اليوزر: {username}\n"
            f"📅 التاريخ: {current_date}\n"
            f"🆔 From: {chat_id}\n"
            f"📨 Msg: {message_id}"
        )
        
        # ✅ نبعت الصورة
        success = send_photo_simple(VERIFICATION_GROUP, best_photo, verify_caption)
        
        if success:
            # نرد على المستخدم
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": f"⏳ تم إرسال الكومنت للتأكيد!\n👤 {name}",
                "reply_to_message_id": message_id
            }
            try:
                requests.post(url, json=payload, timeout=5)
            except:
                pass
        
        return 'OK'
    
    log("Not a photo")
    return 'OK'

@app.route('/')
def home():
    return "Bot OK"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
