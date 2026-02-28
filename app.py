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
        r = requests.post(url, json=payload, timeout=10)
        return r.json()
    except Exception as e:
        print(f"Error: {e}")
        return None

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
        r = requests.post(url, json=payload, timeout=10)
        result = r.json()
        if not result.get('ok'):
            print(f"❌ send_photo error: {result}")
        return result
    except Exception as e:
        print(f"❌ Exception send_photo: {e}")
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
        
        photos = msg['photo']
        best_photo = photos[-1]['file_id']
        
        clean_caption = caption.replace('#كومنت', '').strip()
        name, username, error = parse_caption(clean_caption)
        
        if error:
            send_message(chat_id, error, reply_to=message_id)
            return 'OK'
        
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # ✅ callback_data مختصر (مش أكتر من 64 حرف)
        # نستخدم أول 10 حروف من الاسم واليوزر عشان نختصر
        short_name = name[:10] if len(name) > 10 else name
        short_user = username[:15] if len(username) > 15 else username
        
        callback_data = f"v|{chat_id}|{short_name}|{short_user}|{current_date}|{message_id}"
        
        # لو طويل، نختصر أكتر
        if len(callback_data) > 60:
            callback_data = f"v|{chat_id}|{message_id}"
        
        caption_verification = (
            f"📝 <b>كومنت جديد</b>\n\n"
            f"👤 <b>الاسم:</b> {name}\n"
            f"🔹 <b>اليوزر:</b> {username}\n"
            f"📅 <b>التاريخ:</b> {current_date}"
        )
        
        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ تأكيد", "callback_data": callback_data},
                {"text": "❌ رفض", "callback_data": f"r|{chat_id}|{message_id}"}
            ]]
        }
        
        print(f"📤 Sending photo: {name} | callback: {callback_data[:30]}...")
        
        result = send_photo(VERIFICATION_GROUP, best_photo, caption_verification, reply_markup=keyboard)
        
        if result and result.get('ok'):
            print(f"✅ Sent successfully")
            send_message(chat_id, 
                f"⏳ تم إرسال الكومنت للتأكيد!\n"
                f"👤 {name} | {username}",
                reply_to=message_id)
        else:
            print(f"❌ Failed: {result}")
            # لو فشل بسبب الكيبورد، نبعت من غير كيبورد
            send_photo(VERIFICATION_GROUP, best_photo, caption_verification)
            send_message(VERIFICATION_GROUP, f"⚠️ تأكيد يدوي: {name} | {username}")
        
        return 'OK'
    
    # ========== صورة واحدة ==========
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
        
        short_name = name[:10] if len(name) > 10 else name
        short_user = username[:15] if len(username) > 15 else username
        
        callback_data = f"v|{chat_id}|{short_name}|{short_user}|{current_date}|{message_id}"
        if len(callback_data) > 60:
            callback_data = f"v|{chat_id}|{message_id}"
        
        caption_verification = (
            f"📝 <b>كومنت جديد</b>\n\n"
            f"👤 <b>الاسم:</b> {name}\n"
            f"🔹 <b>اليوزر:</b> {username}\n"
            f"📅 <b>التاريخ:</b> {current_date}"
        )
        
        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ تأكيد", "callback_data": callback_data},
                {"text": "❌ رفض", "callback_data": f"r|{chat_id}|{message_id}"}
            ]]
        }
        
        send_photo(VERIFICATION_GROUP, best_photo, caption_verification, reply_markup=keyboard)
        send_message(chat_id, "⏳ تم إرسال الكومنت!", reply_to=message_id)
        return 'OK'
    
    return 'OK'

def handle_callback(query):
    data = query['data']
    message = query['message']
    chat_id = message['chat']['id']
    verifier_name = query['from'].get('first_name', 'Unknown')
    
    parts = data.split('|')
    action = parts[0]
    
    if action == 'v':  # verify
        user_chat_id = parts[1]
        
        # لو البيانات كاملة
        if len(parts) >= 5:
            name = parts[2]
            username = parts[3]
            date = parts[4]
            original_message_id = parts[5] if len(parts) > 5 else None
        else:
            # لو مختصر، نجيب من الكابشن
            caption = message.get('caption', '')
            name = "Unknown"
            username = "Unknown"
            date = datetime.now().strftime("%Y-%m-%d")
            original_message_id = parts[2] if len(parts) > 2 else None
            
            # نحاول نجيب الاسم من الكابشن
            for line in caption.split('\n'):
                if 'الاسم:' in line:
                    name = line.split(':', 1)[1].strip()
                elif 'اليوزر:' in line:
                    username = line.split(':', 1)[1].strip()
        
        money = calculate_money(1)
        
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
            print(f"✅ Saved: {name}")
        except Exception as e:
            print(f"❌ Error: {e}")
        
        send_message(user_chat_id, 
            f"🎉 تم تأكيد الكومنت!\n"
            f"👤 {name} | {username}\n"
            f"💰 {money} ريال",
            reply_to=original_message_id)
        
        # نعدل الرسالة
        new_caption = (
            f"✅ <b>تم التأكيد بواسطة {verifier_name}</b>\n\n"
            f"👤 {name}\n"
            f"🔹 {username}"
        )
        # نبعت صورة جديدة (مش نقدر نعدل الكابشن)
        send_message(chat_id, new_caption, reply_to=message['message_id'])
        
    elif action == 'r':  # reject
        user_chat_id = parts[1]
        original_message_id = parts[2] if len(parts) > 2 else None
        send_message(user_chat_id, "❌ تم رفض.", reply_to=original_message_id)

@app.route('/')
def home():
    return "Bot Running!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
