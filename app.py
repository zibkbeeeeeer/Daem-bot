import os
import json
import requests
import math
import time
from flask import Flask, request
from datetime import datetime
from threading import Thread, Lock

app = Flask(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN')
GOOGLE_URL = os.environ.get('GOOGLE_SCRIPT_URL')
VERIFICATION_GROUP = os.environ.get('VERIFICATION_GROUP_ID')

# نخزن الكابشن للألبومات
album_captions = {}  # {media_group_id: {"caption": "...", "from_chat": 123, "message_id": 456}}
album_lock = Lock()

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def send_photo_simple(chat_id, photo, caption):
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
            return True
        else:
            log(f"❌ Telegram error: {result}")
            return False
    except Exception as e:
        log(f"❌ Exception: {e}")
        return False

def send_message(chat_id, text, reply_to=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass

def cleanup_albums():
    """نمسح الألبومات القديمة بعد 5 دقايق"""
    while True:
        time.sleep(300)
        with album_lock:
            now = datetime.now()
            to_delete = []
            for mg_id, data in list(album_captions.items()):
                if (now - data.get("time", now)).seconds > 600:
                    to_delete.append(mg_id)
            for mg_id in to_delete:
                del album_captions[mg_id]
                log(f"🧹 Cleaned album: {mg_id}")

# نبدأ التنظيف
Thread(target=cleanup_albums, daemon=True).start()

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    
    if 'message' not in data:
        return 'OK'
    
    msg = data['message']
    chat_id = msg['chat']['id']
    message_id = msg['message_id']
    
    if msg['chat']['type'] == 'private':
        return 'OK'
    
    # ========== صورة (ألبوم أو صورة واحدة) ==========
    if 'photo' in msg:
        caption = msg.get('caption', '') or ''  # لو None نخليها ''
        has_caption = '#كومنت' in caption
        
        media_group_id = msg.get('media_group_id')
        
        with album_lock:
            if media_group_id:
                # ده جزء من ألبوم
                if has_caption:
                    # أول صورة (أو صورة فيها كابشن)
                    log(f"🆕 Album started: {media_group_id}")
                    album_captions[media_group_id] = {
                        "caption": caption,
                        "from_chat": chat_id,
                        "message_id": message_id,
                        "time": datetime.now(),
                        "count": 1
                    }
                    use_caption = caption
                elif media_group_id in album_captions:
                    # صورة تانية في نفس الألبوم
                    album_captions[media_group_id]["count"] += 1
                    use_caption = album_captions[media_group_id]["caption"]
                    log(f"📸 Album {media_group_id}: photo #{album_captions[media_group_id]['count']}")
                else:
                    # صورة من ألبوم بس الكابشن اتمسح أو حاجة غريبة
                    log(f"⚠️ Album {media_group_id} not found, skipping")
                    return 'OK'
            else:
                # صورة واحدة (مش ألبوم)
                if not has_caption:
                    return 'OK'
                use_caption = caption
        
        # نParse الكابشن
        clean = use_caption.replace('#كومنت', '').strip()
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
            log(f"❌ Parse failed: name={name}, user={username}")
            return 'OK'
        
        # نجيب الصورة
        photos = msg['photo']
        best_photo = photos[-1]['file_id']
        
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # نبعت لجروب التأكيد
        verify_caption = (
            f"📝 كومنت جديد\n\n"
            f"👤 الاسم: {name}\n"
            f"🔹 اليوزر: {username}\n"
            f"📅 التاريخ: {current_date}"
        )
        
        if media_group_id:
            verify_caption += f"\n🆔 ألبوم: {str(media_group_id)[-8:]}"
        
        success = send_photo_simple(VERIFICATION_GROUP, best_photo, verify_caption)
        
        if success and has_caption:
            # نرد على المستخدم (بس مرة واحدة لأول صورة)
            send_message(chat_id, 
                f"⏳ تم إرسال الكومنتات للتأكيد!\n"
                f"👤 {name} | {username}",
                reply_to=message_id)
        
        return 'OK'
    
    return 'OK'

@app.route('/')
def home():
    return "Bot OK"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
