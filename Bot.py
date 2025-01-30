import os
import telebot
import google.generativeai as genai
import pymongo
import requests
from dotenv import load_dotenv
from datetime import datetime, timezone
from textblob import TextBlob
from pydub import AudioSegment
from io import BytesIO
import speech_recognition as sr
from PIL import Image
from googlesearch import search

# Load environment variables
load_dotenv(dotenv_path="pro.env")

# Environment Variables

os.environ["TELEGRAM_BOT_TOKEN"] = "7831386819:AAHC3li1_k_HkHtrg1pweho_Cd_7VQeBaCk"
os.environ["MONGO_URI"] = "mongodb+srv://deepthi:deepusiri@deepthi.bqzr7.mongodb.net/?retryWrites=true&w=majority&appName=Deepthi"
os.environ["GEMINI_API_KEY"] = "AIzaSyDyUtqy3nO5H1pLUuKQOWpOJ7wsZGsW1_I"
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize services
bot = telebot.TeleBot(BOT_TOKEN)
client = pymongo.MongoClient(MONGO_URI)
db = client["TelegramBotDB"]
users_col = db["users"]
chats_col = db["chats"]
files_col = db["files"]

# Configure Gemini AI model
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")  

# Sentiment analysis function
def analyze_sentiment(text):
    blob = TextBlob(text)
    sentiment = blob.sentiment.polarity
    if sentiment > 0:
        return "Positive 😊"
    elif sentiment < 0:
        return "Negative 😞"
    return "Neutral 😐"

# User Registration
@bot.message_handler(commands=['start'])
def start(message):
    user = users_col.find_one({"chat_id": message.chat.id})
    if user:
        bot.send_message(message.chat.id, "✨ Welcome back!")
    else:
        markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        contact_button = telebot.types.KeyboardButton(text="📞 Share Contact", request_contact=True)
        markup.add(contact_button)
        bot.send_message(message.chat.id, "👋 Welcome! Please share your contact to register.", reply_markup=markup)

@bot.message_handler(content_types=['contact'])
def register_contact(message):
    if message.contact:
        users_col.insert_one({
            "chat_id": message.chat.id,
            "first_name": message.contact.first_name,
            "username": message.chat.username,
            "phone": message.contact.phone_number,
            "registered_at": datetime.now(timezone.utc)
        })
        bot.send_message(message.chat.id, "✅ Registration successful!")

# Gemini-Powered Chat
@bot.message_handler(func=lambda message: True)
def chat(message):
    bot.send_chat_action(message.chat.id, 'typing')
    try:
        response = model.generate_content(message.text)
        sentiment = analyze_sentiment(response.text)
        reply = f"🗣 *Your Question:* {message.text}\n🤖 *AI Response:* {response.text}\n📊 *Sentiment:* {sentiment}"
        bot.send_message(message.chat.id, reply, parse_mode="Markdown")
        chats_col.insert_one({
            "chat_id": message.chat.id,
            "user_input": message.text,
            "bot_response": response.text,
            "sentiment": sentiment,
            "timestamp": datetime.now(timezone.utc)
        })
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Error: {str(e)}")

# Image/File Analysis
@bot.message_handler(content_types=['photo', 'document'])
def file_analysis(message):
    bot.send_message(message.chat.id, "✅ File received! Processing now...")
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    file_info = bot.get_file(file_id)
    file_path = file_info.file_path
    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

    try:
        response = requests.get(file_url)
        image = Image.open(BytesIO(response.content))
        gemini_response = model.generate_content(["Describe this image in detail.", image])

        sentiment = analyze_sentiment(gemini_response.text)

        bot.send_message(message.chat.id, f"🖼 *Image Analysis:* {gemini_response.text}\n📊 *Sentiment:* {sentiment}", parse_mode="Markdown")

        files_col.insert_one({
            "chat_id": message.chat.id,
            "file_url": file_url,
            "description": gemini_response.text,
            "sentiment": sentiment,
            "timestamp": datetime.now(timezone.utc)
        })
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Error: {str(e)}")
        print("❌ ERROR:", e)

# Voice Message Processing
@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    bot.send_chat_action(message.chat.id, 'typing')
    try:
        file_info = bot.get_file(message.voice.file_id)
        file_path = file_info.file_path
        voice_file = bot.download_file(file_path)
        audio = AudioSegment.from_file(BytesIO(voice_file), format="ogg")
        audio.export("voice_message.wav", format="wav")

        recognizer = sr.Recognizer()
        with sr.AudioFile("voice_message.wav") as source:
            audio_data = recognizer.record(source)
            transcribed_text = recognizer.recognize_google(audio_data)

        response = model.generate_content(transcribed_text)
        bot.send_message(message.chat.id, f"🔊 *You Said:* {transcribed_text}\n🤖 *AI Response:* {response.text}", parse_mode="Markdown")

        files_col.insert_one({
            "chat_id": message.chat.id,
            "transcribed_text": transcribed_text,
            "bot_response": response.text,
            "timestamp": datetime.now(timezone.utc)
        })
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Error: {str(e)}")

# Web Search
@bot.message_handler(commands=['websearch'])
def web_search(message):
    bot.send_message(message.chat.id, "🌍 Enter your query for web search:")
    bot.register_next_step_handler(message, perform_web_search)

def perform_web_search(message):
    bot.send_chat_action(message.chat.id, 'typing')
    query = message.text
    try:
        results = list(search(query, num_results=5))
        summary = model.generate_content(f"Summarize these search results: {results}")
        reply = f"🔍 *Search Query:* {query}\n📌 *Top Links:*\n" + "\n".join(results) + f"\n📝 *Summary:* {summary.text}"
        bot.send_message(message.chat.id, reply, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Error: {str(e)}")

# Run the bot
print("🤖 Bot is running...")
bot.polling(none_stop=True)
