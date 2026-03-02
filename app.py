import os
import json
import requests
import math
import time
import re
from flask import Flask, request
from datetime import datetime
from threading import Thread, Lock

app = Flask(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN')
GOOGLE_URL = os.environ.get('GOOGLE_SCRIPT_URL')
VERIFICATION_GROUP = os.environ.get('VERIFICATION_GROUP_ID')

album_captions = {}
album_lock = Lock()

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def send_photo_with_keyboard(chat_id, photo, caption, keyboard=None, reply_to=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    payload = {
        "chat_id": chat_id,
        "photo": photo,
        "caption": caption,
        "parse_mode": "HTML"
    }
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    
    try:
        r = requests.post(url, json=payload, timeout=10)
        result = r.json()
        if result.get('ok'):
            return True, result
        else:
            log(f"❌ Telegram error: {result}")
            return False, result
    except Exception as e:
        log(f"❌ Exception: {e}")
        return False, None

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

def get_chat_members(chat_id):
    """نجيب كل الأعضاء في الجروب"""
    url = f"https://api.telegram.org/bot{TOKEN}/getChatAdministrators"
    try:
        r = requests.post(url, json={"chat_id": chat_id}, timeout=10)
        result = r.json()
        if result.get('ok'):
            members = []
            for member in result.get('result', []):
                user = member.get('user', {})
                if not user.get('is_bot'):
                    username = user.get('username')
                    if username:
                        members.append(f"@{username}")
                    else:
                        members.append(f"[{user.get('first_name', 'User')}](tg://user?id={user['id']})")
            return members
    except Exception as e:
        log(f"❌ Error getting members: {e}")
    return []

def mention_all(chat_id):
    """نمنشن كل الناس (بس المنشن، من غير أي نص)"""
    members = get_chat_members(chat_id)
    if not members:
        send_message(chat_id, "❌ مقدرش أجيب الأعضاء. لازم أكون Admin.")
        return
    
    batch_size = 5
    for i in range(0, len(members), batch_size):
        batch = members[i:i+batch_size]
        mention_text = " ".join(batch)
        send_message(chat_id, mention_text)
        time.sleep(0.5)

def parse_caption_multi(caption):
    """نParse الكابشن ونجيب الاسم واليوزرات"""
    clean = caption.replace('#كومنت', '').strip()
    lines = clean.split('\n')
    
    name = ""
    users = []
    
    for line in lines:
        line = line.strip()
        if line.startswith('@'):
            users.append(line)
        elif line and not name:
            name = line
    
    return name, users

def cleanup_albums():
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
                log(f"🧹 Cleaned: {mg_id}")

Thread(target=cleanup_albums, daemon=True).start()

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    
    # ✅ نتعامل مع Callbacks
    if 'callback_query' in data:
        handle_callback(data['callback_query'])
        return 'OK'
    
    if 'message' not in data:
        return 'OK'
    
    msg = data['message']
    chat_id = msg['chat']['id']
    message_id = msg['message_id']
    text = msg.get('text', '') or ''
    
    # ✅ @all
    if '@all' in text and msg['chat']['type'] in ['group', 'supergroup']:
        mention_all(chat_id)
        return 'OK'
    
    if msg['chat']['type'] == 'private':
        return 'OK'
    
    # ========== صورة ==========
    if 'photo' in msg:
        caption = msg.get('caption', '') or ''
        has_caption = '#كومنت' in caption
        media_group_id = msg.get('media_group_id')
        
        with album_lock:
            if media_group_id:
                if has_caption:
                    # أول صورة
                    name, users = parse_caption_multi(caption)
                    log(f"🆕 Album: {media_group_id} | Name: {name} | Users: {len(users)}")
                    
                    album_captions[media_group_id] = {
                        "caption": caption,
                        "name": name,
                        "users": users,
                        "from_chat": chat_id,
                        "message_id": message_id,
                        "time": datetime.now(),
                        "photos_count": 1
                    }
                    
                    current_user = users[0] if users else None
                    
                elif media_group_id in album_captions:
                    # صورة تانية
                    album = album_captions[media_group_id]
                    album["photos_count"] += 1
                    idx = album["photos_count"] - 1
                    
                    users = album["users"]
                    if idx < len(users):
                        current_user = users[idx]
                    else:
                        current_user = None  # مفيش يوزر كافي
                    
                    log(f"📸 #{album['photos_count']} | User: {current_user or 'None'}")
                    name = album["name"]
                    caption = album["caption"]
                else:
                    return 'OK'
            else:
                # صورة واحدة
                if not has_caption:
                    return 'OK'
                name, users = parse_caption_multi(caption)
                current_user = users[0] if users else None
        
        photos = msg['photo']
        best_photo = photos[-1]['file_id']
        current_date = datetime.now().strftime("%Y-%m-%d" )
        
        # ✅ نعمل callback_data للزرار (لليوزر أو بدون يوزر)
        short_name = name[:8] if len(name) > 8 else name
        
        if current_user:
            # في يوزر
            short_user = current_user[:10] if len(current_user) > 10 else current_user
            cb_verify = f"v|{chat_id}|{short_name}|{short_user}|{current_date}|{message_id}"
            display_user = current_user
        else:
            # ✅ مفيش يوزر - نستخدم "nouser" أو نتركه فاضي
            cb_verify = f"v|{chat_id}|{short_name}|nouser|{current_date}|{message_id}"
            display_user = "⚠️ غير محدد"
        
        # نختصر لو طويل
        if len(cb_verify) > 60:
            cb_verify = f"v|{chat_id}|{message_id}"
        
        cb_reject = f"r|{chat_id}|{message_id}"
        
        # ✅ زرار التأكيد والرفض لكل الصور (مع يوزر أو بدون)
        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ تأكيد", "callback_data": cb_verify},
                {"text": "❌ رفض", "callback_data": cb_reject}
            ]]
        }
        
        if current_user:
            verify_caption = (
                f"📝 كومنت جديد\n\n"
                f"👤 الاسم: {name}\n"
                f"🔹 اليوزر: {current_user}\n"
                f"📅 التاريخ: {current_date}"
            )
        else:
            # ✅ صورة بدون يوزر - بس مع زرار برضه
            verify_caption = (
                f"📝 كومنت جديد (بدون يوزر)\n\n"
                f"👤 الاسم: {name}\n"
                f"⚠️ اليوزر: غير محدد\n"
                f"📅 التاريخ: {current_date}"
            )
        
        if media_group_id:
            total_users = len(album_captions[media_group_id].get('users', []))
            current_count = album_captions[media_group_id]['photos_count']
            verify_caption += f"\n🆔 صورة {current_count}/{total_users if total_users >= current_count else current_count}"
        
        success, result = send_photo_with_keyboard(VERIFICATION_GROUP, best_photo, verify_caption, keyboard)
        
        if success and has_caption:
            count = album_captions[media_group_id]['photos_count'] if media_group_id else 1
            send_message(chat_id, 
                f"⏳ تم إرسال {count} كومنت للتأكيد!\n"
                f"👤 {name}",
                reply_to=message_id)
        
        return 'OK'
    
    return 'OK'

