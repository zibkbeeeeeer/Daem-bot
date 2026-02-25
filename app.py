import os
import json
import requests
from flask import Flask, request
from datetime import datetime

app = Flask(__name__)

# ✅ الصح: استخدم أسماء المتغيرات بس، القيم في Render
TOKEN = os.environ.get('TELEGRAM_TOKEN')
GOOGLE_URL = os.environ.get('GOOGLE_SCRIPT_URL')
VERIFICATION_GROUP = os.environ.get('VERIFICATION_GROUP_ID')
ADMIN_ID = os.environ.get('ADMIN_CHAT_ID')

# ✅ تأكد إن المتغيرات موجودة
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN not set!")
if not GOOGLE_URL:
    raise ValueError("GOOGLE_SCRIPT_URL not set!")
if not VERIFICATION_GROUP:
    raise ValueError("VERIFICATION_GROUP_ID not set!")

user_data = {}

def send_message(chat_id, text, reply_markup=None):
    # ✅ مفيش مسافة بعد "bot"
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"Sent message: {response.status_code}")
        return response.json()
    except Exception as e:
        print(f"Error sending message: {e}")
        return None

def send_photo(chat_id, photo, caption, reply_markup=None):
    # ✅ مفيش مسافة بعد "bot"
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
        response = requests.post(url, json=payload, timeout=10)
        print(f"Sent photo: {response.status_code}")
        return response.json()
    except Exception as e:
        print(f"Error sending photo: {e}")
        return None

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        print(f"Webhook received: {data}")
        
        if 'message' in data:
            msg = data['message']
            chat_id = msg['chat']['id']
            print(f"Message from {chat_id}")
            
            if 'text' in msg and msg['text'] == '/start':
                print("Processing /start")
                send_message(chat_id, 
                    "👋 أهلاً بيك في بوت داعم!\n\n"
                    "📸 عشان تسجل كومنت جديد:\n"
                    "1️⃣ ابعت صورة للكومنت (Screenshot)\n"
                    "2️⃣ اكتب اسمك الحقيقي\n"
                    "3️⃣ اكتب اليوزر اللي علقت بيه\n\n"
                    "💰 <b>النظام:</b>\n"
                    "• كل 100 كومنت = 5 ريال\n"
                    "• لكل يوزر مختلف\n\n"
                    "ابعت صورة دلوقتي:")
                user_data[chat_id] = {'step': 'waiting_photo'}
                print(f"Started chat with {chat_id}")
            
            elif 'photo' in msg and chat_id in user_data:
                if user_data[chat_id]['step'] == 'waiting_photo':
                    photo = msg['photo'][-1]['file_id']
                    user_data[chat_id]['photo'] = photo
                    user_data[chat_id]['step'] = 'waiting_name'
                    send_message(chat_id, "✅ تم استلام الصورة\n\nاكتب اسمك الحقيقي:")
                    print(f"Got photo from {chat_id}")
            
            elif 'text' in msg and chat_id in user_data:
                text = msg['text']
                step = user_data[chat_id].get('step')
                
                if step == 'waiting_name':
                    user_data[chat_id]['name'] = text
                    user_data[chat_id]['step'] = 'waiting_username'
                    send_message(chat_id, 
                        f"تمام يا {text}!\n\n"
                        f"دلوقتي اكتب اليوزر اللي علقت بيه:\n"
                        f"مثال: @azam_tik1")
                    print(f"Got name: {text}")
                
                elif step == 'waiting_username':
                    username = text if text.startswith('@') else f"@{text}"
                    user_data[chat_id]['username'] = username
                    
                    current_date = datetime.now().strftime("%Y-%m-%d")
                    
                    caption = (
                        f"📝 <b>كومنت جديد للتأكيد</b>\n\n"
                        f"👤 <b>الاسم:</b> {user_data[chat_id]['name']}\n"
                        f"🔹 <b>اليوزر:</b> {username}\n"
                        f"📅 <b>التاريخ:</b> {current_date}\n"
                        f"🆔 <b>معرف المستخدم:</b> {chat_id}\n\n"
                        f"💰 كل 100 كومنت بـ 5 ريال"
                    )
                    
                    keyboard = {
                        "inline_keyboard": [[
                            {"text": "✅ تأكيد", "callback_data": f"verify|{chat_id}|{user_data[chat_id]['name']}|{username}|{current_date}"},
                            {"text": "❌ رفض", "callback_data": f"reject|{chat_id}"}
                        ]]
                    }
                    
                    send_photo(VERIFICATION_GROUP, user_data[chat_id]['photo'], caption, keyboard)
                    
                    send_message(chat_id, 
                        "⏳ تم إرسال الكومنت للتأكيد!\n"
                        "هنبلغك لما يتم التأكيد ✅")
                    
                    print(f"Sent to verification: {username}")
                    del user_data[chat_id]
        
        elif 'callback_query' in data:
            handle_callback(data['callback_query'])
        
        return 'OK'
    except Exception as e:
        print(f"Error in webhook: {e}")
        return 'Error', 500

def handle_callback(query):
    try:
        data = query['data']
        chat_id = query['message']['chat']['id']
        message_id = query['message']['message_id']
        verifier_name = query['from'].get('first_name', 'Unknown')
        
        if data.startswith('verify'):
            parts = data.split('|')
            user_chat_id = parts[1]
            name = parts[2]
            username = parts[3]
            date = parts[4]
            
            print(f"Verifying: {name} - {username}")
            
            try:
                response = requests.post(GOOGLE_URL, json={
                    'action': 'add_comment',
                    'name': name,
                    'username': username,
                    'date': date,
                    'status': '✅ تم التأكيد',
                    'verifiedBy': verifier_name,
                    'amount': 5,
                    'photoUrl': query['message'].get('photo', [{}])[0].get('file_id', '')
                }, timeout=10)
                print(f"Google Sheets response: {response.status_code}")
            except Exception as e:
                print(f"Error saving to Google Sheets: {e}")
            
            send_message(user_chat_id, 
                f"🎉 تم تأكيد كومنتك!\n\n"
                f"📅 التاريخ: {date}\n"
                f"👤 الاسم: {name}\n"
                f"🔹 اليوزر: {username}\n"
                f"💰 المبلغ: 5 ريال لكل 100 كومنت")
            
            new_caption = (
                f"✅ <b>تم التأكيد</b>\n\n"
                f"👤 <b>الاسم:</b> {name}\n"
                f"🔹 <b>اليوزر:</b> {username}\n"
                f"📅 <b>التاريخ:</b> {date}\n"
                f"✅ <b>تم التأكيد بواسطة:</b> {verifier_name}"
            )
            
            # ✅ مفيش مسافة بعد "bot"
            url = f"https://api.telegram.org/bot{TOKEN}/editMessageCaption"
            requests.post(url, json={
                "chat_id": chat_id,
                "message_id": message_id,
                "caption": new_caption,
                "parse_mode": "HTML"
            })
            
        elif data.startswith('reject'):
            user_chat_id = data.split('|')[1]
            send_message(user_chat_id, "❌ تم رفض الكومنت. تأكد من وضوح الصورة.")
            
    except Exception as e:
        print(f"Error in callback: {e}")

@app.route('/')
def home():
    return "Daem Bot is running! 💰"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
