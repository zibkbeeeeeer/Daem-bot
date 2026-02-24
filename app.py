import os
import json
import requests
from flask import Flask, request
from datetime import datetime

app = Flask(__name__)

TOKEN = os.environ.get('8627700788:AAFWZaYAeQroj5C3rQSa61oWjUrrKnKu7aE')
GOOGLE_URL = os.environ.get('https://script.google.com/macros/s/AKfycbzhMePwZKmFETty-yDKh0JJhmHGK-YknC_MYnoRWFlDXkVEPV-LxS5b3M0m1Hs1waD2/exec')
VERIFICATION_GROUP = os.environ.get('-1005150345521')
ADMIN_ID = os.environ.get('6239436951')

user_data = {}

def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(url, json=payload)

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
    requests.post(url, json=payload)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    
    if 'message' in data:
        msg = data['message']
        chat_id = msg['chat']['id']
        
        if 'text' in msg and msg['text'] == '/start':
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
        
        elif 'photo' in msg and chat_id in user_data:
            if user_data[chat_id]['step'] == 'waiting_photo':
                photo = msg['photo'][-1]['file_id']
                user_data[chat_id]['photo'] = photo
                user_data[chat_id]['step'] = 'waiting_name'
                send_message(chat_id, "✅ تم استلام الصورة\n\nاكتب اسمك الحقيقي:")
        
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
                
                del user_data[chat_id]
    
    elif 'callback_query' in data:
        handle_callback(data['callback_query'])
    
    return 'OK'

def handle_callback(query):
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
        
        response = requests.post(GOOGLE_URL, json={
            'action': 'add_comment',
            'name': name,
            'username': username,
            'date': date,
            'status': '✅ تم التأكيد',
            'verifiedBy': verifier_name,
            'amount': 5,
            'photoUrl': query['message'].get('photo', [{}])[0].get('file_id', '')
        })
        
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

@app.route('/')
def home():
    return "Daem Bot is running! 💰"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
