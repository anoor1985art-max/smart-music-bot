import os
import sys
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
import re
import time
import uuid
import threading
import requests
import telebot
from telebot import types
from flask import Flask
import yt_dlp
import imageio_ffmpeg

# ==========================================
# إعدادات البوت والتوكن
# ==========================================
# ضع توكن البوت الجديد هنا (من @BotFather)
BOT_TOKEN = "8807648885:AAHWZMRk3h5b70iH7CD890RAisuUd2WMsV8"
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

# ذاكرة تخزين مؤقت لعناوين الأغاني التي يتم البحث عنها لضمان دقة التحميل 100%
SONG_CACHE = {}

# ==========================================
# الترحيب والقوائم التفاعلية
# ==========================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        f"<b>🎧 مرحباً بك يا {message.from_user.first_name} في بوت الموسيقى والصوتيات الذكي!</b>\n\n"
        f"✨ أنا متخصص حصرياً في <b>عالم الأغاني، الموسيقى، والتعرف الصوتي (Shazam)</b>:\n\n"
        f"🎤 <b>1. التعرف الصوتي الفوري (Shazam):</b>\n"
        f"أرسل لي أي <b>مقطع صوتي (Voice Note)</b> أو <b>فيديو قصير</b> يحتوي على أغنية، وسأستمع إليه لأتعرف على اسم الأغنية والفنان وأجلب لك ملف الـ MP3 فوراً!\n\n"
        f"🔍 <b>2. البحث الفوري بالكلمات أو الاسم:</b>\n"
        f"اكتب لي اسم أي أغنية أو جملة من كلماتها (مثلاً: <i>«اغنية عبد الحليم جيتك من الشوق»</i> أو <i>«Shape of You»</i>)، وسأعرض لك قائمة بالنتائج لتختار منها وتستمع بضغطة زر!\n\n"
        f"🔗 <b>3. التحميل المباشر من الروابط:</b>\n"
        f"أرسل رابط أي أغنية أو مقطع صوتي (YouTube, SoundCloud, Spotify) وسأحوله لك إلى ملف MP3 عالي النقاء 🎼"
    )
    bot.reply_to(message, welcome_text)

# ==========================================
# 1. التعرف الصوتي (Shazam Recognition) لمقاطع الصوت والفيديو
# ==========================================
@bot.message_handler(content_types=['voice', 'audio', 'video', 'video_note'])
def handle_audio_recognition(message):
    status_msg = bot.reply_to(message, "⏳ <b>جاري الاستماع وتحليل البصمة الصوتية للتعرف على الأغنية...</b> 🎧")
    threading.Thread(
        target=process_audio_recognition,
        args=(message, status_msg)
    ).start()

