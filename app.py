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

def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending message: {e}")

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

def process_album(media_group_id):
    if media_group_id not in pending_albums:
        return
    
    album = pending_albums[media_group_id]
    photos = album["photos"]
    caption = album["caption"]
    from_chat = album["from_chat"]
    
    del pending_albums[media_group_id]
    
    clean_caption = caption.replace('#كومنت', '').strip()
    
    name, username, error = parse_caption(clean_caption)
    if error:
        send_message(from_chat, error)
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
    
    keyboard = {
        "inline_keyboard": [[
            {"text": f"✅ تأكيد {count}", "callback_data": f"verify_multi|{from_chat}|{name}|{username}|{count}|{current_date}"},
            {"text": "❌ رفض", "callback_data": f"reject|{from_chat}"}
        ]]
    }
    
    send_photo(VERIFICATION_GROUP, photos[0], caption_verification, keyboard)
    
    send_message(from_chat, 
        f"⏳ تم إرسال {count} كومنتات للتأكيد!\n\n"
        f"👤 {name} | {username}\n"
        f"📊 {count} كومنت\n"
        f"💰 {money} ريال (كل 100 = 5 ريال)")

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    
    if 'message' not in data:
        if 'callback_query' in data:
            handle_callback(data['callback_query'])
        return 'OK'
    
    msg = data['message']
    chat_id = msg['chat']['id']
    
    # تجاهل الرسايل الخاصة
    if msg['chat']['type'] == 'private':
        return 'OK'
    
    # ========== الطريقة 1: ألبوم صور + كابشن ==========
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
                "timer": None
            }
        
        pending_albums[media_group_id]["photos"].append(photo)
        
        if pending_albums[media_group_id]["timer"]:
            pending_albums[media_group_id]["timer"].cancel()
        
        timer = Timer(3.0, process_album, args=[media_group_id])
        pending_albums[media_group_id]["timer"] = timer
        timer.start()
        return 'OK'
    
    # ========== الطريقة 2: صورة واحدة + كابشن ==========
    elif 'photo' in msg and '#كومنت' in (msg.get('caption', '')):
        photo = msg['photo'][-1]['file_id']
        caption = msg.get('caption', '')
        
        clean_caption = caption.replace('#كومنت', '').strip()
        name, username, error = parse_caption(clean_caption)
        if error:
            send_message(chat_id, error)
            return 'OK'
        
        current_date = datetime.now().strftime("%Y-%m-%d")
        money = calculate_money(1)
        
        caption_verification = (
            f"📝 <b>كومنت جديد</b>\n\n"
            f"👤 <b>الاسم:</b> {name}\n"
            f"🔹 <b>اليوزر:</b> {username}\n"
            f"📅 <b>التاريخ:</b> {current_date}\n"
            f"📊 1 كومنت (0 ريال - لسه ما وصلتش 100)"
        )
        
        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ تأكيد", "callback_data": f"verify|{chat_id}|{name}|{username}|{current_date}|1"},
                {"text": "❌ رفض", "callback_data": f"reject|{chat_id}"}
            ]]
        }
        
        send_photo(VERIFICATION_GROUP, photo, caption_verification, keyboard)
        send_message(chat_id, "⏳ تم إرسال الكومنت للتأكيد!")
        return 'OK'
    
    # ========== الطريقة 3: Reply على صورة ==========
    elif 'reply_to_message' in msg and '#كومنت' in msg.get('text', ''):
        original_msg = msg['reply_to_message']
        
        if 'photo' not in original_msg:
            send_message(chat_id, "❌ لازم ترد على صورة!")
            return 'OK'
        
        photo = original_msg['photo'][-1]['file_id']
        caption = msg.get('text', '')
        
        clean_caption = caption.replace('#كومنت', '').strip()
        name, username, error = parse_caption(clean_caption)
        if error:
            send_message(chat_id, error)
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
                {"text": "✅ تأكيد", "callback_data": f"verify|{chat_id}|{name}|{username}|{current_date}|1"},
                {"text": "❌ رفض", "callback_data": f"reject|{chat_id}"}
            ]]
        }
        
        send_photo(VERIFICATION_GROUP, photo, caption_verification, keyboard)
        send_message(chat_id, "⏳ تم إرسال الكومنت للتأكيد!")
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
        
        money = calculate_money(count)
        
        try:
            requests.post(GOOGLE_URL, json={
                'action': 'add_comment',
                'name': name,
                'username': username,
                'date': date,
                'count': count,
                'status': '✅ تم التأكيد',
                'verifiedBy': verifier_name,
                'amount': money
            }, timeout=10)
        except Exception as e:
            print(f"Error saving to Google Sheets: {e}")
        
        send_message(user_chat_id, 
            f"🎉 تم تأكيد {count} كومنتات!\n\n"
            f"👤 {name} | {username}\n"
            f"📊 {count} كومنت\n"
            f"💰 {money} ريال (كل 100 = 5 ريال)")
        
        new_caption = (
            f"✅ <b>تم تأكيد {count} كومنتات</b>\n"
            f"👤 {name} | {username}\n"
            f"💰 {money} ريال\n"
            f"✅ بواسطة: {verifier_name}"
        )
        
        url = f"https://api.telegram.org/bot{TOKEN}/editMessageCaption"
        requests.post(url, json={
            "chat_id": chat_id,
            "message_id": message_id,
            "caption": new_caption,
            "parse_mode": "HTML"
        })
        
    elif data.startswith('verify'):
        parts = data.split('|')
        user_chat_id = parts[1]
        name = parts[2]
        username = parts[3]
        date = parts[4]
        count = int(parts[5]) if len(parts) > 5 else 1
        
        money = calculate_money(count)
        
        try:
            requests.post(GOOGLE_URL, json={
                'action': 'add_comment',
                'name': name,
                'username': username,
                'date': date,
                'count': count,
                'status': '✅ تم التأكيد',
                'verifiedBy': verifier_name,
                'amount': money
            }, timeout=10)
        except Exception as e:
            print(f"Error saving: {e}")
        
        send_message(user_chat_id, 
            f"🎉 تم تأكيد {count} كومنت!\n"
            f"👤 {name} | {username}\n"
            f"💰 {money} ريال")
        
    elif data.startswith('reject'):
        user_chat_id = data.split('|')[1]
        send_message(user_chat_id, "❌ تم رفض الكومنتات.")

@app.route('/')
def home():
    return "Daem Bot is running! 💰"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
