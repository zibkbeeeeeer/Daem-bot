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

album_captions = {}
album_lock = Lock()

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def send_photo_with_keyboard(chat_id, photo, caption, keyboard, reply_to=None):
    """نبعت صورة مع كيبورد"""
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
    
    # ✅ نتعامل مع Callbacks (زرار التأكيد)
    if 'callback_query' in data:
        handle_callback(data['callback_query'])
        return 'OK'
    
    if 'message' not in data:
        return 'OK'
    
    msg = data['message']
    chat_id = msg['chat']['id']
    message_id = msg['message_id']
    
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
                    log(f"🆕 Album: {media_group_id}")
                    album_captions[media_group_id] = {
                        "caption": caption,
                        "from_chat": chat_id,
                        "message_id": message_id,
                        "time": datetime.now(),
                        "count": 1
                    }
                    use_caption = caption
                elif media_group_id in album_captions:
                    album_captions[media_group_id]["count"] += 1
                    use_caption = album_captions[media_group_id]["caption"]
                    log(f"📸 #{album_captions[media_group_id]['count']}")
                else:
                    return 'OK'
            else:
                if not has_caption:
                    return 'OK'
                use_caption = caption
        
        # Parse
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
            log(f"❌ Parse fail")
            return 'OK'
        
        photos = msg['photo']
        best_photo = photos[-1]['file_id']
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # ✅ نعمل callback_data مختصر (أقل من 64 حرف)
        # v = verify, r = reject
        # نستخدم أول 8 حروف من الاسم واليوزر
        short_name = name[:8] if len(name) > 8 else name
        short_user = username[:10] if len(username) > 10 else username
        
        # callback: v|chat_id|name|user|date|msg_id
        cb_verify = f"v|{chat_id}|{short_name}|{short_user}|{current_date}|{message_id}"
        cb_reject = f"r|{chat_id}|{message_id}"
        
        # لو طويل نختصر أكتر
        if len(cb_verify) > 60:
            cb_verify = f"v|{chat_id}|{message_id}"
        
        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ تأكيد", "callback_data": cb_verify},
                {"text": "❌ رفض", "callback_data": cb_reject}
            ]]
        }
        
        verify_caption = (
            f"📝 كومنت جديد\n\n"
            f"👤 الاسم: {name}\n"
            f"🔹 اليوزر: {username}\n"
            f"📅 التاريخ: {current_date}"
        )
        
        if media_group_id:
            verify_caption += f"\n🆔 ألبوم: {str(media_group_id)[-6:]}"
        
        success, result = send_photo_with_keyboard(VERIFICATION_GROUP, best_photo, verify_caption, keyboard)
        
        if success:
            log(f"✅ Sent: {name}")
            if has_caption:
                send_message(chat_id, 
                    f"⏳ تم إرسال الكومنت للتأكيد!\n"
                    f"👤 {name} | {username}",
                    reply_to=message_id)
        else:
            # لو فشل بسبب الكيبورد، نبعت من غيره
            log(f"⚠️ Retrying without keyboard...")
            send_photo_with_keyboard(VERIFICATION_GROUP, best_photo, verify_caption, None)
        
        return 'OK'
    
    return 'OK'

def handle_callback(query):
    """نتعامل مع زرار التأكيد/الرفض"""
    data = query['data']
    query_id = query['id']
    message = query['message']
    chat_id = message['chat']['id']  # جروب التأكيد
    verifier_name = query['from'].get('first_name', 'Unknown')
    
    # نرد على التليجرام فوراً (عشان الزرار ما يفضلش loading)
    answer_url = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
    requests.post(answer_url, json={"callback_query_id": query_id}, timeout=5)
    
    parts = data.split('|')
    action = parts[0]
    
    if action == 'v':  # verify
        user_chat_id = int(parts[1])
        
        # نجيب البيانات
        if len(parts) >= 6:
            name = parts[2]
            username = parts[3]
            date = parts[4]
            original_msg_id = int(parts[5]) if parts[5].isdigit() else None
        else:
            # لو مختصر، نجيب من الكابشن
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
        
        # ✅ نسجل في Google Sheets
        try:
            response = requests.post(GOOGLE_URL, json={
                'action': 'add_comment',
                'name': name,
                'username': username,
                'date': date,
                'count': 1,
                'status': '✅ تم التأكيد',
                'verifiedBy': verifier_name,
                'amount': 0
            }, timeout=10)
            log(f"✅ Saved to Sheets: {name} by {verifier_name}")
        except Exception as e:
            log(f"❌ Sheets error: {e}")
        
        # نرد على المستخدم
        send_message(user_chat_id, 
            f"🎉 تم تأكيد الكومنت!\n"
            f"👤 {name} | {username}\n"
            f"💰 {money} ريال",
            reply_to=original_msg_id)
        
        # نعدل الكابشن في جروب التأكيد
        new_caption = (
            f"✅ تم التأكيد بواسطة {verifier_name}\n\n"
            f"👤 {name}\n"
            f"🔹 {username}\n"
            f"📅 {date}"
        )
        
        # نحاول نعدل الرسالة (editMessageCaption)
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
        
        # نعدل الكابشن
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