def process_audio_recognition(message, status_msg):
    chat_id = message.chat.id
    unique_id = uuid.uuid4().hex[:8]
    file_path_local = None

    try:
        file_info = None
        if message.content_type == 'voice':
            file_info = bot.get_file(message.voice.file_id)
            ext = ".ogg"
        elif message.content_type == 'audio':
            file_info = bot.get_file(message.audio.file_id)
            ext = ".mp3"
        elif message.content_type == 'video_note':
            file_info = bot.get_file(message.video_note.file_id)
            ext = ".mp4"
        elif message.content_type == 'video':
            file_info = bot.get_file(message.video.file_id)
            ext = ".mp4"

        if not file_info:
            raise Exception("تعذر الوصول لملف الوسائط.")

        downloaded_file = bot.download_file(file_info.file_path)
        file_path_local = os.path.join(DOWNLOAD_DIR, f"{unique_id}_sample{ext}")
        with open(file_path_local, 'wb') as new_file:
            new_file.write(downloaded_file)

        # محاولة التعرف عبر خدمة AudD.io (Shazam API)
        url = 'https://api.audd.io/'
        data = {
            'return': 'apple_music,spotify',
            'api_token': 'test'  # أو استخدام البصمة المجانية
        }
        files = {'file': open(file_path_local, 'rb')}
        response = requests.post(url, data=data, files=files, timeout=20).json()
        files['file'].close()

        song_title = None
        song_artist = None

        if response and response.get('status') == 'success' and response.get('result'):
            res = response['result']
            song_title = res.get('title')
            song_artist = res.get('artist')
            album = res.get('album', '')

            info_text = (
                f"🎉 <b>تم التعرف على الأغنية بنجاح!</b>\n\n"
                f"📌 <b>العنوان:</b> {song_title}\n"
                f"👤 <b>الفنان:</b> {song_artist}\n"
                f"💿 <b>الألبوم:</b> {album}\n\n"
                f"⏳ <i>جاري الآن جلب ملف الـ MP3 النظيف للاستماع مباشرة...</i> 🎵"
            )
            bot.edit_message_text(info_text, chat_id=chat_id, message_id=status_msg.message_id)

            # البحث عن الـ MP3 وتحميله
            search_query = f"{song_title} {song_artist}"
            download_and_send_song(chat_id, search_query, status_msg, is_direct_query=True)
        else:
            bot.edit_message_text(
                "❌ <b>لم أتمكن من مطابقـة اللحن بدقة مع قاعدة بيانات Shazam الصوتية.</b>\n\n"
                "💡 <i>نصيحة: جرب كتابة اسم الأغنية أو أي كلمات تتذكرها منها هنا في المحادثة وسأبحث لك عنها فوراً!</i>",
                chat_id=chat_id,
                message_id=status_msg.message_id
            )

    except Exception as e:
        bot.edit_message_text(
            "❌ <b>حدث خطأ أثناء معالجة المقطع الصوتي.</b> يرجى المحاولة مرة أخرى أو البحث بكتابة الاسم.",
            chat_id=chat_id,
            message_id=status_msg.message_id
        )
    finally:
        if file_path_local and os.path.exists(file_path_local):
            try:
                os.remove(file_path_local)
            except Exception:
                pass

# ==========================================
# 2. البحث النصي والروابط (Search & URLs)
# ==========================================
@bot.message_handler(func=lambda message: message.text and not message.text.startswith('/'))
def handle_text_search(message):
    query = message.text.strip()
    status_msg = bot.reply_to(message, f"⏳ <b>جاري البحث عن:</b> <i>«{query}»</i>... 🔍")
    threading.Thread(
        target=process_text_search,
        args=(message, status_msg, query)
    ).start()