def handle_callback(query):
    data = query['data']
    query_id = query['id']
    message = query['message']
    chat_id = message['chat']['id']
    verifier_name = query['from'].get('first_name', 'Unknown')
    
    answer_url = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
    requests.post(answer_url, json={"callback_query_id": query_id}, timeout=5)
    
    parts = data.split('|')
    action = parts[0]
    
    if action == 'v':  # verify
        user_chat_id = int(parts[1])
        
        if len(parts) >= 6:
            name = parts[2]
            username = parts[3]
            if username == "nouser":
                username = "⚠️ غير محدد"  # ✅ نرجع النص الأصلي
            date = parts[4]
            original_msg_id = int(parts[5]) if parts[5].isdigit() else None
        else:
            caption = message.get('caption', '')
            name = "Unknown"
            username = "Unknown"
            date = datetime.now().strftime("%Y-%m-%d")
            original_msg_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
            
            for line in caption.split('\n'):
                if 'الاسم:' in line:
                    name = line.split(':', 1)[1].strip()
                elif 'اليوزر:' in line:
                    username = line.split(':', 1)[1].strip()
        
        money = calculate_money(1)
        
        # ✅ نسجل في Google Sheets (حتى لو مفيش يوزر)
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
            log(f"✅ Saved: {name} ({username}) by {verifier_name}")
        except Exception as e:
            log(f"❌ Sheets error: {e}")
        
        send_message(user_chat_id, 
            f"🎉 تم تأكيد الكومنت!\n"
            f"👤 {name} | {username}\n"
            f"💰 {money} ريال",
            reply_to=original_msg_id)
        
        new_caption = (
            f"✅ تم التأكيد بواسطة {verifier_name}\n\n"
            f"👤 {name}\n"
            f"🔹 {username}\n"
            f"📅 {date}"
        )
        
        edit_url = f"https://api.telegram.org/bot{TOKEN}/editMessageCaption"
        requests.post(edit_url, json={
            "chat_id": chat_id,
            "message_id": message['message_id'],
            "caption": new_caption,
            "parse_mode": "HTML"
        }, timeout=5)
        
    elif action == 'r':  # reject
        user_chat_id = int(parts[1])
        original_msg_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        
        send_message(user_chat_id, "❌ تم رفض الكومنت.", reply_to=original_msg_id)
        
        edit_url = f"https://api.telegram.org/bot{TOKEN}/editMessageCaption"
        requests.post(edit_url, json={
            "chat_id": chat_id,
            "message_id": message['message_id'],
            "caption": "❌ تم الرفض",
            "parse_mode": "HTML"
        }, timeout=5)

def calculate_money(total_comments):
    hundreds = total_comments // 100
    return hundreds * 5

@app.route('/')
def home():
    return "Bot OK"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

