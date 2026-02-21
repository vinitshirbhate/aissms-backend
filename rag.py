import streamlit as st
import json
import requests
import os
from datetime import datetime

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Pune Smart Traffic RAG Agent",
    page_icon="🤖",
    layout="wide",
)

# --- STYLING ---
st.markdown("""
<style>
    .stApp {
        background-color: #0e1117;
        color: #ffffff;
    }
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #00d4ff;
        margin-bottom: 20px;
        text-align: center;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #a0aec0;
        margin-bottom: 30px;
        text-align: center;
    }
    .chat-container {
        border-radius: 10px;
        background-color: #1a202c;
        padding: 20px;
        margin-bottom: 20px;
        border: 1px solid #2d3748;
    }
    .data-card {
        background-color: #2d3748;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 10px;
        border-left: 5px solid #00d4ff;
    }
</style>
""", unsafe_allow_html=True)

# --- CONSTANTS ---
OLLAMA_API_URL = "http://localhost:11434/api/generate"
INPUT_DATA_PATH = "data/input.json"
OUTPUT_DATA_PATH = "data/output.json"

# --- HELPER FUNCTIONS ---
def load_context():
    context_str = ""
    
    if os.path.exists(INPUT_DATA_PATH):
        with open(INPUT_DATA_PATH, "r", encoding="utf-8") as f:
            input_data = json.load(f)
            context_str += "INPUT TRAFFIC STATE DATA:\n" + json.dumps(input_data, indent=2) + "\n\n"
    
    if os.path.exists(OUTPUT_DATA_PATH):
        with open(OUTPUT_DATA_PATH, "r", encoding="utf-8") as f:
            output_data = json.load(f)
            context_str += "AI TRAFFIC DECISION DATA:\n" + json.dumps(output_data, indent=2) + "\n\n"
            
    return context_str

def query_ollama(prompt, context, model_name):
    system_prompt = f"""
You are the Pune Smart City Traffic RAG Agent. You have access to real-time traffic state data and AI-generated decisions for Pune city.
Your goal is to answer user queries accurately based ONLY on the provided context.
If the information is not in the context, be honest and say you don't have that specific data, but offer related insights from the data you DO have.

CONTEXT:
{context}
"""
    
    full_prompt = f"{system_prompt}\n\nUSER QUERY: {prompt}\n\nRESPONSE:"
    
    payload = {
        "model": model_name,
        "prompt": full_prompt,
        "stream": False
    }
    
    try:
        # Increased timeout to 120s for larger models or slower hardware
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=120)
        response.raise_for_status()
        return response.json().get("response", "No response received.")
    except Exception as e:
        return f"Error contacting Ollama: {str(e)}"

# --- UI LAYOUT ---
st.markdown('<div class="main-header">🏙️ Pune Smart Traffic RAG Agent</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">AI-Powered Insights for City Traffic Management</div>', unsafe_allow_html=True)

col1, col2 = st.columns([1, 2])

with col1:
    st.header("📊 Knowledge Base")
    st.write("Current dataset used for retrieval:")
    
    if os.path.exists(INPUT_DATA_PATH):
        with open(INPUT_DATA_PATH, "r") as f:
            data = json.load(f)
            st.markdown(f"""
            <div class="data-card">
                <strong>📍 Venue:</strong> {data.get('venue', {}).get('name', 'N/A')}<br>
                <strong>🚦 Severity:</strong> {data.get('traffic_prediction', {}).get('severity', 'N/A')}<br>
                <strong>☁️ Weather:</strong> {data.get('weather', {}).get('condition', 'N/A')}
            </div>
            """, unsafe_allow_html=True)
            
    if os.path.exists(OUTPUT_DATA_PATH):
        with open(OUTPUT_DATA_PATH, "r") as f:
            data = json.load(f)
            st.markdown(f"""
            <div class="data-card">
                <strong>💡 Priority:</strong> {data.get('priority_level', 'N/A').upper()}<br>
                <strong>🛑 Decisions:</strong> {len(data.get('traffic_management_actions', []))} actions taken
            </div>
            """, unsafe_allow_html=True)

    st.divider()
    st.subheader("⚙️ Settings")
    model_name = st.text_input("Ollama Model", value="gemma3")
    st.info("Ensure Ollama is running locally with the specified model loaded.")

with col2:
    st.header("💬 Ask the Agent")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    if prompt := st.chat_input("What would you like to know about Pune traffic?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing data..."):
                context = load_context()
                # Use the model name from the sidebar/settings input
                response = query_ollama(prompt, context, model_name)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})

                # --- LOG EVENT ---
                try:
                    chat_log_entry = {
                        "timestamp": datetime.now().isoformat(),
                        "user_query": prompt,
                        "assistant_response": response,
                        "model_used": model_name
                    }
                    os.makedirs("data", exist_ok=True)
                    with open("data/chat_log.jsonl", "a", encoding="utf-8") as f:
                        f.write(json.dumps(chat_log_entry) + "\n")
                except Exception as log_error:
                    print(f"Error logging chat: {str(log_error)}")

# --- FOOTER ---
st.sidebar.markdown("---")
st.sidebar.caption("Smart City Hackathon 2026")
st.sidebar.caption("Powered by Ollama & Streamlit")