def process_text_search(message, status_msg, query):
    chat_id = message.chat.id
    try:
        # إذا كان رابطاً مباشراً نحمل فوراً
        if query.startswith('http://') or query.startswith('https://'):
            download_and_send_song(chat_id, query, status_msg, is_direct_query=True)
            return

        # البحث عبر محرك yt-dlp باستخدام عملاء الجوال لتخطي حماية يوتيوب
        ydl_opts = {
            'ffmpeg_location': FFMPEG_PATH,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'nocheckcertificate': True,
            'geo_bypass': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'mweb']
                }
            }
        }
        search_url = f"ytsearch5:{query}"
        results = []

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_url, download=False)
                if info and 'entries' in info:
                    for entry in info['entries']:
                        if entry:
                            title = entry.get('title', 'بدون عنوان')
                            url = entry.get('url') or entry.get('webpage_url')
                            duration = entry.get('duration')
                            dur_str = f"[{duration//60}:{duration%60:02d}]" if duration else ""
                            if url:
                                results.append({'title': title, 'url': url, 'dur': dur_str})
                                SONG_CACHE[url] = {'title': title, 'uploader': entry.get('uploader') or entry.get('channel') or 'YouTube Music'}
        except Exception as search_err:
            print(f"[WARNING] YouTube search blocked on cloud IP, trying SoundCloud: {search_err}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"scsearch5:{query}", download=False)
                if info and 'entries' in info:
                    for entry in info['entries']:
                        if entry:
                            title = entry.get('title', 'بدون عنوان')
                            url = entry.get('url') or entry.get('webpage_url')
                            duration = entry.get('duration')
                            dur_str = f"[{duration//60}:{duration%60:02d}]" if duration else ""
                            if url:
                                results.append({'title': title, 'url': url, 'dur': dur_str})
                                SONG_CACHE[url] = {'title': title, 'uploader': entry.get('uploader') or 'SoundCloud Music'}

        if not results:
            bot.edit_message_text("❌ لم أتمكن من العثور على نتائج مطابقة لهذا البحث. جرب كلمات أخرى.", chat_id=chat_id, message_id=status_msg.message_id)
            return

        markup = types.InlineKeyboardMarkup(row_width=2)
        for idx, res in enumerate(results, 1):
            btn_play = types.InlineKeyboardButton(
                f"▶️ {idx}. {res['title'][:30]} {res['dur']}",
                callback_data=f"play_music|{res['url']}"
            )
            btn_dl = types.InlineKeyboardButton(
                "⬇️ تحميل",
                callback_data=f"dl_file|{res['url']}"
            )
            markup.row(btn_play, btn_dl)

        bot.edit_message_text(
            f"🔎 <b>نتائج البحث عن:</b> <i>«{query}»</i>\n\n"
            f"👇 <i>اضغط على <b>اسم الأغنية (▶️)</b> للاستماع والمعاينة المباشرة، أو اضغط على <b>سهم التحميل (⬇️)</b> لحفظ الملف الأصلي في جهازك:</i>",
            chat_id=chat_id,
            message_id=status_msg.message_id,
            reply_markup=markup
        )

    except Exception as e:
        bot.edit_message_text("❌ حدث خطأ أثناء البحث، يرجى المحاولة لاحقاً.", chat_id=chat_id, message_id=status_msg.message_id)

def update_inline_button_progress(chat_id, message, clicked_data, new_text):
    if not message or not message.reply_markup or not message.reply_markup.keyboard:
        return
    try:
        updated_keyboard = []
        for row in message.reply_markup.keyboard:
            new_row = []
            for btn in row:
                if btn.callback_data == clicked_data:
                    new_row.append(types.InlineKeyboardButton(new_text, callback_data=btn.callback_data))
                else:
                    new_row.append(btn)
            updated_keyboard.append(new_row)
        bot.edit_message_reply_markup(chat_id, message.message_id, reply_markup=types.InlineKeyboardMarkup(keyboard=updated_keyboard))
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("play_music|") or call.data.startswith("dl_file|") or call.data.startswith("dl_doc|"))
def handle_music_selection(call):
    action, url = call.data.split("|", 1)
    is_document = (action == "dl_doc")
    
    bot.answer_callback_query(call.id, "⏳ جاري التحميل والتشغيل على البوت...", show_alert=False)
    
    # تحديث الزر نفسه بمؤشر تحميل مباشر دون إرسال رسائل أسفل الشاشة
    update_inline_button_progress(call.message.chat.id, call.message, call.data, "⏳ جاري التحميل ▓▓░░░ [1/3]")
    
    threading.Thread(
        target=download_and_send_song,
        args=(call.message.chat.id, url, None, False, is_document, call.message, call.data)
    ).start()

