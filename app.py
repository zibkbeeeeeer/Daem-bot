import os
import json
import requests
import math
import time
from flask import Flask, request
from datetime import datetime, timedelta
from threading import Thread, Lock

app = Flask(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN')
GOOGLE_URL = os.environ.get('GOOGLE_SCRIPT_URL')
VERIFICATION_GROUP = os.environ.get('VERIFICATION_GROUP_ID')
ADMIN_ID = os.environ.get('ADMIN_CHAT_ID')

pending_albums = {}
album_timers = {}  # نخلي كل ألبوم يمدد التايمر
global_lock = Lock()  # Lock واحد لكل حاجة

def cleanup_old_albums():
    while True:
        time.sleep(300)
        now = datetime.now()
        with global_lock:
            to_delete = []
            for album_id, album in list(pending_albums.items()):
                if now - album.get("created_at", now) > timedelta(minutes=10):
                    to_delete.append(album_id)
            
            for album_id in to_delete:
                del pending_albums[album_id]
                if album_id in album_timers:
                    album_timers[album_id].cancel()
                    del album_timers[album_id]
                print(f"🧹 Cleaned up: {album_id}")

Thread(target=cleanup_old_albums, daemon=True).start()

def send_message(chat_id, text, reply_to=None, reply_markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error: {e}")

def send_photo(chat_id, photo, caption, reply_markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    payload = {
        "chat_id": chat_id,
        "photo": photo,
        "caption": caption,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error: {e}")

def send_media_group(chat_id, photos, caption, reply_to=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMediaGroup"
    
    media = []
    for i, photo in enumerate(photos):
        item = {
            "type": "photo",
            "media": photo
        }
        if i == 0:
            item["caption"] = caption
            item["parse_mode"] = "HTML"
        media.append(item)
    
    payload = {
        "chat_id": chat_id,
        "media": json.dumps(media)
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"✅ Media group: {len(photos)} photos, status: {response.status_code}")
        return response.json()
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def parse_caption(text):
    if not text:
        return None, None, "مفيش كابشن"
    
    lines = text.strip().split('\n')
    name = ""
    username = ""
    
    for line in lines:
        line = line.strip()
        if line.startswith('@'):
            username = line
        elif line and not name and line != '#كومنت':
            name = line
    
    if not name or not username:
        return None, None, "❌ اكتب:\n\nعزام\n@username\n#كومنت"
    
    return name, username, None

def calculate_money(total_comments):
    hundreds = total_comments // 100
    return hundreds * 5

def process_album_final(media_group_id):
    """تتنفذ بعد ما نتأكد إن مفيش صور جديدة"""
    with global_lock:
        if media_group_id not in pending_albums:
            print(f"⚠️ Album {media_group_id} gone")
            return
        
        album = pending_albums[media_group_id]
        photos = album["photos"]
        caption = album["caption"]
        from_chat = album["from_chat"]
        original_message_id = album["message_id"]
        
        count = len(photos)
        print(f"🔄 FINAL Processing {media_group_id}: {count} photos")
        
        # نمسح من الذاكرة
        del pending_albums[media_group_id]
        if media_group_id in album_timers:
            del album_timers[media_group_id]
    
    # بره الـ Lock عشان ما نبقاش نمسك الدنيا
    clean_caption = caption.replace('#كومنت', '').strip()
    name, username, error = parse_caption(clean_caption)
    
    if error:
        send_message(from_chat, error, reply_to=original_message_id)
        return
    
    current_date = datetime.now().strftime("%Y-%m-%d")
    money = calculate_money(count)
    
    caption_verification = (
        f"📝 <b>{count} كومنتات جديدة</b>\n\n"
        f"👤 <b>الاسم:</b> {name}\n"
        f"🔹 <b>اليوزر:</b> {username}\n"
        f"📅 <b>التاريخ:</b> {current_date}\n"
        f"📊 <b>العدد:</b> {count} كومنت\n"
        f"💰 <b>المستحق:</b> {money} ريال\n\n"
        f"⚠️ كل 100 كومنت = 5 ريال"
    )
    
    result = send_media_group(VERIFICATION_GROUP, photos, caption_verification)
    
    if not result or not result.get('ok'):
        print(f"❌ Media group failed, sending individually")
        for i, photo in enumerate(photos):
            cap = caption_verification if i == 0 else None
            send_photo(VERIFICATION_GROUP, photo, cap)
    
    keyboard = {
        "inline_keyboard": [[
            {"text": f"✅ تأكيد ({count})", "callback_data": f"verify_multi|{from_chat}|{name}|{username}|{count}|{current_date}|{original_message_id}"},
            {"text": "❌ رفض", "callback_data": f"reject|{from_chat}|{original_message_id}"}
        ]]
    }
    
    send_message(VERIFICATION_GROUP, 
        f"☝️ {count} كومنتات | 👤 {name} | 🔹 {username}", 
        reply_markup=keyboard)
    
    send_message(from_chat, 
        f"⏳ تم إرسال {count} كومنتات!\n\n"
        f"👤 {name} | {username}\n"
        f"📊 {count} كومنت\n"
        f"💰 {money} ريال",
        reply_to=original_message_id)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    
    if 'message' not in data:
        if 'callback_query' in data:
            handle_callback(data['callback_query'])
        return 'OK'
    
    msg = data['message']
    chat_id = msg['chat']['id']
    message_id = msg['message_id']
    
    if msg['chat']['type'] == 'private':
        return 'OK'
    
    # ========== ألبوم صور ==========
    if 'media_group_id' in msg and 'photo' in msg:
        caption = msg.get('caption', '')
        
        if '#كومنت' not in caption:
            return 'OK'
        
        media_group_id = msg['media_group_id']
        photo = msg['photo'][-1]['file_id']
        
        with global_lock:
            # لو ألبوم جديد
            if media_group_id not in pending_albums:
                print(f"🆕 NEW Album: {media_group_id}")
                pending_albums[media_group_id] = {
                    "photos": [],
                    "caption": caption,
                    "from_chat": chat_id,
                    "message_id": message_id,
                    "created_at": datetime.now()
                }
            
            # نضيف الصورة
            pending_albums[media_group_id]["photos"].append(photo)
            current_count = len(pending_albums[media_group_id]["photos"])
            print(f"📸 Album {media_group_id}: {current_count} photos")
            
            # نلغي التايمر القديم لو موجود
            if media_group_id in album_timers:
                album_timers[media_group_id].cancel()
                print(f"⏹️ Cancelled old timer for {media_group_id}")
            
            # نعمل تايمر جديد 10 ثواني من دلوقتي
            def start_timer():
                time.sleep(10)
                process_album_final(media_group_id)
            
            t = Thread(target=start_timer)
            album_timers[media_group_id] = t
            t.start()
            print(f"⏱️ Started NEW 10s timer for {media_group_id}")
        
        return 'OK'
    
    # ========== صورة واحدة ==========
    elif 'photo' in msg and '#كومنت' in (msg.get('caption', '')):
        photo = msg['photo'][-1]['file_id']
        caption = msg.get('caption', '')
        
        clean_caption = caption.replace('#كومنت', '').strip()
        name, username, error = parse_caption(clean_caption)
        if error:
            send_message(chat_id, error, reply_to=message_id)
            return 'OK'
        
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        caption_verification = (
            f"📝 <b>كومنت جديد</b>\n\n"
            f"👤 <b>الاسم:</b> {name}\n"
            f"🔹 <b>اليوزر:</b> {username}\n"
            f"📅 <b>التاريخ:</b> {current_date}\n"
            f"📊 1 كومنت"
        )
        
        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ تأكيد", "callback_data": f"verify|{chat_id}|{name}|{username}|{current_date}|1|{message_id}"},
                {"text": "❌ رفض", "callback_data": f"reject|{chat_id}|{message_id}"}
            ]]
        }
        
        send_photo(VERIFICATION_GROUP, photo, caption_verification, reply_markup=keyboard)
        send_message(chat_id, "⏳ تم إرسال الكومنت!", reply_to=message_id)
        return 'OK'
    
    return 'OK'

def handle_callback(query):
    data = query['data']
    message = query['message']
    chat_id = message['chat']['id']
    verifier_name = query['from'].get('first_name', 'Unknown')
    
    if data.startswith('verify_multi'):
        parts = data.split('|')
        user_chat_id = parts[1]
        name = parts[2]
        username = parts[3]
        count = int(parts[4])
        date = parts[5]
        original_message_id = parts[6] if len(parts) > 6 else None
        
        money = calculate_money(count)
        
        for i in range(count):
            try:
                requests.post(GOOGLE_URL, json={
                    'action': 'add_comment',
                    'name': name,
                    'username': username,
                    'date': date,
                    'count': 1,
                    'status': '✅ تم التأكيد',
                    'verifiedBy': verifier_name,
                    'amount': 0
                }, timeout=10)
            except Exception as e:
                print(f"❌ Error: {e}")
        
        send_message(user_chat_id, 
            f"🎉 تم تأكيد {count} كومنتات!\n💰 {money} ريال",
            reply_to=original_message_id)
        
    elif data.startswith('verify'):
        parts = data.split('|')
        user_chat_id = parts[1]
        name = parts[2]
        username = parts[3]
        date = parts[4]
        original_message_id = parts[6] if len(parts) > 6 else None
        
        try:
            requests.post(GOOGLE_URL, json={
                'action': 'add_comment',
                'name': name,
                'username': username,
                'date': date,
                'count': 1,
                'status': '✅ تم التأكيد',
                'verifiedBy': verifier_name,
                'amount': 0
            }, timeout=10)
        except Exception as e:
            print(f"❌ Error: {e}")
        
        send_message(user_chat_id, "🎉 تم تأكيد الكومنت!", reply_to=original_message_id)
        
    elif data.startswith('reject'):
        parts = data.split('|')
        user_chat_id = parts[1]
        original_message_id = parts[2] if len(parts) > 2 else None
        
        send_message(user_chat_id, "❌ تم رفض.", reply_to=original_message_id)

@app.route('/')
def home():
    return "Bot Running!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
