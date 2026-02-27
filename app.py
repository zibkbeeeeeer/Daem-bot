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
album_locks = {}  # Lock لكل ألبوم عشان نتجنب race condition

def cleanup_old_albums():
    """نظف الألبومات القديمة (أكتر من 10 دقايق)"""
    while True:
        time.sleep(300)
        now = datetime.now()
        to_delete = []
        
        for album_id, album in list(pending_albums.items()):
            if now - album.get("created_at", now) > timedelta(minutes=10):
                to_delete.append(album_id)
        
        for album_id in to_delete:
            if album_id in pending_albums:
                del pending_albums[album_id]
            if album_id in album_locks:
                del album_locks[album_id]
            print(f"🧹 Cleaned up old album: {album_id}")

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
        print(f"Error sending photo: {e}")

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
        print(f"❌ Error media group: {e}")
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
        return None, None, "❌ اكتب بالشكل ده:\n\nعزام\n@username\n#كومنت"
    
    return name, username, None

def calculate_money(total_comments):
    hundreds = total_comments // 100
    return hundreds * 5

def process_album_after_delay(media_group_id, delay=8):
    """تتنفذ بعد delay ثواني من آخر صورة"""
    time.sleep(delay)
    
    if media_group_id not in pending_albums:
        print(f"⚠️ Album {media_group_id} not found after {delay}s wait")
        return
    
    album = pending_albums[media_group_id]
    photos = album["photos"]
    caption = album["caption"]
    from_chat = album["from_chat"]
    original_message_id = album["message_id"]
    
    count = len(photos)
    print(f"🔄 Processing {media_group_id}: {count} photos collected after {delay}s wait")
    
    # نمسح الألبوم من الذاكرة
    del pending_albums[media_group_id]
    if media_group_id in album_locks:
        del album_locks[media_group_id]
    
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
    
    # بعت الألبوم كامل
    result = send_media_group(VERIFICATION_GROUP, photos, caption_verification)
    
    if not result or not result.get('ok'):
        print(f"❌ Failed to send media group, trying individual photos")
        # لو فشل، بعت الصور واحدة واحدة
        for i, photo in enumerate(photos):
            cap = caption_verification if i == 0 else None
            send_photo(VERIFICATION_GROUP, photo, cap)
    
    # keyboard
    keyboard = {
        "inline_keyboard": [[
            {"text": f"✅ تأكيد ({count})", "callback_data": f"verify_multi|{from_chat}|{name}|{username}|{count}|{current_date}|{original_message_id}"},
            {"text": "❌ رفض", "callback_data": f"reject|{from_chat}|{original_message_id}"}
        ]]
    }
    
    send_message(VERIFICATION_GROUP, 
        f"☝️ {count} كومنتات | 👤 {name} | 🔹 {username}", 
        reply_markup=keyboard)
    
    # Reply للشخص
    send_message(from_chat, 
        f"⏳ تم إرسال {count} كومنتات للتأكيد!\n\n"
        f"👤 {name} | {username}\n"
        f"📊 {count} كومنت\n"
        f"💰 {money} ريال (كل 100 = 5 ريال)",
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
        photo = msg['photo'][-1]['file_id']  # أعلى جودة
        
        # لو ألبوم جديد، نبدأ نجمع
        if media_group_id not in pending_albums:
            print(f"🆕 New album started: {media_group_id}")
            pending_albums[media_group_id] = {
                "photos": [],
                "caption": caption,
                "from_chat": chat_id,
                "message_id": message_id,
                "created_at": datetime.now(),
                "timer_thread": None
            }
            album_locks[media_group_id] = Lock()
            
            # ✅ ابدأ Thread يستنى 8 ثواني من الآن (مش فوراً)
            t = Thread(target=process_album_after_delay, args=(media_group_id, 8))
            pending_albums[media_group_id]["timer_thread"] = t
            t.start()
            print(f"⏱️ Started 8s timer for {media_group_id}")
        
        # نضيف الصورة للألبوم
        with album_locks.get(media_group_id, Lock()):
            if media_group_id in pending_albums:
                pending_albums[media_group_id]["photos"].append(photo)
                current = len(pending_albums[media_group_id]["photos"])
                print(f"📸 Added photo to {media_group_id}: total {current} photos")
        
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
        send_message(chat_id, "⏳ تم إرسال الكومنت للتأكيد!", reply_to=message_id)
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
                print(f"❌ Error saving comment {i+1}: {e}")
        
        print(f"✅ Saved {count} comments for {name}")
        
        send_message(user_chat_id, 
            f"🎉 تم تأكيد {count} كومنتات!\n"
            f"👤 {name} | {username}\n"
            f"💰 {money} ريال (كل 100 = 5 ريال)",
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
        
        send_message(user_chat_id, 
            f"🎉 تم تأكيد الكومنت!\n"
            f"👤 {name} | {username}",
            reply_to=original_message_id)
        
    elif data.startswith('reject'):
        parts = data.split('|')
        user_chat_id = parts[1]
        original_message_id = parts[2] if len(parts) > 2 else None
        
        send_message(user_chat_id, "❌ تم رفض الكومنتات.", reply_to=original_message_id)

@app.route('/')
def home():
    return "Daem Bot is running! 💰"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
