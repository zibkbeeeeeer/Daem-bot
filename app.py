import os
import json
import requests
import math
from flask import Flask, request
from datetime import datetime
from threading import Timer

app = Flask(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN')
GOOGLE_URL = os.environ.get('GOOGLE_SCRIPT_URL')
VERIFICATION_GROUP = os.environ.get('VERIFICATION_GROUP_ID')
ADMIN_ID = os.environ.get('ADMIN_CHAT_ID')

pending_albums = {}

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

def send_photo(chat_id, photo, caption, reply_to=None, reply_markup=None):
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
        return response.json()
    except Exception as e:
        print(f"Error: {e}")
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

def process_album(media_group_id):
    if media_group_id not in pending_albums:
        return
    
    album = pending_albums[media_group_id]
    photos = album["photos"]
    caption = album["caption"]
    from_chat = album["from_chat"]
    original_message_id = album["message_id"]  # عشان نعمل reply عليه
    
    del pending_albums[media_group_id]
    
    clean_caption = caption.replace('#كومنت', '').strip()
    
    name, username, error = parse_caption(clean_caption)
    if error:
        # ✅ Reply على رسالته الأصلية
        send_message(from_chat, error, reply_to=original_message_id)
        return
    
    count = len(photos)
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
    
    # ✅ بعت الألبوم كامل للتأكيد
    result = send_media_group(VERIFICATION_GROUP, photos, caption_verification)
    
    # ✅ ابعت الـ keyboard في رسالة تانية (Reply على الألبوم لو نجح)
    keyboard = {
        "inline_keyboard": [[
            {"text": f"✅ تأكيد الكل ({count})", "callback_data": f"verify_multi|{from_chat}|{name}|{username}|{count}|{current_date}|{original_message_id}"},
            {"text": "❌ رفض", "callback_data": f"reject|{from_chat}|{original_message_id}"}
        ]]
    }
    
    send_message(VERIFICATION_GROUP, 
        f"☝️ {count} كومنتات للتأكيد | 👤 {name} | 🔹 {username}", 
        reply_markup=keyboard)
    
    # ✅ Reply على رسالة الشخص الأصلية
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
    message_id = msg['message_id']  # عشان نعمل reply عليه
    
    if msg['chat']['type'] == 'private':
        return 'OK'
    
    # ========== ألبوم صور ==========
    if 'media_group_id' in msg and 'photo' in msg:
        caption = msg.get('caption', '')
        if '#كومنت' not in caption:
            return 'OK'
        
        media_group_id = msg['media_group_id']
        photo = msg['photo'][-1]['file_id']
        
        if media_group_id not in pending_albums:
            pending_albums[media_group_id] = {
                "photos": [],
                "caption": caption,
                "from_chat": chat_id,
                "message_id": message_id,  # حفظ ID الرسالة الأصلية
                "timer": None
            }
        
        pending_albums[media_group_id]["photos"].append(photo)
        
        if pending_albums[media_group_id]["timer"]:
            pending_albums[media_group_id]["timer"].cancel()
        
        timer = Timer(3.0, process_album, args=[media_group_id])
        pending_albums[media_group_id]["timer"] = timer
        timer.start()
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
        money = calculate_money(1)
        
        caption_verification = (
            f"📝 <b>كومنت جديد</b>\n\n"
            f"👤 <b>الاسم:</b> {name}\n"
            f"🔹 <b>اليوزر:</b> {username}\n"
            f"📅 <b>التاريخ:</b> {current_date}\n"
            f"📊 1 كومنت (0 ريال)"
        )
        
        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ تأكيد", "callback_data": f"verify|{chat_id}|{name}|{username}|{current_date}|1|{message_id}"},
                {"text": "❌ رفض", "callback_data": f"reject|{chat_id}|{message_id}"}
            ]]
        }
        
        send_photo(VERIFICATION_GROUP, photo, caption_verification, reply_markup=keyboard)
        
        # ✅ Reply على رسالة الشخص
        send_message(chat_id, "⏳ تم إرسال الكومنت للتأكيد!", reply_to=message_id)
        return 'OK'
    
    # ========== Reply على صورة ==========
    elif 'reply_to_message' in msg and '#كومنت' in msg.get('text', ''):
        original_msg = msg['reply_to_message']
        
        if 'photo' not in original_msg:
            send_message(chat_id, "❌ لازم ترد على صورة!", reply_to=message_id)
            return 'OK'
        
        photo = original_msg['photo'][-1]['file_id']
        caption = msg.get('text', '')
        
        clean_caption = caption.replace('#كومنت', '').strip()
        name, username, error = parse_caption(clean_caption)
        if error:
            send_message(chat_id, error, reply_to=message_id)
            return 'OK'
        
        current_date = datetime.now().strftime("%Y-%m-%d")
        money = calculate_money(1)
        
        caption_verification = (
            f"📝 <b>كومنت جديد (Reply)</b>\n\n"
            f"👤 <b>الاسم:</b> {name}\n"
            f"🔹 <b>اليوزر:</b> {username}\n"
            f"📅 <b>التاريخ:</b> {current_date}\n"
            f"📊 1 كومنت (0 ريال)"
        )
        
        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ تأكيد", "callback_data": f"verify|{chat_id}|{name}|{username}|{current_date}|1|{original_msg['message_id']}"},
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
    message_id = message['message_id']
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
        
        # ✅ سجل كل صورة ككومنت منفصل (count مرات)
        for i in range(count):
            try:
                requests.post(GOOGLE_URL, json={
                    'action': 'add_comment',
                    'name': name,
                    'username': username,
                    'date': date,
                    'count': 1,  # كل صورة = كومنت واحد
                    'status': '✅ تم التأكيد',
                    'verifiedBy': verifier_name,
                    'amount': 0 if (i+1) % 100 != 0 else 5  # المبلغ على كل 100
                }, timeout=10)
            except Exception as e:
                print(f"Error saving comment {i+1}: {e}")
        
        # ✅ Reply على رسالة الشخص الأصلية
        reply_text = (
            f"🎉 تم تأكيد {count} كومنتات!\n\n"
            f"👤 {name} | {username}\n"
            f"📊 {count} كومنت\n"
            f"💰 {money} ريال (كل 100 = 5 ريال)"
        )
        
        if original_message_id:
            send_message(user_chat_id, reply_text, reply_to=original_message_id)
        else:
            send_message(user_chat_id, reply_text)
        
    elif data.startswith('verify'):
        parts = data.split('|')
        user_chat_id = parts[1]
        name = parts[2]
        username = parts[3]
        date = parts[4]
        count = int(parts[5]) if len(parts) > 5 else 1
        original_message_id = parts[6] if len(parts) > 6 else None
        
        money = calculate_money(count)
        
        try:
            requests.post(GOOGLE_URL, json={
                'action': 'add_comment',
                'name': name,
                'username': username,
                'date': date,
                'count': 1,
                'status': '✅ تم التأكيد',
                'verifiedBy': verifier_name,
                'amount': money
            }, timeout=10)
        except Exception as e:
            print(f"Error: {e}")
        
        reply_text = (
            f"🎉 تم تأكيد {count} كومنت!\n"
            f"👤 {name} | {username}\n"
            f"💰 {money} ريال"
        )
        
        if original_message_id:
            send_message(user_chat_id, reply_text, reply_to=original_message_id)
        else:
            send_message(user_chat_id, reply_text)
        
    elif data.startswith('reject'):
        parts = data.split('|')
        user_chat_id = parts[1]
        original_message_id = parts[2] if len(parts) > 2 else None
        
        if original_message_id:
            send_message(user_chat_id, "❌ تم رفض الكومنتات.", reply_to=original_message_id)
        else:
            send_message(user_chat_id, "❌ تم رفض الكومنتات.")

@app.route('/')
def home():
    return "Daem Bot is running! 💰"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

