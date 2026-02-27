import json
from dotenv import load_dotenv
import requests
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.error import BadRequest

# ================= CONFIG =================
# ⚠️ REPLACE WITH NEW TOKEN FROM BOTFATHER (REVOKE OLD ONE FIRST)
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

OLLAMA_API_URL = "http://localhost:11434/api/generate"
INPUT_DATA_PATH = "data/input.json"
OUTPUT_DATA_PATH = "data/output.json"
MODEL_NAME = "gemma3"

# ================= LOAD CONTEXT (RAG) =================
def load_context():
    context_str = ""

    if os.path.exists(INPUT_DATA_PATH):
        try:
            with open(INPUT_DATA_PATH, "r", encoding="utf-8") as f:
                input_data = json.load(f)
                context_str += "INPUT TRAFFIC STATE DATA:\n"
                context_str += json.dumps(input_data, indent=2) + "\n\n"
        except Exception as e:
            print("Error reading input.json:", e)

    if os.path.exists(OUTPUT_DATA_PATH):
        try:
            with open(OUTPUT_DATA_PATH, "r", encoding="utf-8") as f:
                output_data = json.load(f)
                context_str += "AI TRAFFIC DECISION DATA:\n"
                context_str += json.dumps(output_data, indent=2) + "\n\n"
        except Exception as e:
            print("Error reading output.json:", e)

    return context_str


# ================= OLLAMA QUERY =================
def query_ollama(prompt, context):
    system_prompt = f"""
You are a Professional Smart City Traffic Intelligence Assistant for Pune.
Provide formal, concise, and data-driven responses.
Use ONLY the provided dataset.
If information is unavailable, respond: "Data not available in current dataset."

CONTEXT:
{context}
"""

    full_prompt = f"{system_prompt}\n\nUSER QUERY: {prompt}\n\nRESPONSE:"

    payload = {
        "model": MODEL_NAME,
        "prompt": full_prompt,
        "stream": False
    }

    try:
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=120)
        response.raise_for_status()
        return response.json().get("response", "No response available from AI engine.")
    except Exception as e:
        return f"System Error: Unable to contact AI engine.\nDetails: {str(e)}"


# ================= DATA HELPERS =================
def get_input_data():
    if os.path.exists(INPUT_DATA_PATH):
        with open(INPUT_DATA_PATH, "r") as f:
            return json.load(f)
    return {}

def get_output_data():
    if os.path.exists(OUTPUT_DATA_PATH):
        with open(OUTPUT_DATA_PATH, "r") as f:
            return json.load(f)
    return {}


# ================= SAFE EDIT (FIXES MESSAGE NOT MODIFIED ERROR) =================
async def safe_edit(query, text, reply_markup=None):
    try:
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup
        )
    except BadRequest as e:
        # Ignore harmless Telegram error
        if "Message is not modified" in str(e):
            pass
        else:
            # Fallback: send new message if edit fails
            await query.message.reply_text(text, reply_markup=reply_markup)


# ================= PROFESSIONAL MENUS =================
def main_menu():
    keyboard = [
        [InlineKeyboardButton("Traffic Overview", callback_data="traffic")],
        [InlineKeyboardButton("AI Decision Intelligence", callback_data="ai")],
        [InlineKeyboardButton("System Status", callback_data="status")],
        [InlineKeyboardButton("Ask AI (Custom Query)", callback_data="ask")]
    ]
    return InlineKeyboardMarkup(keyboard)


def traffic_menu():
    keyboard = [
        [InlineKeyboardButton("Current Traffic Severity", callback_data="severity")],
        [InlineKeyboardButton("Weather Condition", callback_data="weather")],
        [InlineKeyboardButton("Venue Monitoring Status", callback_data="venue")],
        [InlineKeyboardButton("Back to Main Menu", callback_data="main")]
    ]
    return InlineKeyboardMarkup(keyboard)


