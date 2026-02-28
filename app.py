import os
import json
import requests
import math
import time
from flask import Flask, request
from datetime import datetime
from threading import Lock

app = Flask(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN')
GOOGLE_URL = os.environ.get('GOOGLE_SCRIPT_URL')
VERIFICATION_GROUP = os.environ.get('VERIFICATION_GROUP_ID')
ADMIN_ID = os.environ.get('ADMIN_CHAT_ID')

# Lock عشان نتجنب التكرار
global_lock = Lock()

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

def send_photo(chat_id, photo, caption, reply_markup=None, reply_to=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    payload = {
        "chat_id": chat_id,
        "photo": photo,
        "caption": caption,
        "parse_mode": "HTML"
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error sending photo: {e}")
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
        
        # نجيب كل الصور (كل الجودات، نختار أعلى جودة لكل صورة)
        photos = msg['photo']  # ده list بكل جودات الصورة الواحدة
        best_photo = photos[-1]['file_id']  # أعلى جودة
        
        media_group_id = msg['media_group_id']
        
        clean_caption = caption.replace('#كومنت', '').strip()
        name, username, error = parse_caption(clean_caption)
        
        if error:
            send_message(chat_id, error, reply_to=message_id)
            return 'OK'
        
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # ✅ نبعت الصورة فوراً لجروب التأكيد
        caption_verification = (
            f"📝 <b>كومنت جديد</b> (جزء من ألبوم)\n\n"
            f"👤 <b>الاسم:</b> {name}\n"
            f"🔹 <b>اليوزر:</b> {username}\n"
            f"📅 <b>التاريخ:</b> {current_date}\n"
            f"🆔 <b>ألبوم:</b> {media_group_id}"
        )
        
        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ تأكيد", "callback_data": f"verify|{chat_id}|{name}|{username}|{current_date}|1|{message_id}|{media_group_id}"},
                {"text": "❌ رفض", "callback_data": f"reject|{chat_id}|{message_id}"}
            ]]
        }
        
        # نبعت الصورة
        result = send_photo(VERIFICATION_GROUP, best_photo, caption_verification, reply_markup=keyboard)
        
        if result and result.get('ok'):
            print(f"✅ Sent photo to verification: {name} | Album: {media_group_id}")
        else:
            print(f"❌ Failed to send photo: {result}")
        
        # نرد على المستخدم
        send_message(chat_id, 
            f"⏳ تم إرسال الكومنت للتأكيد!\n"
            f"👤 {name} | {username}",
            reply_to=message_id)
        
        return 'OK'
    
    # ========== صورة واحدة (بدون media_group_id) ==========
    elif 'photo' in msg and '#كومنت' in (msg.get('caption', '')):
        photos = msg['photo']
        best_photo = photos[-1]['file_id']
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
                {"text": "✅ تأكيد", "callback_data": f"verify|{chat_id}|{name}|{username}|{current_date}|1|{message_id}|single"},
                {"text": "❌ رفض", "callback_data": f"reject|{chat_id}|{message_id}"}
            ]]
        }
        
        send_photo(VERIFICATION_GROUP, best_photo, caption_verification, reply_markup=keyboard)
        send_message(chat_id, "⏳ تم إرسال الكومنت للتأكيد!", reply_to=message_id)
        return 'OK'
    
    return 'OK'

def handle_callback(query):
    data = query['data']
    message = query['message']
    chat_id = message['chat']['id']
    verifier_name = query['from'].get('first_name', 'Unknown')
    
    parts = data.split('|')
    action = parts[0]
    
    if action == 'verify':
        user_chat_id = parts[1]
        name = parts[2]
        username = parts[3]
        date = parts[4]
        count = int(parts[5])
        original_message_id = parts[6]
        album_id = parts[7] if len(parts) > 7 else 'single'
        
        money = calculate_money(count)
        
        # ✅ نسجل في Google Sheets
        try:
            response = requests.post(GOOGLE_URL, json={
                'action': 'add_comment',
                'name': name,
                'username': username,
                'date': date,
                'count': count,
                'status': '✅ تم التأكيد',
                'verifiedBy': verifier_name,
                'amount': 0,
                'album_id': album_id
            }, timeout=10)
            print(f"✅ Saved to Sheets: {name} | {count} | Album: {album_id}")
        except Exception as e:
            print(f"❌ Error saving: {e}")
        
        # نرد على المستخدم
        send_message(user_chat_id, 
            f"🎉 تم تأكيد الكومنت!\n"
            f"👤 {name} | {username}\n"
            f"💰 {money} ريال",
            reply_to=original_message_id)
        
        # نعدل الرسالة الأصلية في جروب التأكيد
        new_text = (
            f"✅ <b>تم التأكيد بواسطة {verifier_name}</b>\n\n"
            f"👤 {name} | {username}\n"
            f"📅 {date}"
        )
        send_message(chat_id, new_text, reply_to=message['message_id'])
        
    elif action == 'reject':
        user_chat_id = parts[1]
        original_message_id = parts[2] if len(parts) > 2 else None
        
        send_message(user_chat_id, "❌ تم رفض الكومنت.", reply_to=original_message_id)

@app.route('/')
def home():
    return "Daem Bot Running! 💰"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
