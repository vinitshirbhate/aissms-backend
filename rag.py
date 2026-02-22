import json
import logging
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
from openai import OpenAI

# --- LOGGING CONFIGURATION ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/app_debug.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("TelegramTrafficBot")

# ================= CONFIG =================
# ⚠️ REPLACE WITH NEW TOKEN FROM BOTFATHER (REVOKE OLD ONE FIRST)
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

OLLAMA_API_URL = "http://localhost:11434/api/generate"
INPUT_DATA_PATH = "data/input.json"
OUTPUT_DATA_PATH = "data/output.json"
MODEL_NAME = "google/gemini-2.0-flash-001" # Using Gemini via OpenRouter

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

# ================= LOAD CONTEXT (RAG) =================
def load_context():
    logger.info("📚 Loading RAG context from JSON files...")
    context_str = ""

    if os.path.exists(INPUT_DATA_PATH):
        try:
            with open(INPUT_DATA_PATH, "r", encoding="utf-8") as f:
                input_data = json.load(f)
                context_str += "INPUT TRAFFIC STATE DATA:\n"
                context_str += json.dumps(input_data, indent=2) + "\n\n"
            logger.debug(f"Input data loaded successfully. Entries: {len(input_data) if isinstance(input_data, list) else 1}")
        except Exception as e:
            logger.error(f"❌ Error reading input.json: {e}")

    if os.path.exists(OUTPUT_DATA_PATH):
        try:
            with open(OUTPUT_DATA_PATH, "r", encoding="utf-8") as f:
                output_data = json.load(f)
                context_str += "AI TRAFFIC DECISION DATA:\n"
                context_str += json.dumps(output_data, indent=2) + "\n\n"
            logger.debug(f"Output data loaded successfully. Entries: {len(output_data) if isinstance(output_data, list) else 1}")
        except Exception as e:
            logger.error(f"❌ Error reading output.json: {e}")

    logger.info(f"✅ RAG context loaded. Size: {len(context_str)} bytes.")
    return context_str


# ================= OPENROUTER QUERY =================
def query_openrouter(prompt, context):
    logger.info(f"🤖 Querying OpenRouter (Model: {MODEL_NAME})...")
    system_prompt = f"""
You are a Professional Smart City Traffic Intelligence Assistant for Pune.
Provide formal, concise, and data-driven responses.
Use the provided dataset to answer queries.

CRITICAL RULE — MISSING DATA:
If the user asks about a specific place, venue, or event that is NOT in the provided context, you MUST respond with a special trigger tag.
Format: [NEED_ANALYSIS: Actual Name of Venue]
Example: If the user asks about "Magarpatta City" and it's missing, you MUST return "[NEED_ANALYSIS: Magarpatta City]".
Do NOT add any other explanation or text.

CONTEXT:
{context}
"""

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            timeout=60
        )
        result = response.choices[0].message.content
        logger.info("✅ AI query successful.")
        return result
    except Exception as e:
        logger.error(f"❌ OpenRouter query failed: {str(e)}")
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
    user = update.effective_user
    logger.info(f"👋 User {user.username} (ID: {user.id}) started the bot.")
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

    input_data_raw = get_input_data()
    output_data_raw = get_output_data()
    
    # Handle list format for multiple entries
    input_data = input_data_raw[-1] if isinstance(input_data_raw, list) and input_data_raw else input_data_raw
    output_data = output_data_raw[-1] if isinstance(output_data_raw, list) and output_data_raw else output_data_raw

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
    user = update.effective_user
    
    if context.user_data.get("rag_mode"):
        logger.info(f"💬 CUSTOM QUERY from {user.username}: {user_text[:50]}...")
        await update.message.chat.send_action(action="typing")

        rag_context = load_context()
        ai_response = query_openrouter(user_text, rag_context)

        # CHECK IF BACKEND ANALYSIS IS NEEDED
        if "[NEED_ANALYSIS:" in ai_response:
            try:
                # Extract venue name: [NEED_ANALYSIS: VIT Pune] -> VIT Pune
                venue_to_analyze = ai_response.split("[NEED_ANALYSIS:")[1].split("]")[0].strip()
                logger.info(f"🔍 AI detected missing data for: {venue_to_analyze}. Triggering backend analysis...")
                
                # await update.message.reply_text(f"I don't have real-time data for '{venue_to_analyze}' yet. Scanning city sensors and live feeds for you... 📡")
                
                # Call FastAPI Backend
                backend_url = "http://localhost:8000/analyze"
                resp = requests.post(backend_url, json={"venue": venue_to_analyze}, timeout=45)
                
                if resp.status_code == 200:
                    logger.info("✅ Backend analysis successful. Re-querying AI with new data.")
                    # Reload context and query again
                    new_context = load_context()
                    ai_response = query_openrouter(user_text, new_context)
                else:
                    try:
                        error_detail = resp.json().get("detail", "Unknown backend error.")
                    except:
                        error_detail = "City sensors are currently unresponsive."
                    ai_response = f"⚠️ Analysis failed for '{venue_to_analyze}': {error_detail}"
            except Exception as e:
                logger.error(f"❌ Auto-analysis failed: {str(e)}")
                ai_response = f"System Error: Unable to complete live analysis for '{venue_to_analyze}'."

        await update.message.reply_text(ai_response, reply_markup=main_menu())
        context.user_data["rag_mode"] = False

        # Logging
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "user_id": user.id,
                "username": user.username,
                "user_query": user_text,
                "assistant_response": ai_response,
                "model": MODEL_NAME
            }
            with open("data/chat_log.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
            logger.debug("Chat interaction logged to chat_log.jsonl")
        except Exception as e:
            logger.error(f"❌ Chat logging error: {e}")
    else:
        logger.debug(f"Interpreted regular message from {user.username}: {user_text[:30]}")
        await update.message.reply_text(
            "Please use the control panel below to interact with the system.",
            reply_markup=main_menu()
        )


# ================= MAIN (STABLE + CTRL+C SAFE) =================
def main():
    logger.info("🚀 Launching Smart Traffic Professional Telegram Bot...")
    
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("❌ TELEGRAM_BOT_TOKEN is missing from .env!")
        return

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    try:
        logger.info("⚙️ Bot is polling for updates...")
        app.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        logger.warning("停止: Bot manually interrupted.")
    except Exception as e:
        logger.error(f"💥 Fatal Bot Error: {e}")
    finally:
        logger.info("💤 Bot shutdown complete.")


if __name__ == "__main__":
    main()