def ai_menu():
    keyboard = [
        [InlineKeyboardButton("Priority Level", callback_data="priority")],
        [InlineKeyboardButton("Actions Executed", callback_data="actions")],
        [InlineKeyboardButton("Back to Main Menu", callback_data="main")]
    ]
    return InlineKeyboardMarkup(keyboard)


# ================= START COMMAND =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "SMART TRAFFIC MANAGEMENT SYSTEM\n"
        "City: Pune\n"
        "Mode: AI Traffic Intelligence (RAG Enabled)\n\n"
        "Select a module from the control panel below."
    )
    await update.message.reply_text(text, reply_markup=main_menu())


# ================= BUTTON HANDLER =================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer(cache_time=2)

    input_data = get_input_data()
    output_data = get_output_data()

    if query.data == "main":
        await safe_edit(
            query,
            "Main Control Panel - Select Module:",
            reply_markup=main_menu()
        )

    elif query.data == "traffic":
        await safe_edit(
            query,
            "Traffic Overview Module",
            reply_markup=traffic_menu()
        )

    elif query.data == "ai":
        await safe_edit(
            query,
            "AI Decision Intelligence Module",
            reply_markup=ai_menu()
        )

    elif query.data == "status":
        status_msg = (
            "SYSTEM STATUS\n"
            "AI Engine: Connected (Ollama)\n"
            "Data Pipeline: Active\n"
            "Monitoring Network: Operational\n"
            "City Grid: Pune Smart Traffic System"
        )
        await safe_edit(query, status_msg, reply_markup=main_menu())

    elif query.data == "severity":
        severity = input_data.get("traffic_prediction", {}).get("severity", "Not Available")
        await safe_edit(
            query,
            f"Current Traffic Severity: {severity}",
            reply_markup=traffic_menu()
        )

    elif query.data == "weather":
        weather = input_data.get("weather", {}).get("condition", "Not Available")
        await safe_edit(
            query,
            f"Weather Condition: {weather}",
            reply_markup=traffic_menu()
        )

    elif query.data == "venue":
        venue = input_data.get("venue", {}).get("name", "Not Available")
        await safe_edit(
            query,
            f"Monitored Venue: {venue}",
            reply_markup=traffic_menu()
        )

    elif query.data == "priority":
        priority = output_data.get("priority_level", "Not Available")
        await safe_edit(
            query,
            f"AI Priority Level: {priority}",
            reply_markup=ai_menu()
        )

    elif query.data == "actions":
        actions = output_data.get("traffic_management_actions", [])
        await safe_edit(
            query,
            f"Total AI Actions Executed: {len(actions)}",
            reply_markup=ai_menu()
        )

    elif query.data == "ask":
        context.user_data["rag_mode"] = True
        await safe_edit(
            query,
            "AI Query Mode Activated.\nPlease enter your traffic-related question."
        )


# ================= RAG CHAT HANDLER =================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    if context.user_data.get("rag_mode"):
        await update.message.chat.send_action(action="typing")

        rag_context = load_context()
        ai_response = query_ollama(user_text, rag_context)

        await update.message.reply_text(ai_response, reply_markup=main_menu())
        context.user_data["rag_mode"] = False

        # Logging
        try:
            os.makedirs("data", exist_ok=True)
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "user_query": user_text,
                "assistant_response": ai_response,
                "model": MODEL_NAME
            }
            with open("data/chat_log.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            print("Logging Error:", e)
    else:
        await update.message.reply_text(
            "Please use the control panel below to interact with the system.",
            reply_markup=main_menu()
        )


# ================= MAIN (STABLE + CTRL+C SAFE) =================
def main():
    print("Launching Smart Traffic Professional Telegram Bot...")
    print("Press Ctrl + C to stop the bot.\n")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    try:
        app.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        print("\nBot stopped manually using Ctrl + C.")
    except Exception as e:
        print("Fatal Error:", e)
    finally:
        print("Bot shutdown complete.")


if __name__ == "__main__":
    main()