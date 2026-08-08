import sqlite3
import time
import random
import threading
import telebot
from telebot.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

TOKEN = "8748584199:AAFWocSNskzFgttAwJFchnDvXx_E7p5IlGQ"
OWNER_ID = 6454550864

bot = telebot.TeleBot(TOKEN)

# ----------------- قاعدة البيانات (قائمة المتصدرين 24 ساعة) -----------------
def init_db():
    conn = sqlite3.connect("xo_game.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS leaderboard (
                    user_id INTEGER,
                    first_name TEXT,
                    wins INTEGER,
                    timestamp REAL
                )''')
    conn.commit()
    conn.close()

def add_win(user_id, first_name):
    conn = sqlite3.connect("xo_game.db")
    c = conn.cursor()
    now = time.time()
    c.execute("INSERT INTO leaderboard VALUES (?, ?, 1, ?)", (user_id, first_name, now))
    conn.commit()
    conn.close()

def get_leaderboard():
    conn = sqlite3.connect("xo_game.db")
    c = conn.cursor()
    cutoff = time.time() - (24 * 3600)
    c.execute("DELETE FROM leaderboard WHERE timestamp < ?", (cutoff,))
    conn.commit()
    
    c.execute("SELECT first_name, COUNT(*) as total_wins FROM leaderboard GROUP BY user_id ORDER BY total_wins DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    return rows

init_db()

# ----------------- الإعدادات والحالات -----------------
games = {}
user_settings = {}

DEFAULT_SYMBOLS = ("❌", "⭕")
SYMBOL_OPTIONS = [
    ("❌", "⭕"),
    ("🔴", "🔵"),
    ("🔥", "⚡"),
    ("👑", "💎"),
    ("👑", "💀"),
    ("🤍","🧡")
]

TIMER_OPTIONS = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60]

def get_user_config(user_id):
    if user_id not in user_settings:
        user_settings[user_id] = {'symbols': DEFAULT_SYMBOLS, 'timer': 0}
    return user_settings[user_id]

def get_start_markup():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎮 لعب ضد الذكاء الاصطناعي", callback_data="play"),
        InlineKeyboardButton("⚔️ تحدي صديق (في محادثة)", switch_inline_query=" "),
        InlineKeyboardButton("🎨 تخصيص الرموز", callback_data="custom_symbols"),
        InlineKeyboardButton("⏱️ ضبط المؤقت الزمني", callback_data="custom_timer"),
        InlineKeyboardButton("🏆 قائمة المتصدرين (24h)", callback_data="show_leaderboard"),
        InlineKeyboardButton("📢 قناة البوت", url="https://t.me/xx28z")
    )
    return markup

def create_board_markup(game_id, is_over=False):
    game = games[game_id]
    markup = InlineKeyboardMarkup(row_width=3)
    buttons = []
    for i in range(9):
        val = game['board'][i]
        text = val if val != " " else "   "
        buttons.append(InlineKeyboardButton(text, callback_data=f"move_{game_id}_{i}"))

    markup.add(*buttons)
    if is_over:
        if game['is_ai']:
            markup.add(
                InlineKeyboardButton(
                    "🔄 اللعب مرة أخرى (ضد الذكاء الاصطناعي)",
                    callback_data="play",
                )
            )
        else:
            markup.add(
                InlineKeyboardButton(
                    "⚔️ اللعب مرة أخرى معك",
                    switch_inline_query=" ",
                )
            )

    return markup

def check_winner(board):
    win_conditions = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),
        (0, 3, 6), (1, 4, 7), (2, 5, 8),
        (0, 4, 8), (2, 4, 6)
    ]
    for a, b, c in win_conditions:
        if board[a] == board[b] == board[c] and board[a] != " ":
            return board[a]
    if " " not in board:
        return "Draw"
    return None

def generate_rating(moves, total_time):
    if total_time < 10 and moves <= 5:
        return "أسطوري ⭐⭐⭐⭐⭐ (سرعة وذكاء خارق)"
    elif total_time < 20:
        return "ممتاز ⭐⭐⭐⭐ (تكتيك سريع)"
    elif total_time < 40:
        return "جيد جداً ⭐⭐⭐ (لعب متزن)"
    else:
        return "مقبول ⭐⭐ (يحتاج تركيز وسرعة أكبر)"

# ----------------- الذكاء الاصطناعي -----------------
def ai_best_move(board, ai_symbol, player_symbol, difficulty="medium"):
    empty_indices = [i for i, val in enumerate(board) if val == " "]
    if not empty_indices:
        return None
    if difficulty == "easy":
        return random.choice(empty_indices)
    elif difficulty == "medium":
        if random.random() < 0.5:
            return random.choice(empty_indices)

    for i in range(9):
        if board[i] == " ":
            board[i] = ai_symbol
            if check_winner(board) == ai_symbol:
                board[i] = " "
                return i
            board[i] = " "

    for i in range(9):
        if board[i] == " ":
            board[i] = player_symbol
            if check_winner(board) == player_symbol:
                board[i] = " "
                return i
            board[i] = " "

    if board[4] == " ":
        return 4

    return random.choice(empty_indices)

# ----------------- فاحص المؤقت -----------------
def timer_thread():
    while True:
        time.sleep(2)
        now = time.time()
        for game_id, game in list(games.items()):
            if game['status'] == 'playing' and game['timer_limit'] > 0:
                if now - game['last_move_time'] > game['timer_limit']:
                    game['status'] = 'ended'
                    time_limit = game['timer_limit']
                    
                    if game['turn'] == game['player1']['id']:
                        winner = game['player2']
                        loser = game['player1']
                    else:
                        winner = game['player1']
                        loser = game['player2']

                    if winner['id'] != 0:
                        add_win(winner['id'], winner['first_name'])

                    text = (
                        f"⏰ انتهاء الوقت!\n\n"
                        f"تأخر {loser['first_name']} في اللعب عن {time_limit} ثانية.\n\n"
                        f"النتيجة : فوز تلقائي\n"
                        f"الفائز : {winner['first_name']}\n"
                        f"حظ اوفر يا خسران {loser['first_name']} \n"
                        f'<a href="https://t.me/altaee_z">حقوق البوت محفوظة للمطور Ali Altaee ©2026</a>'
                    )
                    
                    try:
                        if game.get('inline_message_id'):
                            bot.edit_message_text(text=text, inline_message_id=game['inline_message_id'], reply_markup=create_board_markup(game_id, is_over=True), parse_mode="HTML", disable_web_page_preview=True)
                        elif game.get('chat_id') and game.get('message_id'):
                            bot.edit_message_text(text=text, chat_id=game['chat_id'], message_id=game['message_id'], reply_markup=create_board_markup(game_id, is_over=True), parse_mode="HTML", disable_web_page_preview=True)
                    except Exception:
                        pass

threading.Thread(target=timer_thread, daemon=True).start()

# ----------------- المحادثة الشخصية (/start) -----------------
@bot.message_handler(commands=['start'])
def start_cmd(message):
    text = (
        f"مرحباً بك {message.from_user.first_name} في بوت لعبة XO! 🎮\n"
        "يمكنك التحكم بالإعدادات أدناه أو بدء التحدي مباشرةً:\n"
        '<a href="https://t.me/altaee_z">حقوق البوت محفوظة للمطور Ali Altaee ©2026</a>'
    )
    bot.reply_to(
        message, 
        text, 
        parse_mode='HTML', 
        disable_web_page_preview=True, 
        reply_markup=get_start_markup()
    )

def show_leaderboard_msg(chat_id):
    rows = get_leaderboard()
    if not rows:
        text = "🏆 قائمة المتصدرين (خلال آخر 24 ساعة):\n\nلا يوجد فائزون حتى الآن!"
    else:
        text = "🏆 قائمة المتصدرين (خلال آخر 24 ساعة):\n\n"
        for idx, (name, wins) in enumerate(rows, 1):
            text += f"{idx}. {name} — {wins} 🥇\n"
    bot.send_message(chat_id, text, parse_mode="Markdown")

# ----------------- Inline Mode -----------------
@bot.inline_handler(func=lambda query: True)
def inline_query_handler(query):
    user_id = query.from_user.id
    config = get_user_config(user_id)
    
    game_id = f"{user_id}_{int(time.time())}"
    
    timer_text = f"{config['timer']} ثانية" if config['timer'] > 0 else "بدون مؤقت"
    symbols_text = f"{config['symbols'][0]} ضد {config['symbols'][1]}"
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⚔️ أنا موافق لنلعب XO (انضمام)", callback_data=f"join_{game_id}"))
    
    msg_content = InputTextMessageContent(
        f"🎮 تحدي XO جديد!\n\n"
        f"👤 المنشئ: [{query.from_user.first_name}](tg://user?id={user_id})\n"
        f"🎨 الرموز: {symbols_text}\n"
        f"⏱️ المؤقت: {timer_text}\n\n"
        f"بانتظار المنافس للضغط على الزر أدناه لبدء اللعبة...",
        parse_mode="Markdown"
    )
    
    article = InlineQueryResultArticle(
        id=game_id,
        title="ابدأ تحدي XO مع صديقك او في القناة",
        description=f"الرموز:  {symbols_text} | المؤقت: {timer_text}",
        input_message_content=msg_content,
        reply_markup=markup
    )
    
    games[game_id] = {
        'player1': {'id': user_id, 'first_name': query.from_user.first_name},
        'player2': None,
        'symbols': config['symbols'],
        'board': [" "] * 9,
        'turn': None,
        'start_time': None,
        'last_move_time': None,
        'timer_limit': config['timer'],
        'moves_count': 0,
        'status': 'waiting',
        'is_ai': False,
        'inline_message_id': None
    }
    
    bot.answer_inline_query(query.id, [article], cache_time=1)

# ----------------- الاستجابة للأزرار Callback Queries -----------------
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    data = call.data.split("_")
    action = data[0]

    if action == "custom":
        sub = data[1] if len(data) > 1 else ""
        if sub == "symbols":
            markup = InlineKeyboardMarkup(row_width=2)
            for x, o in SYMBOL_OPTIONS:
                markup.add(InlineKeyboardButton(f"{x} و {o}", callback_data=f"setsymbols_{x}_{o}"))
            markup.add(InlineKeyboardButton("🔄 إعادة للافتراضي (❌ و ⭕)", callback_data="setsymbols_❌_⭕"))
            markup.add(InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main"))
            bot.edit_message_text("اختر شكل الرموز المفضلة لديك:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
            bot.answer_callback_query(call.id)
            
        elif sub == "timer":
            markup = InlineKeyboardMarkup(row_width=2)
            for t in TIMER_OPTIONS:
                lbl = f"{t} ثانية" if t > 0 else "بدون مؤقت ♾️"
                markup.add(InlineKeyboardButton(lbl, callback_data=f"settimer_{t}"))
            markup.add(InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main"))
            bot.edit_message_text("حدد مهلة وقت الحركة لكل لاعب:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
            bot.answer_callback_query(call.id)

    elif action == "setsymbols":
        x_sym, o_sym = data[1], data[2]
        config = get_user_config(call.from_user.id)
        config['symbols'] = (x_sym, o_sym)
        bot.answer_callback_query(call.id, f"تم تغيير الرموز إلى {x_sym} و {o_sym}")
        text = f"تم ضبط الرموز بنجاح إلى: {x_sym} و {o_sym}\nاختر من القائمة أدناه:"
        bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_start_markup())

    elif action == "settimer":
        t_val = int(data[1])
        config = get_user_config(call.from_user.id)
        config['timer'] = t_val
        lbl = f"{t_val} ثانية" if t_val > 0 else "بدون مؤقت"
        bot.answer_callback_query(call.id, f"تم ضبط المؤقت: {lbl}")
        text = f"تم ضبط المؤقت بنجاح إلى: {lbl}\nاختر من القائمة أدناه:"
        bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_start_markup())

    elif action == "main":
        text = (
            f"مرحباً بك {call.from_user.first_name} في بوت لعبة XO! 🎮\n"
            "يمكنك التحكم بالإعدادات أدناه أو بدء التحدي مباشرةً:\n\n"
            '<a href="https://t.me/altaee_z">حقوق البوت محفوظة للمطور Ali Altaee ©2026</a>'
        )
        bot.edit_message_text(
            text=text, 
            chat_id=call.message.chat.id, 
            message_id=call.message.message_id, 
            reply_markup=get_start_markup(),
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        bot.answer_callback_query(call.id)

    elif action == "show":
        if call.message:
            show_leaderboard_msg(call.message.chat.id)
        bot.answer_callback_query(call.id)

    elif action == "play":
        config = get_user_config(call.from_user.id)
        game_id = f"ai_{call.from_user.id}_{int(time.time())}"
        
        games[game_id] = {
            'player1': {'id': call.from_user.id, 'first_name': call.from_user.first_name},
            'player2': {'id': 0, 'first_name': "الذكاء الاصطناعي 🤖"},
            'symbols': config['symbols'],
            'board': [" "] * 9,
            'turn': call.from_user.id,
            'start_time': time.time(),
            'last_move_time': time.time(),
            'timer_limit': config['timer'],
            'moves_count': 0,
            'status': 'playing',
            'is_ai': True,
            'chat_id': call.message.chat.id if call.message else None,
            'message_id': None
        }

        p1_sym, p2_sym = config['symbols']
        timer_lbl = f"{config['timer']} ثانية" if config['timer'] > 0 else "بدون مؤقت"
        text = (
            f"🎮 مباراة ضد الذكاء الاصطناعي!\n\n"
            f"<blockquote>باوع حبيبي اني ذكاء اصطناعي العب وياك اذا شفتك شغلت عقلك ودماغك اخليك تفوز واذا نفس وضعك سلملي 🤣</blockquote>\n\n"
            f"{p1_sym} أنت: {call.from_user.first_name}\n"
            f"{p2_sym} المنافس: الذكاء الاصطناعي 🤖\n"
            f"⏱️ المؤقت: {timer_lbl}\n\n"
            f"الدور الآن عندك ({p1_sym})"
        )
        if call.message:
            msg = bot.send_message(call.message.chat.id, text, reply_markup=create_board_markup(game_id), parse_mode="HTML")
            games[game_id]['message_id'] = msg.message_id
        bot.answer_callback_query(call.id)

    elif action == "join":
        game_id = f"{data[1]}_{data[2]}"
        if game_id not in games:
            bot.answer_callback_query(call.id, "هذه اللعبة منتهية أو غير صالحة.", show_alert=True)
            return
        
        game = games[game_id]
        if game['status'] != 'waiting':
            bot.answer_callback_query(call.id, "اللعبة بدأت بالفعل أو انتهت!", show_alert=True)
            return
            
        if call.from_user.id == game['player1']['id']:
            bot.answer_callback_query(call.id, "لا يمكنك تحدي نفسك!", show_alert=True)
            return

        game['player2'] = {'id': call.from_user.id, 'first_name': call.from_user.first_name}
        game['turn'] = game['player1']['id']
        game['start_time'] = time.time()
        game['last_move_time'] = time.time()
        game['status'] = 'playing'
        game['inline_message_id'] = call.inline_message_id

        p1_sym, p2_sym = game['symbols']
        timer_text = f"{game['timer_limit']} ثانية" if game['timer_limit'] > 0 else "بدون مؤقت"
        
        text = (
            f"🎮بدأت مباراة XO!\n\n"
            f"<blockquote>بسم الله الرحمن الرحيم</blockquote>\n"
            f"{p1_sym} اللاعب الأول: {game['player1']['first_name']}\n"
            f"{p2_sym} اللاعب الثاني: {game['player2']['first_name']}\n"
            f"⏱️ المؤقت للحركة: {timer_text}\n\n"
            f"يا صاحب اللعبة ابدي من يمك \n"
            f"الدور الآن عند: {game['player1']['first_name']} ({p1_sym})"
        )
        
        bot.edit_message_text(
            text=text,
            inline_message_id=call.inline_message_id,
            reply_markup=create_board_markup(game_id),
            parse_mode="HTML"
        )
        bot.answer_callback_query(call.id, "تم الانضمام للعبة! بالتوفيق.")

    elif action == "move":
        index = int(data[-1])
        game_id = "_".join(data[1:-1])

        if game_id not in games or games[game_id]["status"] != "playing":
            bot.answer_callback_query(call.id, "اللعبة غير نشطة.", show_alert=True)
            return

        game = games[game_id]
        user_id = call.from_user.id

        if user_id not in [game["player1"]["id"], game["player2"]["id"]]:
            bot.answer_callback_query(call.id, "أنت لست طرفاً في هذه اللعبة!", show_alert=True)
            return

        if user_id != game["turn"]:
            bot.answer_callback_query(call.id, "مو دورك انتظر صاحبك يلعب! 😌", show_alert=True)
            return

        if game["board"][index] != " ":
            bot.answer_callback_query(call.id, "هذا مختارينه قبلك شوفلك غيره 👻", show_alert=True)
            return

        p1_sym, p2_sym = game["symbols"]
        current_symbol = p1_sym if user_id == game["player1"]["id"] else p2_sym

        game["board"][index] = current_symbol
        game["moves_count"] += 1
        game["last_move_time"] = time.time()

        result = check_winner(game["board"])

        if result:
            process_game_over(game_id, result, call)
            return

        if game["is_ai"]:
            difficulty = game.get("difficulty", "medium")
            ai_idx = ai_best_move(game["board"], p2_sym, p1_sym, difficulty)
            if ai_idx is not None:
                game["board"][ai_idx] = p2_sym
                game["moves_count"] += 1
                game["last_move_time"] = time.time()

                ai_result = check_winner(game["board"])
                if ai_result:
                    process_game_over(game_id, ai_result, call)
                    return

            text = (
                f"🎮 مباراة ضد الذكاء الاصطناعي\n\n"
                f"{p1_sym} أنت: {game['player1']['first_name']}\n"
                f"{p2_sym} المنافس: الذكاء الاصطناعي 🤖\n\n"
                f"الدور الآن عندك ({p1_sym})"
            )
            bot.edit_message_text(
                text=text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=create_board_markup(game_id),
                parse_mode="Markdown",
            )
        else:
            game["turn"] = (
                game["player2"]["id"]
                if user_id == game["player1"]["id"]
                else game["player1"]["id"]
            )
            next_player = (
                game["player2"]
                if game["turn"] == game["player2"]["id"]
                else game["player1"]
            )
            next_symbol = (
                p2_sym if game["turn"] == game["player2"]["id"] else p1_sym
            )

            text = (
                f"🎮 **مباراة XO مستمرة**\n\n"
                f"{p1_sym} {game['player1']['first_name']} ضد {p2_sym}"
                f" {game['player2']['first_name']}\n\n"
                f"الدور الآن عند: {next_player['first_name']} ({next_symbol})"
            )

            bot.edit_message_text(
                text=text,
                inline_message_id=call.inline_message_id,
                reply_markup=create_board_markup(game_id),
                parse_mode="Markdown",
            )

        bot.answer_callback_query(call.id)

def process_game_over(game_id, result, call):
    game = games[game_id]
    game['status'] = 'ended'
    total_time = int(time.time() - game['start_time'])
    p1_sym, p2_sym = game['symbols']

    if result == 'Draw':
        text = (
            f"النتيجة : تعادل 🤝\n\n"
            f"مدة لعبكم هي: {total_time} ثانية\n"
            f"أداء متكافئ بين {game['player1']['first_name']} و"
            f" {game['player2']['first_name']}!"
        )
    else:
        winner = game['player1'] if result == p1_sym else game['player2']
        loser = game['player2'] if result == p1_sym else game['player1']
        rating = generate_rating(game['moves_count'], total_time)

        if winner['id'] != 0:
            add_win(winner['id'], winner['first_name'])

        text = (
            f"النتيجة : فوز 🏆\n"
            f"الفائز : {winner['first_name']}\n\n"
            f"أحسنت يا {winner['first_name']} لقد فزت بالتحدي تقييمك ({rating})\n\n"
            f"مدة لعبكم هي: {total_time} ثانية\n\n"
            f"حظ أوفر يا خسران {loser['first_name']}   😂"
        )

    markup = create_board_markup(game_id, is_over=True)

    if game['is_ai']:
        markup.add(
            InlineKeyboardButton(
                "🔙 العودة للقائمة الرئيسية", callback_data="main"
            )
        )
        bot.edit_message_text(
            text=text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
        )
    else:
        bot.edit_message_text(
            text=text, 
            inline_message_id=call.inline_message_id, 
            reply_markup=markup
        )

print("Bot is running...")
bot.infinity_polling()