def download_and_send_song(chat_id, url_or_query, status_msg, is_direct_query=False, is_document=False, call_msg=None, clicked_data=None):
    unique_id = uuid.uuid4().hex[:8]
    output_template = os.path.join(DOWNLOAD_DIR, f"{unique_id}_%(title).50s.%(ext)s")

    ydl_opts = {
        'outtmpl': output_template,
        'ffmpeg_location': FFMPEG_PATH,
        'quiet': True,
        'no_warnings': True,
        'format': 'bestaudio/best',
        'socket_timeout': 7,
        'retries': 1,
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'mweb']
            }
        },
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    target_url = url_or_query if (url_or_query.startswith('http://') or url_or_query.startswith('https://')) else f"ytsearch1:{url_or_query}"

    extracted_title = url_or_query
    extracted_artist = "AI Music Bot"

    # 1. جلب العنوان بدقة متناهية من الذاكرة المؤقتة أو عبر oEmbed دون تحميل
    if url_or_query.startswith("http://") or url_or_query.startswith("https://"):
        if url_or_query in SONG_CACHE:
            extracted_title = SONG_CACHE[url_or_query].get('title', url_or_query)
            extracted_artist = SONG_CACHE[url_or_query].get('uploader', extracted_artist)
        else:
            try:
                # oEmbed السريع من يوتيوب يعمل دائماً وبدون حظر
                r = requests.get(f"https://www.youtube.com/oembed?url={url_or_query}&format=json", timeout=6)
                if r.status_code == 200:
                    data = r.json()
                    extracted_title = data.get('title', url_or_query)
                    extracted_artist = data.get('author_name', extracted_artist)
            except Exception as oemb_err:
                print(f"[INFO] oEmbed fallback: {oemb_err}")

            if extracted_title == url_or_query:
                try:
                    with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True, 'nocheckcertificate': True}) as ydl_meta:
                        meta = ydl_meta.extract_info(url_or_query, download=False)
                        if meta and meta.get('title'):
                            extracted_title = meta.get('title')
                            extracted_artist = meta.get('uploader') or extracted_artist
                except Exception as meta_err:
                    print(f"[INFO] Title extraction fallback: {meta_err}")

    try:
        downloaded_file = None
        song_title = extracted_title if extracted_title != url_or_query else "موسيقى MP3"
        artist_name = extracted_artist if extracted_artist != "AI Music Bot" else "Universal Music"

        if status_msg:
            try:
                bot.edit_message_text("⏳ <b>[1/3] جاري استخراج الصوت ومعالجة الملف...</b> ⬇️", chat_id=chat_id, message_id=status_msg.message_id)
            except Exception:
                pass
        elif call_msg and clicked_data:
            update_inline_button_progress(chat_id, call_msg, clicked_data, "⏳ جاري التجهيز ▓▓▓░░ [1/3]")

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target_url, download=True)
                if info:
                    if 'entries' in info and info['entries']:
                        info = info['entries'][0]
                    song_title = info.get('title', song_title)
                    artist_name = info.get('uploader') or info.get('artist') or artist_name
                    fname = ydl.prepare_filename(info)
                    fname = os.path.splitext(fname)[0] + '.mp3'
                    if os.path.exists(fname):
                        downloaded_file = fname
        except Exception as yt_err:
            print(f"[WARNING] yt-dlp mobile client failed ({yt_err}), trying fallback methods...")
            # 1. محاولة التحميل عبر السحاب السريع Cobalt API إذا كان رابط يوتيوب
            if "youtube.com" in target_url or "youtu.be" in target_url or target_url.startswith("http"):
                if status_msg:
                    try:
                        bot.edit_message_text("⚡ <b>[2/3] جاري التحميل فائق السرعة عبر السحاب (Cobalt API)...</b> ⬇️", chat_id=chat_id, message_id=status_msg.message_id)
                    except Exception:
                        pass
                elif call_msg and clicked_data:
                    update_inline_button_progress(chat_id, call_msg, clicked_data, "⚡ سحاب سريع ▓▓▓▓░ [2/3]")
                try:
                    cobalt_url = "https://api.cobalt.tools/api/json"
                    payload = {'url': target_url, 'downloadMode': 'audio', 'audioFormat': 'mp3'}
                    r = requests.post(cobalt_url, json=payload, headers={'Accept': 'application/json'}, timeout=15)
                    if r.status_code == 200 and r.json().get('url'):
                        audio_data = requests.get(r.json()['url'], timeout=30).content
                        fname = os.path.join(DOWNLOAD_DIR, f"{unique_id}_audio.mp3")
                        with open(fname, 'wb') as f:
                            f.write(audio_data)
                        downloaded_file = fname
                        if extracted_title != url_or_query:
                            song_title = extracted_title
                            artist_name = extracted_artist
                except Exception as cob_err:
                    print(f"[ERROR] Cobalt API fallback failed: {cob_err}")

            # 2. إذا فشل يوتيوب، نحاول البحث والتحميل من SoundCloud باستخدام العنوان الدقيق للأغنية
            if not downloaded_file:
                sc_query = url_or_query if not url_or_query.startswith("http") else extracted_title
                if sc_query.startswith("http") or not sc_query.strip():
                    sc_query = "موسيقى"
                print(f"[INFO] Searching SoundCloud for exact title: {sc_query}")
                if status_msg:
                    try:
                        bot.edit_message_text(f"🔄 <b>[3/3] جاري جلب الملف الأصلي من SoundCloud:</b>\n<i>«{extracted_title[:45]}»</i> 🎶", chat_id=chat_id, message_id=status_msg.message_id)
                    except Exception:
                        pass
                elif call_msg and clicked_data:
                    update_inline_button_progress(chat_id, call_msg, clicked_data, "🔄 جلب الأصل ▓▓▓▓▓ [3/3]")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"scsearch1:{sc_query}", download=True)
                    if info and 'entries' in info and info['entries']:
                        info = info['entries'][0]
                        song_title = info.get('title', song_title)
                        artist_name = info.get('uploader') or info.get('artist') or artist_name
                        fname = ydl.prepare_filename(info)
                        fname = os.path.splitext(fname)[0] + '.mp3'
                        if os.path.exists(fname):
                            downloaded_file = fname

        if not downloaded_file:
            for fname in os.listdir(DOWNLOAD_DIR):
                if fname.startswith(unique_id):
                    downloaded_file = os.path.join(DOWNLOAD_DIR, fname)
                    break

        if not downloaded_file or not os.path.exists(downloaded_file):
            raise Exception("تعذر استخراج الملف الصوتي بسبب قيود الشبكة السحابية.")

        if status_msg:
            try:
                bot.edit_message_text("📤 <b>اكتمل التجهيز! جاري إرسال المقطع الآن...</b> ⚡", chat_id=chat_id, message_id=status_msg.message_id)
            except Exception:
                pass

        with open(downloaded_file, 'rb') as f:
            if is_document:
                bot.send_document(
                    chat_id,
                    f,
                    caption="",
                    reply_to_message_id=None
                )
            else:
                # إرسال هادئ ونظيف جداً وبدون أي نص شرح أو زر أسفل المشغل كما طلب المستخدم
                bot.send_audio(
                    chat_id,
                    f,
                    caption="",
                    title=song_title,
                    performer=artist_name,
                    reply_to_message_id=None,
                    reply_markup=None
                )

        if status_msg:
            try:
                bot.delete_message(chat_id, status_msg.message_id)
            except Exception:
                pass
        elif call_msg and clicked_data:
            update_inline_button_progress(chat_id, call_msg, clicked_data, "✅ تم التشغيل")

    except Exception as e:
        if status_msg:
            try:
                bot.edit_message_text(f"❌ عذراً، تعذر جلب الملف الصوتي: {e}", chat_id=chat_id, message_id=status_msg.message_id)
            except Exception:
                pass
        elif call_msg and clicked_data:
            update_inline_button_progress(chat_id, call_msg, clicked_data, "❌ تعذر جلب المقطع")
        else:
            bot.send_message(chat_id, f"❌ عذراً، تعذر جلب المقطع الصوتي: {e}")
    finally:
        try:
            for fname in os.listdir(DOWNLOAD_DIR):
                if fname.startswith(unique_id):
                    os.remove(os.path.join(DOWNLOAD_DIR, fname))
        except Exception:
            pass

# ==========================================
# تشغيل خادم الويب للعمل 24/7 على Render وتشغيل البوت
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "<b>🤖 Smart Music & Audio Bot is Running Alive 24/7! (Status: Online 🟢)</b>", 200

def run_bot_polling():
    while True:
        try:
            if BOT_TOKEN == "PUT_YOUR_MUSIC_BOT_TOKEN_HERE":
                print("[WARNING] Please put your actual bot token in music_bot.py!")
                time.sleep(10)
                continue
            print("[INFO] Smart Music Bot is polling Telegram...")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"[ERROR] Music Bot polling restart due to: {e}")
            time.sleep(5)

# تشغيل البوت في مسار منفصل (Background Thread) ليعمل سواء عبر python مباشرة أو عبر gunicorn في السحابة
polling_thread = threading.Thread(target=run_bot_polling, daemon=True)
polling_thread.start()

if __name__ == "__main__":
    print("[INFO] Smart Music Bot is starting...")
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
