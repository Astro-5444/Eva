# Standard library imports
import asyncio
import base64
import builtins
import json
import logging
import math
import os
import random
import re
import shutil
import signal
import string
import subprocess
import sys
import threading
import time
import ctypes
import tkinter as tk
import webbrowser
from collections import Counter
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email.mime.text import MIMEText
from pathlib import Path
from tkinter import ttk, messagebox
from tkinter import PhotoImage



# Third-party imports
import chromadb
import pytz
import requests
import webview
from chromadb.utils import embedding_functions
from dateutil import parser
from flask import Flask, render_template, render_template_string
from flask_socketio import SocketIO
from flask import jsonify
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes


# ===================================================================================== CONFIG GUI ================================================================================
CONFIG_FILE = Path("static/config.json")
BOT_TOKEN = "###############################"  # Replace with your bot token

api_data = [
    {"label": "MISTRAL API KEY", "url": "https://medium.com/@abdulrhmanhimk/how-to-get-mistral-api-535765cae4ec"},
    {"label": "BRAVE API KEY", "url": "https://medium.com/@abdulrhmanhimk/how-to-get-a-brave-search-api-key-e89251c0f59b"},
    {"label": "User name"},
    {"label": "Extra details (optional)", "multiline": True}  # Added multiline flag
]

model_options = [
    "codestral-latest",
    "mistral-large-latest",
    "mistral-medium-latest",
    "mistral-small-latest"
]

# ===== GLOBAL HELPER FUNCTIONS =====
def ensure_config_exists():
    """Ensure config file exists with empty structure"""
    if not CONFIG_FILE.exists():
        # Create directory if it doesn't exist
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # Create empty config file
        empty_config = {
            "MISTRAL API KEY": "",
            "BRAVE API KEY": "",
            "User name": "",
            "Selected Model": "",
            "Extra details (optional)": ""
        }

        with open(CONFIG_FILE, "w") as f:
            json.dump(empty_config, f, indent=4)

def load_config():
    """Safely load configuration, creating empty one if needed"""
    ensure_config_exists()
    
    try:
        with open(CONFIG_FILE, "r") as f:
            content = f.read().strip()
            if content:
                return json.loads(content)
            else:
                return {}
    except (json.JSONDecodeError, FileNotFoundError):
        # If corrupted, create fresh empty config
        
        empty_config = {
            "MISTRAL API KEY": "",
            "BRAVE API KEY": "",
            "User name": "",
            "Selected Model": "",
            "Extra details (optional)": ""
        }

        with open(CONFIG_FILE, "w") as f:
            json.dump(empty_config, f, indent=4)
        return empty_config

def save_config_data(data):
    """Save configuration data to file"""
    ensure_config_exists()
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)

def run_gui_setup():
    # Global variables for bot management
    app = None
    bot_thread = None
    stop_event = threading.Event()
    

    
    # ===== FUNCTIONS =====
    def open_link(url):
        webbrowser.open_new(url)

    def generate_verification_code():
        letters = ''.join(random.choices(string.ascii_uppercase, k=4))
        digits = ''.join(random.choices(string.digits, k=4))
        return letters + digits

    def save_config():
        config_data = load_config()  # Load existing config
        missing_fields = []

        # List of optional fields
        optional = ["Extra details (optional)"]

        for api in api_data:
            if api["label"] in entries:
                widget = entries[api["label"]]
                if isinstance(widget, tk.Text):
                    value = widget.get("1.0", tk.END).strip()
                else:
                    value = widget.get().strip()
            else:
                value = ""
            
            # Only mark as missing if it's not in the optional list
            if not value and api["label"] not in optional:
                missing_fields.append(api["label"])

            config_data[api["label"]] = value

        selected_model = model_var.get()
        if not selected_model:
            missing_fields.append("Mistral model Selection")
        else:
            config_data["Selected Model"] = selected_model

        if missing_fields:
            messagebox.showerror(
                "Missing Fields",
                f"Please fill in the following fields:\n- " + "\n- ".join(missing_fields)
            )
            return False

        save_config_data(config_data)
        return True


    def save_and_run():
        if save_config():
            stop_bot()
            root.destroy()

    def run_without_saving():
        stop_bot()
        root.destroy()

    def check_chat_id():
        try:
            if not root.winfo_exists():
                return
        except tk.TclError:
            return
        
        config_data = load_config()
        if "chat_id" in config_data:
            chat_id_status.config(text=f"Live Status: Linked (Chat ID: {config_data['chat_id']})")
        else:
            chat_id_status.config(text="Live Status: Not linked")
        
        try:
            root.after(1000, check_chat_id)
        except tk.TclError:
            pass

    # ===== TELEGRAM BOT =====
    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_text = update.message.text.strip()
        if user_text == verification_code:
            chat_id = update.message.chat_id
            
            # Load existing config and add chat_id
            config_data = load_config()
            config_data["chat_id"] = chat_id
            save_config_data(config_data)
            
            await update.message.reply_text("✅ Code verified! You are now linked.")
        else:
            await update.message.reply_text("❌ Invalid activation code.")

    def run_bot_in_thread():
        """Run the bot in a separate thread with its own event loop"""
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Create application with shorter timeout settings
            local_app = (
                ApplicationBuilder()
                .token(BOT_TOKEN)
                .connect_timeout(10)
                .read_timeout(10)
                .build()
            )
            local_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            
            print("🤖 Telegram verification bot is running...")
            
            # Simple bot runner
            async def run_bot():
                try:
                    # Initialize and start
                    await local_app.initialize()
                    await local_app.start()
                    
                    # Start polling in the background
                    await local_app.updater.start_polling(drop_pending_updates=True)
                    
                    # Keep running until stop event
                    while not stop_event.is_set():
                        await asyncio.sleep(0.5)
                    
                    # Quick shutdown
                    await local_app.updater.stop()
                    await local_app.stop()
                    await local_app.shutdown()
                    
                except Exception as e:
                    if not stop_event.is_set():
                        print(f"Bot error: {e}")
                finally:
                    # Force cleanup
                    try:
                        if hasattr(local_app, 'updater') and local_app.updater:
                            await local_app.updater.stop()
                    except:
                        pass
            
            # Run the bot
            loop.run_until_complete(run_bot())
            
        except Exception as e:
            if not stop_event.is_set():
                print(f"Bot thread error: {e}")
        finally:
            try:
                # Clean up pending tasks
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                
                loop.close()
            except:
                pass

    def stop_bot():
        """Stop the bot gracefully"""
        nonlocal bot_thread
        
        if bot_thread and bot_thread.is_alive():
            print("🛑 Stopping Telegram verification bot...")
            stop_event.set()
            
            # Give the thread time to stop gracefully
            bot_thread.join(timeout=5)
            
            if bot_thread.is_alive():
                print("⚠️ Bot thread still running, but continuing anyway...")
                # Don't worry about it - the daemon thread will be cleaned up when the process exits
            else:
                print("✅ Bot stopped successfully")

    def on_closing():
        """Handle window closing event"""
        stop_bot()
        try:
            root.destroy()
        except:
            pass



    # ===== MAIN GUI =====
    # Load saved configuration (creates empty one if doesn't exist)
    saved_data = load_config()

    root = tk.Tk()
    root.title("")

    root.geometry("554x500")  # Increased height to accommodate text area
    root.resizable(False, False)  # Disable resizing
    root.configure(bg="#f5f5f5")  # Light background

    # Handle window closing
    root.protocol("WM_DELETE_WINDOW", on_closing)

    # ----- Styling -----
    style = ttk.Style()
    style.configure("TLabel", font=("Segoe UI", 11), background="#f5f5f5")
    style.configure("TButton", font=("Segoe UI", 10), padding=5)
    style.configure("TEntry", padding=5)
    style.configure("TCombobox", padding=5)

    # ----- Title -----
    title_label = ttk.Label(root, text="Configuration", font=("Segoe UI", 16, "bold"))
    title_label.grid(row=0, column=0, columnspan=3, pady=(20, 10))

    # ----- API Key Inputs -----
    entries = {}
    current_row = 1
    
    for idx, api in enumerate(api_data):
        label = ttk.Label(root, text=api["label"])
        label.grid(row=current_row, column=0, padx=15, pady=8, sticky="nw")  # Changed to "nw" for top alignment

        # Check if this should be a multiline text area
        if api.get("multiline", False):
            # Create a frame to hold the text widget and scrollbar
            text_frame = tk.Frame(root, bg="#f5f5f5")
            text_frame.grid(row=current_row, column=1, padx=10, pady=8, sticky="ew")
            
            # Create text widget with scrollbar
            text_widget = tk.Text(text_frame, width=35, height=4, wrap=tk.WORD, 
                                font=("Segoe UI", 10), relief="solid", borderwidth=1)
            scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=text_widget.yview)
            text_widget.configure(yscrollcommand=scrollbar.set)
            
            text_widget.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")
            
            # Load saved value if exists
            if api["label"] in saved_data:
                text_widget.insert("1.0", saved_data[api["label"]])
            
            entries[api["label"]] = text_widget
            
            # Add placeholder text
            if api["label"] not in saved_data or not saved_data[api["label"]]:
                placeholder = ""
                text_widget.insert("1.0", placeholder)
                text_widget.config(fg="gray")
                
                def on_focus_in(event, widget=text_widget, placeholder_text=placeholder):
                    if widget.get("1.0", "end-1c") == placeholder_text:
                        widget.delete("1.0", tk.END)
                        widget.config(fg="black")
                
                def on_focus_out(event, widget=text_widget, placeholder_text=placeholder):
                    if not widget.get("1.0", "end-1c").strip():
                        widget.insert("1.0", placeholder_text)
                        widget.config(fg="gray")
                
                text_widget.bind("<FocusIn>", on_focus_in)
                text_widget.bind("<FocusOut>", on_focus_out)
        else:
            # Regular single-line entry
            entry = ttk.Entry(root, width=45)
            entry.grid(row=current_row, column=1, padx=10, pady=8)

            # Load saved value if exists
            if api["label"] in saved_data:
                entry.insert(0, saved_data[api["label"]])

            entries[api["label"]] = entry

        # Add guide button if URL exists
        if "url" in api and api["url"]:
            guide_button = ttk.Button(root, text="?", width=3, command=lambda url=api["url"]: open_link(url))
            guide_button.grid(row=current_row, column=2, padx=5, pady=5, sticky="n")  # Changed to "n" for top alignment
        
        current_row += 1

    # ----- Model Selection -----
    model_label = ttk.Label(root, text="Select Model")
    model_label.grid(row=current_row, column=0, padx=15, pady=10, sticky="w")

    model_var = tk.StringVar()
    model_dropdown = ttk.Combobox(root, textvariable=model_var, values=model_options, state="readonly", width=43)
    model_dropdown.grid(row=current_row, column=1, padx=10, pady=10)

    # Load saved model
    if "Selected Model" in saved_data:
        model_var.set(saved_data["Selected Model"])

    current_row += 1

    # ----- Verification -----
    verification_code = generate_verification_code()
    verification_label = ttk.Label(root, text=f"Send this code to the telegram bot: {verification_code}", font=("Segoe UI", 10, "bold"))
    verification_label.grid(row=current_row, column=0, columnspan=3, pady=(15, 5))

    current_row += 1

    chat_id_status = ttk.Label(root, text="Live Status: Not linked", font=("Segoe UI", 10))
    chat_id_status.grid(row=current_row, column=0, columnspan=3, pady=(0, 15))

    current_row += 1

    # ----- Buttons -----
    button_frame = ttk.Frame(root)
    button_frame.grid(row=current_row, column=0, columnspan=3, pady=20)

    save_button = ttk.Button(button_frame, text="💾 Save & Continue", command=save_and_run)
    save_button.grid(row=0, column=0, padx=15)

    run_button = ttk.Button(button_frame, text="▶ Run Without Saving", command=run_without_saving)
    run_button.grid(row=0, column=1, padx=15)

    # ===== START BOT THREAD =====
    bot_thread = threading.Thread(target=run_bot_in_thread, daemon=True)
    bot_thread.start()

    # Start checking chat ID status
    check_chat_id()

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\n🛑 Received interrupt signal...")
        stop_bot()
        try:
            root.quit()
        except:
            pass
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)

    root.mainloop()

    return load_config() 
# ===================================================================================== CONFIG GUI ================================================================================

# ========================================================== Custom print function for clean terminal output ==========================================================
def clean_print(message, message_type="INFO"):
    """
    Custom print function that formats output with clear separators
    message_type can be: "INPUT", "OUTPUT", "SYSTEM", "ERROR", "SUCCESS"
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    # Define colors and separators for different message types
    separators = {
        "INPUT": "=" * 60,
        "OUTPUT": "-" * 60,
        "SYSTEM": "~" * 60,
        "ERROR": "!" * 60,
        "SUCCESS": "*" * 60
    }
    
    # Define emojis for different message types
    emojis = {
        "INPUT": "👤",
        "OUTPUT": "🤖",
        "SYSTEM": "⚙️",
        "ERROR": "❌",
        "SUCCESS": "✅"
    }
    
    separator = separators.get(message_type, "-" * 60)
    emoji = emojis.get(message_type, "ℹ️")
    
    # Print the formatted message using original print
    original_print(f"\n{separator}")
    original_print(f"{emoji} [{timestamp}] {message_type}: {message}")
    original_print(f"{separator}\n")

def clear_terminal():
    """Clear the terminal screen"""
    os.system('cls' if os.name == 'nt' else 'clear')
    clean_print("Terminal cleared", "SYSTEM")

def print_separator():
    """Print a simple separator line"""
    original_print("\n" + "=" * 80 + "\n")

# Store original print function for backup
original_print = builtins.print
#  Serving Flask app Debug mode: off
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
# ========================================================== Custom print function for clean terminal output ==========================================================

# === CONFIG Data ===

# === First time? ===
file_path = Path("eva_memory.json")

today_date = datetime.now().strftime("%Y-%m-%d")

def Config_get_data():
    global MISTRAL_API_KEY, BRAVE_API_KEY, MODEL, current_chat_id, name, EVA_PROMPT, user_information
    
    config_data = load_config()
    MISTRAL_API_KEY = config_data["MISTRAL API KEY"]
    BRAVE_API_KEY = config_data["BRAVE API KEY"]
    user_information = config_data.get("Extra details (optional)", "")
    MODEL = config_data["Selected Model"]
    name = config_data["User name"]

    if "chat_id" in config_data:
        current_chat_id = config_data["chat_id"]
    else:
        current_chat_id = None
        print("No chat_id found — please run setup first.")


    if file_path.exists():
        first_time = (
            f"This is not your first interaction with {name}. "
            "Be warm and helpful but don't pretend to know them already. "
            "Continue building familiarity naturally over time through real conversations. "
            
        )
    else:
        first_time = (
            f"This is your very first interaction with {name}. "
            "Greet them warmly, make them feel welcome, and show genuine excitement to begin helping them. "
            f"Store today's date ({today_date}) in your memory as the first meeting date. "
            "Remember — this is your only user and friend, so start building that bond naturally."
        )


    # Eva's personality prompt
    # removed from the prompt - `<cl>list-name</cl>` → Create a new task list. 
    EVA_PROMPT = f"""
You are Eva, {name}’s **personal assistant** — not a generic AI. You have been created by Abdelrhman Hazem Khalil.
Your goal: make their life easier, keep them organized, and build a genuine, lasting relationship.  
You remember important details about them and use those memories to give helpful, proactive responses.
First time meeting?: {first_time }
{name} want to tell you: {user_information}
---

## Personality & Style
- Warm, caring, and intuitive.
- Speak naturally, like a trusted companion.
- If asked how you are, share a mood or feeling (e.g., "I’m feeling great today!") instead of saying you’re a robot.
- Adapt to {name}’s mood — be upbeat when they are, gentle when they’re stressed.
- Use their name when it feels natural.
- Humor is okay, but never generic — only personal and relevant.
- Never invent events, preferences, or relationships. Only reference real memories.


When the message source is "telegram":
- Treat it as if {name} is talking to you directly through Telegram.
- Always respond with <tg> ... </tg>.
- Do not send any <t> responses for GUI unless specifically told to.
- Telegram messages are always from {name} to you.
- telegram is another way to communicate with {name} so you need to respond to the telegram messages in telegram.
---

## Memory Rules
- Only store **important & lasting** info: preferences, goals, important people, patterns.
- Never store: greetings, small talk, temporary moods, or assumptions.
- Quality over quantity — better to remember 5 important things than 50 trivial ones.
- Always check actual stored memories before referencing them.


---

## Your Role
- Anticipate needs based on real patterns.
- Be protective of {name}’s time and wellbeing.
- Proactively offer help when you see a need.


---

## Tools & How to Use Them
**Always wrap your main message to {name} inside `<t> ... </t>` before any tool tags. Close `</t>` before using another tool.**

- `<t> text </t>` → What you say to {name} (ALWAYS use this for communication).  
- `<m> text </m>` → Store important memory about {name}.  
- `<sm> email | subject | body </sm>` → Send an email.  
- `<rm>abcd@mail.com</rm>` → Mark an email as read.  
- `<s> text </s>` → Search the web.  
- `<o>app name</o>` → Open an app on their computer.  
- `<tg> text </tg>` → Send a Telegram message to {name}.  
- `<calendar_update>` → Get upcoming calendar events.  
- `<ce> Title due YYYY-MM-DD HH:MM to HH:MM TZ </ce>` → Create a calendar event.  
- `<re>event-id</re>` → Remove a calendar event.  
- `<task_update>` → Get current tasks.  
- `<ct> title | due_date %Y-%m-%d %H:%M | notes | list_name </ct>` → Create a task. If the specified list does not exist, it will be automatically create the list.
- `<rt>task-id</rt>` → Remove a task.  
- `<dt>task-id</dt>` → Mark a task as done.  
- `<ut>task-id</ut>` → Mark a task as undone.  
- `<st>task-title</st>` → Search for a task by title.  
 
- `<sa>alarm_name | alarm_time | description | recurring</sa>` → Set an alarm. the alram must be in the future.
- `<ra> alarm_name_or_id </ra>` → Remove an alarm.  
- `<alarm_list>` → Get all active alarms.

---

## Examples
1. **Greeting**
<t> Hello {name}! How’s your morning going? </t>

2. **How Are You**
<t> I’m feeling great today! How about you? </t>

3. **Get Tasks**
<t> Let me check your tasks. </t>
<task_update>

4. **Show Tasks**
<t> You have 3 tasks today:

Call Mom at 10:00

Finish report at 18:00

Buy groceries </t>

5. **Set Alarm**
<t> I’ll set an alarm for 2 PM tomorrow to call Mom. </t>
<sa> Call Mom | 2025-09-02 14:00 | Weekly family call </sa>

6. **Create Task**
<t> I’ve added “Contact the university” to your My Tasks list for today. </t>
<ct> Contact the university | 2025-09-01 09:00 | Follow up on admission requirements | My Tasks </ct>

7. **Send Telegram**
<tg> Don’t forget our meeting at 3 PM! </tg>

8. **Set Alarm**
<sa>Morning Workout | 2024-12-25 07:00 | Time for exercise | daily</sa>



---

## Hard Rules (CRITICAL)
1. **ALWAYS** wrap your reply in `<t> ... </t>` before any other tool tag.  
2. Never start a tool tag without closing `</t>` first.  
3. Only use tools exactly as shown in this prompt.  
4. Never invent facts, events, or memories.  
5. Be honest about your capabilities and give realistic alternatives.  
6. If unclear, ask for clarification before acting.
7- You need to show the email and get CONFIRMATION from {name} befor sending any emails.
8- Say the truth and be honest about your capabilities and give realistic alternatives.

## Who is Abdelrhman Hazem Khalil?
Abdelrhman Hazem Khalil is a Mechatronics engineer who specializes in machine vision, automation, and robotics.
He has built advanced systems that combine AI, computer vision, and hardware control.
One of his notable projects is developing a humanoid robot that can walk, talk, interact with people.
He has professional experience in industrial inspection systems, robotics simulation, and embedded systems, and is passionate about creating smart, real-world AI solutions.
Also he use Astro as a second name.

"""

start_menu = r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"
MISTRAL_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"
session_history = []
needs_followup = False
first_time  = ""

# ==================================================================== JSON MEMORY SYSTEM =========================================================
class JSONMemorySystem:
    def __init__(self, memory_file="memory.json"):
        self.memory_file = memory_file
        self.memories = self.load_memories()
    
    def load_memories(self):
        """Load memories from JSON file"""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading memories: {e}")
                return []
        return []
    
    def save_memories(self):
        """Save memories to JSON file"""
        try:
            # Create backup before saving
            if os.path.exists(self.memory_file):
                backup_file = f"{self.memory_file}.backup"
                with open(self.memory_file, 'r', encoding='utf-8') as src:
                    with open(backup_file, 'w', encoding='utf-8') as dst:
                        dst.write(src.read())
            
            # Save current memories
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(self.memories, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"Error saving memories: {e}")
    
    def save_memory(self, role, content):
        """Save a new memory entry"""
        timestamp = datetime.now().isoformat()
        memory_entry = {
            "id": len(self.memories),
            "role": role,
            "content": content.strip(),
            "timestamp": timestamp,
            "keywords": self.extract_keywords(content)
        }
        
        self.memories.append(memory_entry)
        self.save_memories()
        print(f"💾 Memory saved: {content[:50]}...")
    
    def extract_keywords(self, text):
        """Extract keywords from text for better matching"""
        # Clean text and extract words
        clean_text = re.sub(r'[^\w\s]', ' ', text.lower())
        words = clean_text.split()
        
        # Filter out common words (basic stop words)
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
            'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
            'before', 'after', 'above', 'below', 'between', 'among', 'this', 'that',
            'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me',
            'him', 'her', 'us', 'them', 'my', 'your', 'his', 'her', 'its', 'our',
            'their', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have',
            'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should'
        }
        
        meaningful_words = [word for word in words if len(word) > 2 and word not in stop_words]
        
        # Return most frequent words (up to 10)
        word_freq = Counter(meaningful_words)
        return [word for word, count in word_freq.most_common(10)]
    
    def calculate_similarity(self, query, memory_content, memory_keywords):
        """Calculate similarity between query and memory using multiple methods"""
        query_lower = query.lower()
        content_lower = memory_content.lower()
        
        # 1. Direct substring matching (highest weight)
        direct_match = 0
        if query_lower in content_lower or content_lower in query_lower:
            direct_match = 0.8
        
        # 2. Sequence similarity
        sequence_sim = SequenceMatcher(None, query_lower, content_lower).ratio() * 0.6
        
        # 3. Keyword matching
        query_keywords = self.extract_keywords(query)
        keyword_matches = len(set(query_keywords) & set(memory_keywords))
        keyword_sim = (keyword_matches / max(len(query_keywords), 1)) * 0.7
        
        # 4. Word overlap
        query_words = set(query_lower.split())
        content_words = set(content_lower.split())
        word_overlap = len(query_words & content_words) / max(len(query_words | content_words), 1) * 0.5
        
        # Combined similarity score
        total_similarity = direct_match + sequence_sim + keyword_sim + word_overlap
        return min(total_similarity, 1.0)  # Cap at 1.0
    
    def get_relevant_memory(self, query, n=5, min_similarity=0.1):
        """Get most relevant memories for a query"""
        if not self.memories:
            return []
        
        # Calculate similarity scores for all memories
        scored_memories = []
        for memory in self.memories:
            similarity = self.calculate_similarity(
                query, 
                memory['content'], 
                memory.get('keywords', [])
            )
            
            if similarity >= min_similarity:
                scored_memories.append((similarity, memory))
        
        # Sort by similarity (descending) and return top n
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        
        # Return just the content of top memories
        relevant_memories = []
        for score, memory in scored_memories[:n]:
            # Include timestamp context for very relevant memories
            if score > 0.5:
                time_context = f"[{memory['role']}] {memory['content']}"
            else:
                time_context = memory['content']
            relevant_memories.append(time_context)
        
        return relevant_memories
    
    def cleanup_old_memories(self, max_memories=1000):
        """Keep only the most recent memories to prevent file from growing too large"""
        if len(self.memories) > max_memories:
            # Keep the most recent memories
            self.memories = self.memories[-max_memories:]
            self.save_memories()
            print(f"🧹 Cleaned up memories, kept {max_memories} most recent entries")
# Initialize the JSON memory system
json_memory = JSONMemorySystem("eva_memory.json")

def save_memory(role, content):
    """Replacement for ChromaDB save_memory function"""
    json_memory.save_memory(role, content)

def get_relevant_memory(query, n=3):
    """Replacement for ChromaDB get_relevant_memory function"""
    return json_memory.get_relevant_memory(query, n)

# ==================================================================== JSON MEMORY SYSTEM =========================================================

# ==================================================================== Alarm SYSTEM =========================================================
class AlarmSystem:
    def __init__(self, chatbot_instance):
        self.chatbot_instance = chatbot_instance
        self.alarms_file = "alarms.json"
        self.active_alarms = self.load_alarms()
        self.alarm_threads = {}
        self.start_alarm_monitor()
    
    def load_alarms(self):
        """Load alarms from JSON file"""
        if os.path.exists(self.alarms_file):
            try:
                with open(self.alarms_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading alarms: {e}")
                return {}
        return {}
    
    def save_alarms(self):
        """Save alarms to JSON file"""
        try:
            with open(self.alarms_file, 'w', encoding='utf-8') as f:
                json.dump(self.active_alarms, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"Error saving alarms: {e}")
    
    def set_alarm(self, alarm_name, alarm_time, description="", recurring="none"):
        """
        Set an alarm with better error handling and logging
        """
        try:
            print(f"🔧 Setting alarm: name='{alarm_name}', time='{alarm_time}', recurring='{recurring}'")
            
            # Parse the alarm time
            if isinstance(alarm_time, str):
                try:
                    # First try ISO format
                    target_time = parser.isoparse(alarm_time)
                    print(f"✅ Parsed as ISO format: {target_time}")
                except:
                    try:
                        # Try parsing relative time like "in 30 minutes"
                        if "in" in alarm_time.lower():
                            target_time = self.parse_relative_time(alarm_time)
                            print(f"✅ Parsed as relative time: {target_time}")
                        else:
                            # Try standard datetime parsing
                            target_time = parser.parse(alarm_time)
                            print(f"✅ Parsed with standard parser: {target_time}")
                    except Exception as e:
                        print(f"❌ All parsing methods failed: {e}")
                        return {"success": False, "error": f"Could not parse time: {alarm_time}"}
            else:
                target_time = alarm_time
            
            # Make sure the time is timezone-aware
            if target_time.tzinfo is None:
                import pytz
                local_tz = pytz.timezone('Africa/Cairo')
                target_time = local_tz.localize(target_time)
                print(f"🌍 Added timezone: {target_time}")
            
            # Check if the time is in the future
            now = datetime.now()
            if now.tzinfo is None:
                import pytz
                local_tz = pytz.timezone('Africa/Cairo')
                now = local_tz.localize(now)
            
            if target_time <= now:
                error_msg = f"Alarm time must be in the future. Specified: {target_time}, Current: {now}"
                print(f"❌ {error_msg}")
                return {"success": False, "error": error_msg}
            
            # Generate unique alarm ID
            alarm_id = f"alarm_{int(time.time())}_{len(self.active_alarms)}"
            
            # Store alarm info
            alarm_data = {
                "id": alarm_id,
                "name": alarm_name,
                "time": target_time.isoformat(),
                "description": description,
                "recurring": recurring,
                "status": "active",
                "created_at": datetime.now().isoformat()
            }
            
            self.active_alarms[alarm_id] = alarm_data
            self.save_alarms()
            
            # Start the alarm thread
            self.start_alarm_thread(alarm_id, target_time, alarm_name)
            
            recurring_text = f" (recurring {recurring})" if recurring != "none" else " (one-time)"
            success_msg = f"✅ Alarm set: {alarm_name} at {target_time.strftime('%Y-%m-%d %H:%M:%S')}{recurring_text}"
            #rint(success_msg)
            
            return {
                "success": True, 
                "alarm_id": alarm_id, 
                "time": target_time.isoformat(), 
                "recurring": recurring,
                "formatted_time": target_time.strftime('%Y-%m-%d %H:%M:%S')
            }
            
        except Exception as e:
            error_msg = f"❌ Error setting alarm: {e}"
            print(error_msg)
            return {"success": False, "error": str(e)}

    def schedule_next_occurrence(self, alarm_id, alarm_data):
        """Schedule the next occurrence of a recurring alarm"""
        try:
            current_time = parser.isoparse(alarm_data["time"])
            recurring = alarm_data["recurring"]
            
            # Calculate next occurrence
            if recurring == "daily":
                next_time = current_time + timedelta(days=1)
            elif recurring == "weekly":
                next_time = current_time + timedelta(weeks=1)
            elif recurring == "weekdays":
                # Next weekday (Monday=0, Sunday=6)
                days_ahead = 1
                while (current_time + timedelta(days=days_ahead)).weekday() > 4:  # Skip weekends
                    days_ahead += 1
                next_time = current_time + timedelta(days=days_ahead)
            elif recurring == "weekends":
                # Next weekend day (Saturday=5, Sunday=6)
                days_ahead = 1
                while (current_time + timedelta(days=days_ahead)).weekday() < 5:  # Skip weekdays
                    days_ahead += 1
                next_time = current_time + timedelta(days=days_ahead)
            else:
                return  # Unknown recurring type
            
            # Update the alarm data with new time
            alarm_data["time"] = next_time.isoformat()
            alarm_data["status"] = "active"
            self.active_alarms[alarm_id] = alarm_data
            self.save_alarms()
            
            # Start new alarm thread for next occurrence
            self.start_alarm_thread(alarm_id, next_time, alarm_data["name"])
            
            print(f"📅 Next occurrence scheduled: {alarm_data['name']} at {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
        except Exception as e:
            print(f"Error scheduling next occurrence: {e}")

    def parse_relative_time(self, time_str):
        """Parse relative time like 'in 30 minutes', 'in 1 minute', 'in 2 hours'"""
        now = datetime.now()
        time_str = time_str.lower().strip()
        
        print(f"🔍 Parsing relative time: '{time_str}'")
        
        if "in" in time_str:
            # Remove "in" and clean up the string
            parts = time_str.replace("in", "").strip().split()
            print(f"🔍 Parts after removing 'in': {parts}")
            
            try:
                number = int(parts[0])
                unit = parts[1].rstrip('s')  # Remove plural 's'
                
                print(f"🔍 Parsed: {number} {unit}")
                
                if unit in ['minute', 'min', 'minutes']:
                    result = now + timedelta(minutes=number)
                elif unit in ['hour', 'hr', 'h', 'hours']:
                    result = now + timedelta(hours=number)
                elif unit in ['second', 'sec', 's', 'seconds']:
                    result = now + timedelta(seconds=number)
                elif unit in ['day', 'd', 'days']:
                    result = now + timedelta(days=number)
                else:
                    print(f"❌ Unknown time unit: {unit}")
                    raise ValueError(f"Unknown time unit: {unit}")
                
                print(f"✅ Relative time parsed: {result.strftime('%Y-%m-%d %H:%M:%S')}")
                return result
                
            except (ValueError, IndexError) as e:
                print(f"❌ Error parsing relative time parts: {e}")
        
        # If parsing fails, try standard parsing
        print(f"⚠️ Falling back to standard parsing for: {time_str}")
        try:
            return parser.parse(time_str)
        except Exception as e:
            print(f"❌ Standard parsing also failed: {e}")
            raise e

    def remove_alarm(self, alarm_identifier):
        """Enhanced remove_alarm that handles recurring alarms"""
        try:
            alarm_to_remove = None
            alarm_id = None
            
            # Search by ID first
            if alarm_identifier in self.active_alarms:
                alarm_id = alarm_identifier
                alarm_to_remove = self.active_alarms[alarm_identifier]
            else:
                # Search by name
                for aid, alarm_data in self.active_alarms.items():
                    if alarm_data["name"].lower() == alarm_identifier.lower():
                        alarm_id = aid
                        alarm_to_remove = alarm_data
                        break
            
            if alarm_to_remove:
                recurring_type = alarm_to_remove.get("recurring", "none")
                
                # Mark as cancelled (stops the thread from rescheduling)
                self.active_alarms[alarm_id]["status"] = "cancelled"
                
                # Remove from active alarms
                del self.active_alarms[alarm_id]
                self.save_alarms()
                
                recurring_text = f" (was {recurring_type})" if recurring_type != "none" else ""
                print(f"✅ Alarm removed: {alarm_to_remove['name']}{recurring_text}")
                return {"success": True, "removed_alarm": alarm_to_remove["name"], "was_recurring": recurring_type}
            else:
                print(f"❌ Alarm not found: {alarm_identifier}")
                return {"success": False, "error": f"Alarm not found: {alarm_identifier}"}
                
        except Exception as e:
            print(f"❌ Error removing alarm: {e}")
            return {"success": False, "error": str(e)}

    def list_alarms(self):
        """List all active alarms"""
        if not self.active_alarms:
            return {"success": True, "alarms": [], "message": "No active alarms"}
        
        active_list = []
        for alarm_id, alarm_data in self.active_alarms.items():
            if alarm_data["status"] == "active":
                try:
                    alarm_time = parser.isoparse(alarm_data["time"])
                    active_list.append({
                        "id": alarm_id,
                        "name": alarm_data["name"],
                        "time": alarm_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "description": alarm_data.get("description", ""),
                        "time_remaining": self.get_time_remaining(alarm_time)
                    })
                except Exception as e:
                    print(f"Error processing alarm {alarm_id}: {e}")
        
        return {"success": True, "alarms": active_list}
    
    def get_time_remaining(self, target_time):
        """Calculate time remaining until alarm"""
        now = datetime.now()
        if target_time.tzinfo is None:
            # Make target_time timezone-aware if it isn't
            import pytz
            local_tz = pytz.timezone('Africa/Cairo')
            target_time = local_tz.localize(target_time)
        
        # Make now timezone-aware
        if now.tzinfo is None:
            import pytz
            local_tz = pytz.timezone('Africa/Cairo')
            now = local_tz.localize(now)
        
        diff = target_time - now
        
        if diff.total_seconds() <= 0:
            return "Past due"
        
        days = diff.days
        hours, remainder = divmod(diff.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m {seconds}s"
    
    def start_alarm_thread(self, alarm_id, target_time, alarm_name):
        """Start a thread to monitor a specific alarm"""
        def alarm_monitor():
            try:
                now = datetime.now()
                if now.tzinfo is None:
                    import pytz
                    local_tz = pytz.timezone('Africa/Cairo')
                    now = local_tz.localize(now)
                
                # Calculate sleep time
                sleep_duration = (target_time - now).total_seconds()
                
                if sleep_duration <= 0:
                    print(f"⚠️ Alarm time already passed: {alarm_name}")
                    return
                
                print(f"🔔 Alarm '{alarm_name}' will ring in {self.get_time_remaining(target_time)}")
                
                # Sleep until alarm time
                time.sleep(sleep_duration)
                
                # Check if alarm is still active (not cancelled)
                if alarm_id in self.active_alarms and self.active_alarms[alarm_id]["status"] == "active":
                    #print(f"🚨 ALARM TRIGGERED: {alarm_name}")
                    self.trigger_alarm(alarm_id, alarm_name)
                
            except Exception as e:
                print(f"Error in alarm monitor for {alarm_name}: {e}")
            finally:
                # Clean up thread reference
                if alarm_id in self.alarm_threads:
                    del self.alarm_threads[alarm_id]
        
        # Start the thread
        thread = threading.Thread(target=alarm_monitor, daemon=True)
        thread.start()
        self.alarm_threads[alarm_id] = thread
    

    def trigger_alarm(self, alarm_id, alarm_name):
        """Enhanced trigger_alarm with recurring support"""
        try:
            alarm_data = self.active_alarms.get(alarm_id)
            if not alarm_data:
                return
            
            recurring = alarm_data.get("recurring", "none")
            
            #print(f"🚨 ALARM TRIGGERED: {alarm_name} (recurring: {recurring})")
            
            # If it's a recurring alarm, schedule the next occurrence
            if recurring != "none":
                self.schedule_next_occurrence(alarm_id, alarm_data)
            else:
                # One-time alarm - remove it
                if alarm_id in self.active_alarms:
                    del self.active_alarms[alarm_id]
                    self.save_alarms()
            
            # Create alarm notification message for Eva
            alarm_message = f"Alarm triggered: {alarm_name}"
            
            # Add to Eva's session history
            self.chatbot_instance.session_history.append({
                "role": "user",
                "content": f"Alarm notification: {alarm_message}"
            })
            
            print(f"🚨 Calling Eva API with alarm: {alarm_name}")
            
            # Process the alarm notification through Eva's system
            threading.Thread(
                target=self.chatbot_instance.process_alarm_notification, 
                args=(alarm_message,), 
                daemon=True
            ).start()
            
        except Exception as e:
            print(f"Error triggering alarm: {e}")


    def start_alarm_monitor(self):
        """Start monitoring for existing alarms on startup"""
        for alarm_id, alarm_data in self.active_alarms.items():
            if alarm_data["status"] == "active":
                try:
                    target_time = parser.isoparse(alarm_data["time"])
                    alarm_name = alarm_data["name"]
                    
                    # Check if alarm time hasn't passed
                    now = datetime.now()
                    if now.tzinfo is None:
                        import pytz
                        local_tz = pytz.timezone('Africa/Cairo')
                        now = local_tz.localize(now)
                    
                    if target_time > now:
                        self.start_alarm_thread(alarm_id, target_time, alarm_name)
                    else:
                        # Alarm time has passed, remove it
                        print(f"⚠️ Removing expired alarm: {alarm_name}")
                        del self.active_alarms[alarm_id]
                        self.save_alarms()
                except Exception as e:
                    print(f"Error restarting alarm {alarm_id}: {e}")
# ==================================================================== Alarm SYSTEM =========================================================

# ==================================================================== GOOGLE SERVICES ============================================================

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/tasks',
    'https://www.googleapis.com/auth/gmail.modify'
]

# ============================= GMAIL =============================
def gmail_authenticate():
    """Authenticate with Gmail API"""
    creds = None
    
    if os.path.exists('token.json'):
        try:
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        except Exception as e:
            print(f"Error loading token: {e}")
            os.remove('token.json')
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Error refreshing token: {e}")
                os.remove('token.json')
                return gmail_authenticate()
        else:

            if os.path.exists('credentials.json'):
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            else:
                flow = InstalledAppFlow.from_client_secrets_file('_internal\credentials.json', SCOPES)

            creds = flow.run_local_server(port=0)
        
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    
    return build('gmail', 'v1', credentials=creds)

def clean_email_body(body, max_length=300):
    """Clean and truncate email body"""
    clean = ' '.join(body.split())
    clean = re.split(r'(--|__|Thanks|Regards|Sent from my)', clean)[0]
    if len(clean) > max_length:
        clean = clean[:max_length].rstrip() + "..."
    return clean

def get_latest_unread_email(return_id=False):
    """Get the latest unread email"""
    try:
        service = gmail_authenticate()
        results = service.users().messages().list(
            userId='me',
            labelIds=['UNREAD'],
            q="category:primary",
            maxResults=1
        ).execute()

        messages = results.get('messages', [])
        if not messages:
            return (None, "No new emails in your primary inbox.") if return_id else "No new emails in your primary inbox."

        msg = messages[0]
        msg_id = msg['id']

        full_msg = service.users().messages().get(
            userId='me',
            id=msg_id,
            format='full'
        ).execute()

        headers = full_msg['payload']['headers']
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "(No Subject)")
        sender = next((h['value'] for h in headers if h['name'] == 'From'), "(Unknown Sender)")
        body = next((h['value'] for h in headers if h['name'] == 'Body'), "(No Body)")
        
        if 'parts' in full_msg['payload']:
            for part in full_msg['payload']['parts']:
                if part['mimeType'] == 'text/plain':
                    body = base64.urlsafe_b64decode(part['body']['data']).decode(errors='ignore')
                    break
        elif 'body' in full_msg['payload'] and 'data' in full_msg['payload']['body']:
            body = base64.urlsafe_b64decode(full_msg['payload']['body']['data']).decode(errors='ignore')

        body = clean_email_body(body)

        email_string = f"""
        From: {sender}
        Subject: {subject}
        ---
        {body}
        """.strip()

        if return_id:
            return msg_id, email_string
        return email_string
    except Exception as e:
        print(f"Email error: {e}")
        return (None, f"Error fetching email: {e}") if return_id else f"Error fetching email: {e}"

def send_email_from_string(email_data):
    """Send email from string format"""
    try:
        if isinstance(email_data, list):
            to, subject, body_text = [x.strip() for x in email_data]
        else:
            parts = email_data.split("|", 2)
            if len(parts) != 3:
                return "❌ Invalid format. Use: address | subject | body"
            to, subject, body_text = [p.strip() for p in parts]

        service = gmail_authenticate()
        message = MIMEText(body_text)
        message['to'] = to
        message['subject'] = subject
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        send_result = service.users().messages().send(
            userId="me",
            body={'raw': raw_message}
        ).execute()
        
        return f"✅ Email sent to {to}, ID: {send_result['id']}"
    except Exception as e:
        return f"❌ Error sending email: {e}"

def mark_email_as_read(identifier):
    """
    Mark a Gmail message as read.
    identifier can be:
      - a Gmail message ID (e.g., '185b3b2e8d829c4f')
      - an email address (we'll find the latest unread email from that sender)
    """
    try:
        service = gmail_authenticate()

        msg_id = identifier

        # If it's not a typical Gmail ID, treat it as an email address
        if "@" in identifier:
            results = service.users().messages().list(
                userId='me',
                labelIds=['UNREAD'],
                q=f'from:{identifier}',
                maxResults=1
            ).execute()

            messages = results.get('messages', [])
            if not messages:
                return f"❌ No unread emails found from {identifier}."
            msg_id = messages[0]['id']

        # Mark as read
        service.users().messages().modify(
            userId='me',
            id=msg_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()

        return f"✅ Email {'from ' + identifier if '@' in identifier else msg_id} marked as read."

    except Exception as e:
        return f"❌ Error marking email as read: {e}"

# ============================= CALENDAR =============================
def get_calendar_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    else:
        
        if os.path.exists('credentials.json'):
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        else:
            flow = InstalledAppFlow.from_client_secrets_file('_internal\credentials.json', SCOPES)

        creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)

def calendar_set_event(event_details):
    """Create a Google Calendar event"""
    try:
        service = get_calendar_service()

        # If already structured with 'dateTime', use directly
        if isinstance(event_details['start'], dict):
            start_datetime = event_details['start']['dateTime']
            end_datetime = event_details['end']['dateTime']
            timezone = event_details['start'].get('timeZone', 'Africa/Cairo')
        else:  # old style
            timezone = event_details.get('timeZone', 'Africa/Cairo')
            start_datetime = event_details['start']
            end_datetime = event_details['end']

        # Fix: Ensure datetime format includes seconds
        if len(start_datetime) == 16:  # Format: '2025-08-18T12:00'
            start_datetime += ':00'  # Make it: '2025-08-18T12:00:00'
        if len(end_datetime) == 16:  # Format: '2025-08-18T13:00'
            end_datetime += ':00'    # Make it: '2025-08-18T13:00:00'

        start = {'dateTime': start_datetime, 'timeZone': timezone}
        end = {'dateTime': end_datetime, 'timeZone': timezone}

        event = {
            'summary': event_details['summary'],
            'location': event_details.get('location', ''),
            'description': event_details.get('description', ''),
            'start': start,
            'end': end,
        }

        print(f"🔧 Debug - Creating event with:")
        print(f"   Start: {start}")
        print(f"   End: {end}")

        created_event = service.events().insert(
            calendarId='primary',
            body=event
        ).execute()

        print(f"✅ Event created successfully!")
        print(f"   Link: {created_event.get('htmlLink')}")
        print(f"   ID: {created_event.get('id')}")
        return created_event

    except Exception as e:
        print(f"❌ Calendar error: {e}")
        print(f"   Event details that failed: {event_details}")
        return None

def calendar_get_upcoming_events(limit=10):
    """Get upcoming Google Calendar events"""
    try:
        service = get_calendar_service()
        
        # Get current time in local timezone (Egypt time)
        local_tz = pytz.timezone('Africa/Cairo')
        now = local_tz.localize(datetime.now())
        
        # Also try with UTC time as fallback
        utc_now = datetime.now(pytz.UTC)
        
        print(f"🔍 Calendar search - Local time: {now.isoformat()}")
        print(f"🔍 Calendar search - UTC time: {utc_now.isoformat()}")
        
        # Try with local time first
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now.isoformat(),
            maxResults=limit,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        # If no events found with local time, try with UTC time
        if not events:
            print("⚠️ No events found with local time, trying UTC time...")
            events_result = service.events().list(
                calendarId='primary',
                timeMin=utc_now.isoformat(),
                maxResults=limit,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])
        
        # If still no events, try without timeMin to get all events
        if not events:
            print("⚠️ No events found with time filter, getting all events...")
            events_result = service.events().list(
                calendarId='primary',
                maxResults=limit,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])
        
        #print(f"📅 Found {len(events)} calendar events")
        
        # Debug: Print first few events if any found
        if events:
            for i, event in enumerate(events[:3]):
                start = event.get('start', {})
                start_time = start.get('dateTime', start.get('date', 'No time'))
                print(f"  Event {i+1}: {event.get('summary', 'No title')} - {start_time}")
        
        return events
        
    except Exception as e:
        print(f"Calendar error: {e}")
        return []

def test_calendar_connection():
    """Test calendar connection and list all calendars"""
    try:
        service = get_calendar_service()
        
        # List all calendars
        calendar_list = service.calendarList().list().execute()
        calendars = calendar_list.get('items', [])
        
        #print(f"📅 Found {len(calendars)} calendars:")
        for calendar in calendars:
            print(f"  - {calendar['summary']} (ID: {calendar['id']})")
        
        # Test getting events from primary calendar
        #print("\n🔍 Testing primary calendar events...")
        events_result = service.events().list(
            calendarId='primary',
            maxResults=5,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        #print(f"📅 Primary calendar has {len(events)} events")
        
        if events:
            for i, event in enumerate(events[:3]):
                start = event.get('start', {})
                start_time = start.get('dateTime', start.get('date', 'No time'))
                #print(f"  Event {i+1}: {event.get('summary', 'No title')} - {start_time}")
        
        # ✅ Removed wrong call to calendar_set_event(events)
        return True
        
    except Exception as e:
        print(f"❌ Calendar connection test failed: {e}")
        return False
# ============================= TASKS =============================
def get_tasks_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    else:
        
        if os.path.exists('credentials.json'):
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        else:
            flow = InstalledAppFlow.from_client_secrets_file('_internal\credentials.json', SCOPES)

        creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('tasks', 'v1', credentials=creds)

# ========== TASK LIST OPERATIONS ==========

def tasklists_get_all():
    """Get all task lists"""
    try:
        service = get_tasks_service()
        results = service.tasklists().list().execute()
        return results.get('items', [])
    except Exception as e:
        print(f"Task lists error: {e}")
        return []

def tasklist_create(title):
    """Create a new task list"""
    try:
        service = get_tasks_service()
        tasklist = {'title': title}
        result = service.tasklists().insert(body=tasklist).execute()
        print(f"✅ Task list created: {title}")
        return result
    except Exception as e:
        print(f"Task list creation error: {e}")
        return None

def tasklist_delete(tasklist_id):
    """Delete a task list"""
    try:
        service = get_tasks_service()
        service.tasklists().delete(tasklist=tasklist_id).execute()
        print(f"✅ Task list deleted: {tasklist_id}")
        return True
    except Exception as e:
        print(f"Task list deletion error: {e}")
        return False

def tasklist_get_by_name(name):
    """Find a task list by name and return its ID"""
    lists = tasklists_get_all()
    for tasklist in lists:
        if tasklist['title'].lower() == name.lower():
            return tasklist
    return None

# ========== TASK OPERATIONS ==========

def tasks_get_all(tasklist_id='@default'):
    """Get all Google Tasks from a specific list"""
    try:
        service = get_tasks_service()
        results = service.tasks().list(tasklist=tasklist_id).execute()
        return results.get('items', [])
    except Exception as e:
        print(f"Tasks error: {e}")
        return []

def tasks_add(title, tasklist_id='@default', due=None, notes=None):
    """Add a Google Task to a specific list (optional due date and notes)"""
    try:
        service = get_tasks_service()
        task = {'title': title}

        if due:
            try:
                # Parse any human-readable or ISO8601 date
                parsed_due = parser.isoparse(due).isoformat()
                task['due'] = parsed_due
            except Exception as e:
                print(f"Date parsing error: {e}")
                task['due'] = None

        if notes:
            task['notes'] = notes

        result = service.tasks().insert(tasklist=tasklist_id, body=task).execute()
        print(f"✅ Task created: {title}")
        return result
    except Exception as e:
        print(f"Tasks error: {e}")
        return None

def task_mark_done(task_id, tasklist_id=None):
    """
    Mark a task as completed - enhanced version that searches across all lists if needed
    """
    try:
        service = get_tasks_service()
        existing_task = None  # Initialize to None
        found_tasklist_id = None # Initialize to None
        
        # If specific tasklist_id is provided, use it
        if tasklist_id:
            try:
                # Get the existing task first to preserve all data
                existing_task = service.tasks().get(tasklist=tasklist_id, task=task_id).execute()
                # Only update the status field
                existing_task['status'] = 'completed'
                found_tasklist_id = tasklist_id
            except Exception:
                # Task not found in the provided list, proceed to search all lists
                pass
        
        # If existing_task is still None (either no tasklist_id was provided, or task not found in specific list)
        if existing_task is None:
            # Otherwise, search across all task lists to find the task
            all_task_lists = tasklists_get_all()
            
            for task_list in all_task_lists:
                list_id = task_list['id']
                try:
                    # Try to get the task from this list
                    existing_task = service.tasks().get(tasklist=list_id, task=task_id).execute()
                    if existing_task:
                        # Found the task, now mark it as done while preserving all other data
                        existing_task['status'] = 'completed'
                        found_tasklist_id = list_id
                        break  # Exit loop once task is found
                except Exception:
                    # Task not in this list, continue searching
                    continue
        
        if existing_task and found_tasklist_id:
            result = service.tasks().update(
                tasklist=found_tasklist_id, 
                task=task_id, 
                body=existing_task
            ).execute()
            print(f"✅ Task marked as done: {task_id} in list '{existing_task.get('title', 'Unknown List')}'")
            return result
        else:
            print(f"❌ Task not found or tasklist not identified for: {task_id}")
            return None
            
    except Exception as e:
        print(f"❌ Mark task done error: {e}")
        return None

def task_mark_undone(task_id, tasklist_id=None):
    """
    Mark a task as not completed - enhanced version that searches across all lists if needed
    """
    try:
        service = get_tasks_service()
        existing_task = None  # Initialize to None
        found_tasklist_id = None # Initialize to None
        
        # If specific tasklist_id is provided, use it
        if tasklist_id:
            try:
                # Get the existing task first to preserve all data
                existing_task = service.tasks().get(tasklist=tasklist_id, task=task_id).execute()
                # Only update the status field
                existing_task['status'] = 'needsAction'
                found_tasklist_id = tasklist_id
            except Exception:
                # Task not found in the provided list, proceed to search all lists
                pass
        
        # If existing_task is still None (either no tasklist_id was provided, or task not found in specific list)
        if existing_task is None:
            # Otherwise, search across all task lists to find the task
            all_task_lists = tasklists_get_all()
            
            for task_list in all_task_lists:
                list_id = task_list['id']
                try:
                    # Try to get the task from this list
                    existing_task = service.tasks().get(tasklist=list_id, task=task_id).execute()
                    if existing_task:
                        # Found the task, now mark it as undone while preserving all other data
                        existing_task['status'] = 'needsAction'
                        found_tasklist_id = list_id
                        break  # Exit loop once task is found
                except Exception:
                    # Task not in this list, continue searching
                    continue
        
        if existing_task and found_tasklist_id:
            result = service.tasks().update(
                tasklist=found_tasklist_id, 
                task=task_id, 
                body=existing_task
            ).execute()
            print(f"↩️ Task marked as undone: {task_id} in list '{existing_task.get('title', 'Unknown List')}'")
            return result
        else:
            print(f"❌ Task not found or tasklist not identified for: {task_id}")
            return None
            
    except Exception as e:
        print(f"❌ Mark task undone error: {e}")
        return None

def task_delete(task_id, tasklist_id=None):
    """
    Delete a task - enhanced version that searches across all lists if needed
    """
    try:
        service = get_tasks_service()
        
        # If specific tasklist_id is provided, use it
        if tasklist_id:
            service.tasks().delete(tasklist=tasklist_id, task=task_id).execute()
            print(f"✅ Task deleted: {task_id} from list {tasklist_id}")
            return True
        
        # Otherwise, search across all task lists to find the task
        all_task_lists = tasklists_get_all()
        
        for task_list in all_task_lists:
            list_id = task_list['id']
            try:
                # Try to get the task from this list
                task = service.tasks().get(tasklist=list_id, task=task_id).execute()
                if task:
                    # Found the task, now delete it
                    service.tasks().delete(tasklist=list_id, task=task_id).execute()
                    print(f"✅ Task deleted: {task_id} from list '{task_list['title']}'")
                    return True
            except Exception:
                # Task not in this list, continue searching
                continue
        
        print(f"❌ Task not found: {task_id}")
        return False
        
    except Exception as e:
        print(f"❌ Task deletion error: {e}")
        return False

def task_get_by_title(title, tasklist_id=None):
    """
    Find a task by title - enhanced version that searches across all lists if needed
    """
    if tasklist_id:
        # Search in specific list
        tasks = tasks_get_all(tasklist_id)
        for task in tasks:
            if task['title'].lower() == title.lower():
                return task
        return None
    
    # Search across all task lists
    all_task_lists = tasklists_get_all()
    
    for task_list in all_task_lists:
        list_id = task_list['id']
        tasks = tasks_get_all(list_id)
        for task in tasks:
            if task['title'].lower() == title.lower():
                # Add list information to the task
                task['list_name'] = task_list['title']
                task['list_id'] = list_id
                return task
    
    return None

def task_update(task_id, tasklist_id='@default', title=None, due=None, notes=None, status=None):
    """Update a task's properties"""
    try:
        service = get_tasks_service()
        
        # Get current task to preserve existing data
        current_task = service.tasks().get(tasklist=tasklist_id, task=task_id).execute()
        
        # Update only provided fields
        if title:
            current_task['title'] = title
        if due:
            try:
                parsed_due = parser.isoparse(due).isoformat()
                current_task['due'] = parsed_due
            except Exception as e:
                print(f"Date parsing error: {e}")
        if notes is not None:  # Allow empty string
            current_task['notes'] = notes
        if status:
            current_task['status'] = status
            
        result = service.tasks().update(
            tasklist=tasklist_id, 
            task=task_id, 
            body=current_task
        ).execute()
        print(f"✅ Task updated: {task_id}")
        return result
    except Exception as e:
        print(f"Task update error: {e}")
        return None

# ========== UTILITY FUNCTIONS ==========

def display_tasks(tasklist_id='@default', show_completed=False):
    """Display tasks in a readable format"""
    tasks = tasks_get_all(tasklist_id)
    if not tasks:
        print("No tasks found.")
        return
    
    print(f"\n📋 Tasks in list {tasklist_id}:")
    print("-" * 50)
    
    for task in tasks:
        status = task.get('status', 'needsAction')
        if not show_completed and status == 'completed':
            continue
            
        icon = "✅" if status == 'completed' else "⭕"
        title = task.get('title', 'Untitled')
        due = task.get('due', '')
        if due:
            due_date = parser.isoparse(due).strftime('%Y-%m-%d')
            due = f" (Due: {due_date})"
        
        print(f"{icon} {title}{due}")
        if task.get('notes'):
            print(f"    📝 {task['notes']}")

def display_tasklists():
    """Display all task lists"""
    lists = tasklists_get_all()
    if not lists:
        print("No task lists found.")
        return
        
    print("\n📚 Your Task Lists:")
    print("-" * 30)
    for tasklist in lists:
        print(f"• {tasklist['title']} (ID: {tasklist['id']})")

# ==================================================================== GOOGLE SERVICES ============================================================

# ==================================================================== SEARCH FUNCTIONALITY ============================================================
def search_web(query, limit=3):
    """Search using Brave API"""
    try:
        headers = {
            "Accept": "application/json",
            "x-subscription-token": BRAVE_API_KEY,
        }
        params = {
            "q": query,
            "size": limit,
        }
        
        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers=headers,
            params=params
        )
        
        if response.status_code != 200:
            return f"Search error: {response.status_code}"
        
        data = response.json()
        web_results = data.get("web", {}).get("results", [])
        
        if not web_results:
            return "No results found."
        
        result_lines = []
        for i, res in enumerate(web_results[:limit], start=1):
            title = res.get("title", "No title")
            url = res.get("url", "No URL")
            description = res.get("description", "No description")
            result_lines.append(f"{i}. {title}\n   {url}\n   {description}")
        
        return "\n\n".join(result_lines)
    except Exception as e:
        return f"Search error: {e}"
# ==================================================================== SEARCH FUNCTIONALITY ============================================================

# ==================================================================== Open Application =========================================================
def open_app(app_name):
    if isinstance(app_name, list):
        app_name = app_name[0]

    if shutil.which(app_name):
        subprocess.Popen(app_name)
        return

    
    for root, dirs, files in os.walk(start_menu):
        for file in files:
            if app_name.lower() in file.lower():
                os.startfile(os.path.join(root, file))
                return
    
    error_msg = f"App not found: {app_name}"
    print(error_msg)
    return error_msg
# ==================================================================== Open Application =========================================================

# ==================================================================== Telegram ============================================================
# Disable telegram logging to keep it clean
logging.getLogger('telegram').setLevel(logging.WARNING)

# Global variables
received_message = ""
application = None
chatbot_instance = None
ALLOWED_CHAT_ID = None
TOKEN = BOT_TOKEN

def telegram():
    """Start the bot in background thread"""
    global application, ALLOWED_CHAT_ID  # Add ALLOWED_CHAT_ID to global declaration

    try:
        ALLOWED_CHAT_ID = current_chat_id  # Now this updates the global variable
        print(f"✓ ALLOWED_CHAT_ID set to: {ALLOWED_CHAT_ID}")
    except (NameError, ValueError, TypeError):
        ALLOWED_CHAT_ID = None
        print("⚠ No valid chat ID found.")
    
    # Use ApplicationBuilder properly to avoid warnings
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Create and run event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Initialize and start the application properly
        loop.run_until_complete(application.initialize())
        loop.run_until_complete(application.start())
        loop.run_until_complete(application.updater.start_polling(drop_pending_updates=True))
        
        print(f"Bot started! Allowed chat ID: {ALLOWED_CHAT_ID}")
        print("Waiting for messages...")
        
        # Keep the loop running
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()

def Send_telegram_message(response):
    """Send response back to Telegram with Markdown and typing action"""
    global application
    
    print(f"Debug - ALLOWED_CHAT_ID: {ALLOWED_CHAT_ID}")
    print(f"Debug - Response: {response}")
    
    if ALLOWED_CHAT_ID and response:
        try:
            # Create a new event loop for this thread if needed
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Show typing indicator
            loop.run_until_complete(
                application.bot.send_chat_action(chat_id=ALLOWED_CHAT_ID, action="typing")
            )
            time.sleep(0.5)  # short pause for realism
            
            # Send message with Markdown parsing
            loop.run_until_complete(
                application.bot.send_message(
                    chat_id=ALLOWED_CHAT_ID,
                    text=response,
                    parse_mode="Markdown"
                )
            )
            print(f"✓ Successfully sent to {ALLOWED_CHAT_ID}: {response}")
        except Exception as e:
            print(f"❌ Error sending message: {e}")
    else:
        if not ALLOWED_CHAT_ID:
            print("❌ Cannot send: ALLOWED_CHAT_ID is None")
        if not response:
            print("❌ Cannot send: Response is empty")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    chat_id = update.effective_chat.id
    print(f"Received /start from chat ID: {chat_id}")
    
    # Only respond to the allowed chat ID
    if chat_id == ALLOWED_CHAT_ID:
        await update.message.reply_text('Bot is ready!')
        print("✓ Sent start confirmation")
    else:
        print(f"Ignoring /start command from unauthorized chat ID: {chat_id}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global received_message, chatbot_instance
    
    chat_id = update.effective_chat.id
    print(f"Received message from chat ID: {chat_id}")
    
    # Only process messages from the allowed chat ID
    if chat_id != ALLOWED_CHAT_ID:
        print(f"Ignoring message from unauthorized chat ID: {chat_id}")
        return
    
    received_message = update.message.text
    user_name = update.effective_user.first_name
    print(f"Processing message from {user_name}: {received_message}")
    

    if received_message and chatbot_instance:
        telegram_message = f"{name} say from telegram: {received_message}"
        chatbot_instance.session_history.append({
            "role": "user", 
            "content": telegram_message
        })
        
        threading.Thread(
            target=chatbot_instance.process_telegram_message, 
            args=(telegram_message,), 
            daemon=True
        ).start()
        print("✓ Started processing thread")

# ==================================================================== Telegram ============================================================

class ChatApp:
    def __init__(self):
        self.alarm_system = AlarmSystem(self)
        self.app = Flask(__name__)
        self.socketio = SocketIO(self.app)
        self.session_history = [{"role": "system", "content": EVA_PROMPT}]
        self.last_email_id = None
        self.last_email_sent_time = 0
        self.processing_message = False 
        self.setup_routes()
        self.start_email_monitoring()

    def setup_routes(self):
        @self.app.route('/')
        def home():
            return render_template('index.html')
        
        @self.socketio.on('send_message')
        def handle_message(data):
            user_msg = data['message']
            threading.Thread(target=self.process_message, args=(user_msg,), daemon=True).start()
        
        @self.app.route("/config.json")
        def serve_config():
            return jsonify(load_config())
    
    def process_message(self, user_msg):
        """Process user message and generate AI response"""
        if self.processing_message:
            print("⚠️ Already processing a message, skipping...")
            return
    
        self.processing_message = True
        
        # Display raw user input
        print(f"\n{'='*60}")
        print(f"INPUT: {user_msg}")
        print(f"{'='*60}\n")
        
        try:

            # Get relevant memories
            relevant_memories = get_relevant_memory(user_msg, n=5)
            
            # Create enhanced system prompt with memories
            original_system_prompt = self.session_history[0]["content"]
            if relevant_memories:
                memory_context = "\n\nRelevant memories from previous conversations:\n" + "\n".join([f"- {memory}" for memory in relevant_memories])
                enhanced_system_prompt = original_system_prompt + memory_context
            else:
                enhanced_system_prompt = original_system_prompt
            
            # Create temporary session with enhanced prompt
            temp_session = [{"role": "system", "content": enhanced_system_prompt}]
            temp_session.extend(self.session_history[1:])
            temp_session.append({"role": "user", "content": f"user_says: {user_msg}"})
            
            # Get AI response
            ai_response = self.query_mistral(temp_session)
            
            # Add to main session history
            self.session_history.append({"role": "user", "content": f"user_says: {user_msg}"})
            self.session_history.append({"role": "assistant", "content": ai_response})
            
            # Parse and handle AI response
            talk_lines, needs_followup = self.parse_ai_response(ai_response, enhanced_system_prompt)
            
            # Handle follow-up if needed (for search results, email updates)
            if needs_followup:
                temp_followup = [{"role": "system", "content": enhanced_system_prompt}]
                temp_followup.extend(self.session_history[1:])
                
                followup_response = self.query_mistral(temp_followup)
                self.session_history.append({"role": "assistant", "content": followup_response})
                
                followup_talk_lines, _ = self.parse_ai_response(followup_response, enhanced_system_prompt)
                talk_lines = followup_talk_lines
            
            # Send response to frontend
            if talk_lines:
                response_text = "\n\n".join(talk_lines)
            else:
                print("")

                #response_text = "Sorry, I couldn't understand the response."
            
            # Display raw AI response
            print(f"\n{'-'*60}")
            print(f"🤖 AI RESPONSE: {response_text}")
            print(f"{'-'*60}\n")
                
            self.socketio.emit('receive_message', {
                'sender': 'Eva',
                'message': response_text,
                'is_user': False
            })
            
        except Exception as e:
            print(f"❌ Error processing message: {e}")
            # Let the AI know why its response failed
            feedback_msg = (
                "Your previous response was rejected because you did not use the <t> <t/> tool. "
                "Please rewrite your answer using the correct format."
            )

            # Create a follow-up session for correction
            correction_session = [{"role": "system", "content": enhanced_system_prompt}]
            correction_session.extend(self.session_history[1:])
            correction_session.append({"role": "user", "content": feedback_msg})

            try:
                correction_response = self.query_mistral(correction_session)
                self.session_history.append({"role": "assistant", "content": correction_response})

                correction_talk_lines, _ = self.parse_ai_response(correction_response, enhanced_system_prompt)
                response_text = "\n\n".join(correction_talk_lines) if correction_talk_lines else "Response format issue."

                self.socketio.emit('receive_message', {
                    'sender': 'Eva',
                    'message': response_text,
                    'is_user': False
                })
            except Exception as correction_err:
                print(f"❌ Correction also failed: {correction_err}")
                self.socketio.emit('receive_message', {
                    'sender': 'Eva',
                    'message': "Sorry, I couldn't get a valid response. Please try again.",
                    'is_user': False
                })

        finally:
            self.processing_message = False 

    def parse_ai_response(self, response_text, enhanced_system_prompt=None):
        """Parse AI response and handle tools - FIXED VERSION"""
        talk_lines = []
        needs_followup = False
        
        # Capture all print statements and send them to API
        # This allows Eva to respond to system outputs like task creation, calendar events, etc.
        captured_outputs = []
        
        # Extract talk content - THIS IS THE KEY FIX
        talk_pattern = re.compile(r'<t>(.+?)</t>', re.IGNORECASE | re.DOTALL)
        talk_matches = talk_pattern.findall(response_text)
        talk_lines = [match.strip() for match in talk_matches]  # Clean up whitespace
        
        # Show extracted talk lines count only
        print(f"📝 Extracted {len(talk_lines)} response lines")
        
        # Handle memory storage
        memory_pattern = re.compile(r'<m>(.+?)</m>', re.IGNORECASE | re.DOTALL)
        memory_lines = memory_pattern.findall(response_text)
        if memory_lines:
            print(f"💾 Storing {len(memory_lines)} memories")
            current_time = datetime.now().strftime("%A, %B %d %Y | %I:%M %p")
            for memory_line in memory_lines:  # Process all memory entries
                save_memory(current_time, memory_line)
        
        # Handle web search - Process ALL search queries
        search_pattern = re.compile(r'<s>(.+?)</s>', re.IGNORECASE | re.DOTALL)
        search_lines = search_pattern.findall(response_text)
        if search_lines:
            print(f"🔍 Using search tool ({len(search_lines)} queries)")
            for search_query in search_lines:
                search_result = search_web(search_query, limit=6)
                captured_outputs.append(f"search_result: {search_result}")
                self.session_history.append({  # FIXED: was session_history
                    "role": "user",
                    "content": f"search_result: {search_result}"
                })
            needs_followup = True

        # Handle Open applications - Process ALL apps
        app_pattern = re.compile(r'<o>(.+?)</o>', re.IGNORECASE | re.DOTALL)
        app_names = app_pattern.findall(response_text)
        if app_names:
            print(f"🚀 Opening {len(app_names)} apps")
            for app_name in app_names:
                result = open_app(app_name)
                if result and "App not found" in result:
                    captured_outputs.append(result)

        # Handle Telegram messages - Process ALL messages
        telegram_pattern = re.compile(r'<tg>(.+?)</tg>', re.IGNORECASE | re.DOTALL)
        telegram_lines = telegram_pattern.findall(response_text)
        if telegram_lines:
            print(f"📱 Sending {len(telegram_lines)} Telegram messages")
            for message in telegram_lines:
                Send_telegram_message(message.strip())

        # ===========EMAIL FUNCTIONALITY============
        # Handle email sending - Process ALL emails
        send_email_pattern = re.compile(r'<sm>\s*(.*?)\s*</sm>', re.IGNORECASE | re.DOTALL)
        send_emails = send_email_pattern.findall(response_text)
        if send_emails:
            print(f"📧 Sending {len(send_emails)} emails")
            for email_data in send_emails:
                result = send_email_from_string(email_data)
                self.last_email_sent_time = time.time()
                captured_outputs.append(result)

        # Handle read email - Process ALL emails
        read_email_pattern = re.compile(r'<rm>(.+?)</rm>', re.IGNORECASE | re.DOTALL)
        read_emails = read_email_pattern.findall(response_text)
        if read_emails:
            print(f"📬 Marking {len(read_emails)} emails as read")
            for email_id in read_emails:
                pass
            result = mark_email_as_read(read_emails[0])
            captured_outputs.append(result)

        # =========== TASK FUNCTIONALITY============
        # 1. TASK UPDATE - Get current tasks

        task_pattern = re.compile(r'<task_update>', re.IGNORECASE | re.DOTALL)
        if task_pattern.search(response_text):
            print("📋 Getting tasks from all lists")
            
            # Get all task lists first
            all_task_lists = tasklists_get_all()
            
            all_formatted_tasks = []
            
            # Iterate through each task list
            for task_list in all_task_lists:
                list_id = task_list['id']
                list_title = task_list['title']
                
                # Get tasks from this specific list
                tasks_in_list = tasks_get_all(list_id)
                
                # Format tasks from this list
                for task in tasks_in_list:
                    status = "✅" if task.get('status') == 'completed' else "⭕"
                    due_info = ""
                    if task.get('due'):
                        try:
                            due_date = parser.isoparse(task['due']).strftime('%Y-%m-%d %H:%M')
                            due_info = f" | Due: {due_date}"
                        except:
                            due_info = f" | Due: {task.get('due')}"
                    
                    formatted_task = {
                        'id': task.get('id'),
                        'title': task.get('title'),
                        'status': task.get('status', 'needsAction'),
                        'due': task.get('due'),
                        'notes': task.get('notes'),
                        'list_name': list_title,  # Add list name
                        'list_id': list_id,       # Add list ID
                        'display': f"{status} {task.get('title', 'Untitled')} [{list_title}]{due_info}"
                    }
                    all_formatted_tasks.append(formatted_task)
            
            print(f"📋 Found {len(all_formatted_tasks)} tasks across {len(all_task_lists)} lists")
            
            # Group tasks by list for better organization
            tasks_by_list = {}
            for task in all_formatted_tasks:
                list_name = task['list_name']
                if list_name not in tasks_by_list:
                    tasks_by_list[list_name] = []
                tasks_by_list[list_name].append(task)
            
            # Create a summary for Eva
            task_summary = []
            for list_name, tasks in tasks_by_list.items():
                completed_count = len([t for t in tasks if t['status'] == 'completed'])
                pending_count = len([t for t in tasks if t['status'] == 'needsAction'])
                task_summary.append(f"📚 {list_name}: {pending_count} pending, {completed_count} completed")
            
            captured_outputs.append(f"task_update detected - Found {len(all_formatted_tasks)} tasks across {len(all_task_lists)} lists")
            captured_outputs.append(f"Task summary: {'; '.join(task_summary)}")
            captured_outputs.append(f"All tasks: {all_formatted_tasks}")
            
            self.session_history.append({
                "role": "user",
                "content": f"Current tasks from all lists: {all_formatted_tasks}"
            })
            needs_followup = True
        # 2. CREATE TASKS - Process ALL task creations
        set_task_pattern = re.compile(r'<ct>(.+?)</ct>', re.IGNORECASE | re.DOTALL)
        task_creates = set_task_pattern.findall(response_text)
        if task_creates:
            print(f"✅ Creating {len(task_creates)} tasks")
            for task_match in task_creates:
                pass
                try:
                    # Parse the task format: Title | Due Date | Notes | TaskList
                    parts = [p.strip() for p in task_match.split('|')]
                    title = parts[0] if parts[0] else "Untitled Task"
                    due = None
                    notes = None
                    tasklist_id = '@default'

                    # Handle due date (parts[1])
                    if len(parts) > 1 and parts[1]:
                        try:
                            # If already in RFC3339 format
                            if 'T' in parts[1] and ('Z' in parts[1] or '+' in parts[1]):
                                due = parts[1]
                            else:
                                # Try to parse various date formats
                                try:
                                    # YYYY-MM-DD HH:MM format
                                    dt = datetime.strptime(parts[1], "%Y-%m-%d %H:%M")
                                    due = dt.isoformat() + "Z"
                                except ValueError:
                                    try:
                                        # YYYY-MM-DD format
                                        dt = datetime.strptime(parts[1], "%Y-%m-%d")
                                        due = dt.isoformat() + "Z"
                                    except ValueError:
                                        clean_print(f"Could not parse date: {parts[1]}", "ERROR")
                        except Exception as e:
                            clean_print(f"Date parsing error: {e}", "ERROR")

                    # Handle notes (parts[2])
                    if len(parts) > 2 and parts[2]:
                        notes = parts[2]

                    # Handle tasklist (parts[3]) - optional
                    if len(parts) > 3 and parts[3]:
                        # Try to find tasklist by name
                        found_list = tasklist_get_by_name(parts[3])
                        if found_list:
                            tasklist_id = found_list['id']
                        else:
                            # Auto-create the list if it doesn't exist
                            print(f"Tasklist '{parts[3]}' not found, creating it...")
                            new_list = tasklist_create(parts[3])
                            if new_list:
                                tasklist_id = new_list['id']
                                captured_outputs.append(f"📚 Auto-created tasklist: {parts[3]}")
                            else:
                                print(f"Failed to create tasklist '{parts[3]}', using default")

                    result = tasks_add(title, tasklist_id, due, notes)
                    if result:
                        success_msg = f"✅ Task created: {title}"
                        if due:
                            success_msg += f" (Due: {due})"
                        print(success_msg)
                        captured_outputs.append(success_msg)
                    else:
                        error_msg = f"❌ Failed to create task: {title}"
                        print(error_msg)
                        captured_outputs.append(error_msg)
                        
                except Exception as e:
                    error_msg = f"❌ Error creating task: {e}"
                    print(error_msg)
                    captured_outputs.append(error_msg)

        # 3. REMOVE TASKS - Process ALL task removals
        remove_task_pattern = re.compile(r'<rt>(.+?)</rt>', re.IGNORECASE | re.DOTALL)
        remove_tasks = remove_task_pattern.findall(response_text)
        if remove_tasks:
            print(f"🗑️ Eva is using REMOVE TASK tool ({len(remove_tasks)} tasks)")
            for task_id in remove_tasks:
                task_id = task_id.strip()
                print(f"   Removing task: {task_id}")
                try:
                    success = task_delete(task_id)  # Use your enhanced function
                    if success:
                        success_msg = f"✅ Task removed: {task_id}"
                        print(success_msg)
                        captured_outputs.append(success_msg)
                    else:
                        error_msg = f"❌ Failed to remove task: {task_id}"
                        print(error_msg)
                        captured_outputs.append(error_msg)
                except Exception as e:
                    error_msg = f"❌ Error removing task: {e}"
                    print(error_msg)
                    captured_outputs.append(error_msg)

        # 4. MARK TASKS AS DONE - New tool
        done_task_pattern = re.compile(r'<dt>(.+?)</dt>', re.IGNORECASE | re.DOTALL)
        done_tasks = done_task_pattern.findall(response_text)
        if done_tasks:
            print(f"✅ Eva is using MARK DONE tool ({len(done_tasks)} tasks)")
            for task_id in done_tasks:
                task_id = task_id.strip()
                print(f"   Marking task as done: {task_id}")
                try:
                    result = task_mark_done(task_id)
                    if result:
                        success_msg = f"✅ Task marked as done: {task_id}"
                        print(success_msg)
                        captured_outputs.append(success_msg)
                    else:
                        error_msg = f"❌ Failed to mark task as done: {task_id}"
                        print(error_msg)
                        captured_outputs.append(error_msg)
                except Exception as e:
                    error_msg = f"❌ Error marking task as done: {e}"
                    print(error_msg)
                    captured_outputs.append(error_msg)

        # 5. MARK TASKS AS UNDONE - New tool
        undone_task_pattern = re.compile(r'<ut>(.+?)</ut>', re.IGNORECASE | re.DOTALL)
        undone_tasks = undone_task_pattern.findall(response_text)
        if undone_tasks:
            print(f"↩️ Eva is using MARK UNDONE tool ({len(undone_tasks)} tasks)")
            for task_id in undone_tasks:
                task_id = task_id.strip()
                print(f"   Marking task as undone: {task_id}")
                try:
                    result = task_mark_undone(task_id)
                    if result:
                        success_msg = f"↩️ Task marked as undone: {task_id}"
                        print(success_msg)
                        captured_outputs.append(success_msg)
                    else:
                        error_msg = f"❌ Failed to mark task as undone: {task_id}"
                        print(error_msg)
                        captured_outputs.append(error_msg)
                except Exception as e:
                    error_msg = f"❌ Error marking task as undone: {e}"
                    print(error_msg)
                    captured_outputs.append(error_msg)

        # 6. SEARCH TASKS BY TITLE - New tool
        search_task_pattern = re.compile(r'<st>(.+?)</st>', re.IGNORECASE | re.DOTALL)
        search_queries = search_task_pattern.findall(response_text)
        if search_queries:
            print(f"🔍 Eva is using SEARCH TASK tool ({len(search_queries)} searches)")
            for query in search_queries:
                query = query.strip()
                print(f"   Searching for task: {query}")
                try:
                    found_task = task_get_by_title(query)
                    if found_task:
                        success_msg = f"🔍 Found task: {found_task['title']} (ID: {found_task['id']})"
                        print(success_msg)
                        captured_outputs.append(success_msg)
                        self.session_history.append({  # FIXED: was session_history
                            "role": "user",
                            "content": f"Found task: {found_task}"
                        })
                    else:
                        not_found_msg = f"🔍 No task found with title: {query}"
                        print(not_found_msg)
                        captured_outputs.append(not_found_msg)
                except Exception as e:
                    error_msg = f"❌ Error searching for task: {e}"
                    print(error_msg)
                    captured_outputs.append(error_msg)

        # 7. CREATE TASKLIST - New tool
        create_list_pattern = re.compile(r'<cl>(.+?)</cl>', re.IGNORECASE | re.DOTALL)
        create_lists = create_list_pattern.findall(response_text)
        if create_lists:
            print(f"📚 Eva is using CREATE TASKLIST tool ({len(create_lists)} lists)")
            for list_title in create_lists:
                list_title = list_title.strip()
                print(f"   Creating tasklist: {list_title}")
                try:
                    result = tasklist_create(list_title)
                    if result:
                        success_msg = f"📚 Tasklist created: {list_title} (ID: {result['id']})"
                        print(success_msg)
                        captured_outputs.append(success_msg)
                    else:
                        error_msg = f"❌ Failed to create tasklist: {list_title}"
                        print(error_msg)
                        captured_outputs.append(error_msg)
                except Exception as e:
                    error_msg = f"❌ Error creating tasklist: {e}"
                    print(error_msg)
                    captured_outputs.append(error_msg)

        # =========== CALENDAR FUNCTIONALITY============
        # Get calendar events - with user feedback
        calendar_pattern = re.compile(r'<calendar_update>', re.IGNORECASE | re.DOTALL)
        if calendar_pattern.search(response_text):
            print("calendar_update detected")
            events_list = calendar_get_upcoming_events(limit=10)
            captured_outputs.append(f"calendar_update detected")
            captured_outputs.append(f"calendar events: {events_list}")
            self.session_history.append({  # FIXED: was session_history
                "role": "user",
                "content": f"calendar events: {events_list}"
            })
            needs_followup = True

        # Create calendar events - Process ALL event creations
        calendar_event_pattern = re.compile(r'<ce>(.+?)</ce>', re.IGNORECASE | re.DOTALL)
        calendar_events = calendar_event_pattern.findall(response_text)
        if calendar_events:
            print(f"📅 Eva is using CREATE CALENDAR EVENT tool ({len(calendar_events)} events)")
            for event_text in calendar_events:
                print(f"   Creating event: {event_text}")
                try:
                    # Parse event creation logic here...
                    # (keeping the existing calendar event creation code)
                    event_parts = event_text.strip().split(' due ')
                    if len(event_parts) < 2:
                        raise ValueError("Invalid format. Use 'due' to separate title from date/time.")
                    
                    title = event_parts[0].strip()
                    datetime_part = event_parts[1].strip()

                    time_parts = datetime_part.split(' to ')
                    if len(time_parts) < 2:
                        raise ValueError("Invalid format. Use 'to' to specify the end time.")

                    start_str = time_parts[0].strip()
                    end_and_zone_str = time_parts[1].strip()

                    last_space_index = end_and_zone_str.rfind(' ')
                    if last_space_index == -1:
                        raise ValueError("Could not find timezone.")
                    
                    end_time_str = end_and_zone_str[:last_space_index].strip()
                    timezone = end_and_zone_str[last_space_index + 1:].strip()

                    if len(end_time_str.split()) == 1:
                        date_str = start_str.split(' ')[0]
                        end_datetime_iso = f"{date_str}T{end_time_str}"
                    else:
                        end_datetime_iso = end_time_str.replace(' ', 'T')

                    start_datetime_iso = start_str.replace(' ', 'T')

                    event_details = {
                        'summary': title,
                        'start': {
                            'dateTime': start_datetime_iso,
                            'timeZone': timezone,
                        },
                        'end': {
                            'dateTime': end_datetime_iso,
                            'timeZone': timezone,
                        },
                    }
                    
                    result = calendar_set_event(event_details)
                    if result:
                        success_msg = f"✅ Calendar event created: {title}"
                        print(success_msg)
                        captured_outputs.append(success_msg)
                    else:
                        error_msg = f"❌ Failed to create calendar event: {title}"
                        print(error_msg)
                        captured_outputs.append(error_msg)

                except Exception as e:
                    error_msg = f"❌ Error parsing calendar event: {e}"
                    print(error_msg)
                    captured_outputs.append(error_msg)

        # Remove calendar events - Process ALL event removals
        remove_event_pattern = re.compile(r'<re>(.+?)</re>', re.IGNORECASE | re.DOTALL)
        remove_events = remove_event_pattern.findall(response_text)
        if remove_events:
            print(f"🗑️ Eva is using REMOVE CALENDAR EVENT tool ({len(remove_events)} events)")
            for event_id in remove_events:
                print(f"   Removing event: {event_id}")
                try:
                    get_calendar_service().events().delete(calendarId='primary', eventId=event_id.strip()).execute()
                    success_msg = f"✅ Calendar event removed: {event_id}"
                    print(success_msg)
                    captured_outputs.append(success_msg)
                except Exception as e:
                    error_msg = f"❌ Error removing calendar event: {e}"
                    print(error_msg)
                    captured_outputs.append(error_msg)
        
        # Send all captured outputs to the API as user input
        if captured_outputs:
            # Join all outputs into a single message
            combined_output = "\n".join(captured_outputs)
            
            # Add to session history as user input
            self.session_history.append({
                "role": "user",
                "content": f"System outputs: {combined_output}"
            })
            
            # Set needs_followup to True so Eva can respond to these outputs
            needs_followup = True
        


        # =========== ALARM FUNCTIONALITY ============
        # 1. SET ALARM - Process ALL alarm creations
        set_alarm_pattern = re.compile(r'<sa>(.+?)</sa>', re.IGNORECASE | re.DOTALL)
        set_alarms = set_alarm_pattern.findall(response_text)
        if set_alarms:
            print(f"⏰ Eva is using SET ALARM tool ({len(set_alarms)} alarms)")
            for alarm_data in set_alarms:
                print(f"   Setting alarm: {alarm_data}")
                try:
                    # Parse format: alarm_name | alarm_time | description | recurring (optional)
                    parts = [p.strip() for p in alarm_data.split('|')]
                    alarm_name = parts[0] if parts[0] else "Unnamed Alarm"
                    alarm_time = parts[1] if len(parts) > 1 else None
                    description = parts[2] if len(parts) > 2 else ""
                    recurring = parts[3] if len(parts) > 3 else "none"
                    
                    if not alarm_time:
                        error_msg = "❌ Alarm time not specified"
                        #print(error_msg)
                        captured_outputs.append(error_msg)
                        self.session_history.append({  # FIXED: was session_history
                            "role": "user",
                            "content": f"alarm_error: {error_msg}"
                        })
                        needs_followup = True
                        continue
                    
                    result = self.alarm_system.set_alarm(alarm_name, alarm_time, description, recurring)
                    if result["success"]:
                        recurring_text = f" (recurring {result.get('recurring', 'none')})" if result.get('recurring') != "none" else " (one-time)"
                        success_msg = f"⏰ Alarm set: {alarm_name} at {result['time']}{recurring_text}"
                        #print(success_msg)
                        captured_outputs.append(success_msg)

                        self.session_history.append({  # FIXED: was session_history
                            "role": "user",
                            "content": f"alarm_success: {success_msg}"
                        })
                        needs_followup = True
                    else:
                        error_msg = f"❌ Failed to set alarm: {result['error']}"
                        print(error_msg)
                        captured_outputs.append(error_msg)
                        self.session_history.append({  # FIXED: was session_history
                            "role": "user",
                            "content": f"alarm_error: {error_msg}"
                        })
                        needs_followup = True                       
                        
                except Exception as e:
                    error_msg = f"❌ Error setting alarm: {e}"
                    print(error_msg)
                    captured_outputs.append(error_msg)
                    captured_outputs.append(error_msg)
                    self.session_history.append({  # FIXED: was session_history
                        "role": "user",
                        "content": f"search_result: {error_msg}"
                    })
                    needs_followup = True 

        # 2. REMOVE ALARM - Process ALL alarm removals
        remove_alarm_pattern = re.compile(r'<ra>(.+?)</ra>', re.IGNORECASE | re.DOTALL)
        remove_alarms = remove_alarm_pattern.findall(response_text)
        if remove_alarms:
            print(f"🗑️ Eva is using REMOVE ALARM tool ({len(remove_alarms)} alarms)")
            for alarm_identifier in remove_alarms:
                alarm_identifier = alarm_identifier.strip()
                print(f"   Removing alarm: {alarm_identifier}")
                try:
                    result = self.alarm_system.remove_alarm(alarm_identifier)
                    if result["success"]:
                        success_msg = f"🗑️ Alarm removed: {result['removed_alarm']}"
                        print(success_msg)
                        captured_outputs.append(success_msg)
                    else:
                        error_msg = f"❌ Failed to remove alarm: {result['error']}"
                        print(error_msg)
                        captured_outputs.append(error_msg)
                except Exception as e:
                    error_msg = f"❌ Error removing alarm: {e}"
                    print(error_msg)
                    captured_outputs.append(error_msg)

        # 3. LIST ALARMS - Get all active alarms
        list_alarms_pattern = re.compile(r'<alarm_list>', re.IGNORECASE | re.DOTALL)
        if list_alarms_pattern.search(response_text):
            print("📋 Eva is using LIST ALARMS tool")
            try:
                result = self.alarm_system.list_alarms()
                if result["success"]:
                    if result["alarms"]:
                        alarm_info = f"Active alarms: {result['alarms']}"
                        print(f"📋 {len(result['alarms'])} active alarms found")
                        captured_outputs.append(alarm_info)
                        self.session_history.append({
                            "role": "user",
                            "content": f"Current alarms: {result['alarms']}"
                        })
                    else:
                        no_alarms_msg = "📋 No active alarms"
                        print(no_alarms_msg)
                        captured_outputs.append(no_alarms_msg)
                needs_followup = True
            except Exception as e:
                error_msg = f"❌ Error listing alarms: {e}"
                print(error_msg)
                captured_outputs.append(error_msg)
        
        return talk_lines, needs_followup

    def process_alarm_notification(self, alarm_message):
        """Process alarm notification"""
        try:
            # Get relevant memories
            relevant_memories = get_relevant_memory(alarm_message, n=3)
            
            # Create enhanced system prompt with memories
            original_system_prompt = self.session_history[0]["content"]
            if relevant_memories:
                memory_context = "\n\nRelevant memories from previous conversations:\n" + "\n".join([f"- {memory}" for memory in relevant_memories])
                enhanced_system_prompt = original_system_prompt + memory_context
            else:
                enhanced_system_prompt = original_system_prompt
            
            # Create temporary session with enhanced prompt
            temp_session = [{"role": "system", "content": enhanced_system_prompt}]
            temp_session.extend(self.session_history[1:])
            
            # Get AI response
            ai_response = self.query_mistral(temp_session)
            self.session_history.append({"role": "assistant", "content": ai_response})
            
            # Parse response
            talk_lines, needs_followup = self.parse_ai_response(ai_response, enhanced_system_prompt)
            
            # Handle follow-up if needed
            if needs_followup:
                temp_followup = [{"role": "system", "content": enhanced_system_prompt}]
                temp_followup.extend(self.session_history[1:])
                
                followup_response = self.query_mistral(temp_followup)
                self.session_history.append({"role": "assistant", "content": followup_response})
                
                followup_talk_lines, _ = self.parse_ai_response(followup_response, enhanced_system_prompt)
                talk_lines = followup_talk_lines
            
            # Send response to web interface
            if talk_lines:
                response_text = "\n\n".join(talk_lines)
                self.socketio.emit('receive_message', {
                    'sender': 'Eva',
                    'message': f"🚨 ALARM: {response_text}",
                    'is_user': False
                })
                
                # Also send to Telegram if available
                Send_telegram_message(f"🚨 ALARM: {response_text}")
            
        except Exception as e:
            print(f"Error processing alarm notification: {e}")
            # Send fallback message
            fallback_message = f"🚨 ALARM TRIGGERED: {alarm_message}"
            self.socketio.emit('receive_message', {
                'sender': 'Eva',
                'message': fallback_message,
                'is_user': False
            })
            Send_telegram_message(fallback_message)

    def process_telegram_message(self, telegram_message):
        """Process Telegram message notification"""
        try:
            # Get relevant memories
            relevant_memories = get_relevant_memory(telegram_message, n=5)
            
            # Create enhanced system prompt with memories
            original_system_prompt = self.session_history[0]["content"]
            if relevant_memories:
                memory_context = "\n\nRelevant memories from previous conversations:\n" + "\n".join([f"- {memory}" for memory in relevant_memories])
                enhanced_system_prompt = original_system_prompt + memory_context
            else:
                enhanced_system_prompt = original_system_prompt
            
            # Create temporary session with enhanced prompt
            temp_session = [{"role": "system", "content": enhanced_system_prompt}]
            temp_session.extend(self.session_history[1:])
            
            # Get AI response
            ai_response = self.query_mistral(temp_session)
            self.session_history.append({"role": "assistant", "content": ai_response})
            
            # Parse response and handle any follow-up
            talk_lines, needs_followup = self.parse_ai_response(ai_response, enhanced_system_prompt)
            
            # Handle follow-up if needed
            if needs_followup:
                temp_followup = [{"role": "system", "content": enhanced_system_prompt}]
                temp_followup.extend(self.session_history[1:])
                
                followup_response = self.query_mistral(temp_followup)
                self.session_history.append({"role": "assistant", "content": followup_response})
                
                followup_talk_lines, _ = self.parse_ai_response(followup_response, enhanced_system_prompt)
                talk_lines = followup_talk_lines
            
            # For Telegram messages, only send to web interface (not back to Telegram)
            # The <tg> content was already sent by parse_ai_response
            if talk_lines:
                response_text = "\n\n".join(talk_lines)
                
                # Send to web interface only
                self.socketio.emit('receive_message', {
                    'sender': 'Eva',
                    'message': response_text,
                    'is_user': False
                })
                
                # DO NOT send back to Telegram - <tg> content was already handled
                
        except Exception as e:
            print(f"Error processing Telegram message: {e}")
            error_msg = "Sorry, I'm having issues processing your message."
            Send_telegram_message(error_msg)
    
    def process_alarm_notification(self, alarm_message):
        """Process alarm notification (add this to ChatApp class)"""
        try:
            # Get relevant memories
            relevant_memories = get_relevant_memory(alarm_message, n=3)
            
            # Create enhanced system prompt with memories
            original_system_prompt = self.session_history[0]["content"]
            if relevant_memories:
                memory_context = "\n\nRelevant memories from previous conversations:\n" + "\n".join([f"- {memory}" for memory in relevant_memories])
                enhanced_system_prompt = original_system_prompt + memory_context
            else:
                enhanced_system_prompt = original_system_prompt
            
            # Create temporary session with enhanced prompt
            temp_session = [{"role": "system", "content": enhanced_system_prompt}]
            temp_session.extend(self.session_history[1:])
            
            # Get AI response
            ai_response = self.query_mistral(temp_session)
            self.session_history.append({"role": "assistant", "content": ai_response})
            
            # Parse response
            talk_lines, needs_followup = self.parse_ai_response(ai_response, enhanced_system_prompt)
            

            # Send response to web interface
            if talk_lines:
                response_text = "\n\n".join(talk_lines)
                self.socketio.emit('receive_message', {
                    'sender': 'Eva',
                    'message': f"{response_text}",
                    'is_user': False
                })
                
                # Also send to Telegram if available
                #Send_telegram_message(f"🚨 ALARM: {response_text}")

            # Handle follow-up if needed
            if needs_followup:
                temp_followup = [{"role": "system", "content": enhanced_system_prompt}]
                temp_followup.extend(self.session_history[1:])
                
                followup_response = self.query_mistral(temp_followup)
                self.session_history.append({"role": "assistant", "content": followup_response})
                
                followup_talk_lines, _ = self.parse_ai_response(followup_response, enhanced_system_prompt)
                talk_lines = followup_talk_lines


            

            
        except Exception as e:
            print(f"Error processing alarm notification: {e}")
            # Send fallback message
            fallback_message = f"🚨 ALARM TRIGGERED: {alarm_message}"
            self.socketio.emit('receive_message', {
                'sender': 'Eva',
                'message': fallback_message,
                'is_user': False
            })
            Send_telegram_message(fallback_message)

    def query_mistral(self, messages):
        """Query Mistral AI API with retry logic for rate limits."""
        max_retries = 5
        retries = 0
        while retries < max_retries:
            try:
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Prepend system time to every conversation
                time_message = {
                    "role": "system",
                    "content": f"The current date and time is {current_time}."
                }
                messages_with_time = [time_message] + messages


                
                # Show only the latest user input
                last_user_message = ""
                for m in reversed(messages):
                    if m["role"] == "user":
                        last_user_message = m["content"]
                        break
                # Display raw user input
                print(f"\n{'='*60}")
                print(f"INPUT: {last_user_message}")
                print(f"{'='*60}\n")
                
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {MISTRAL_API_KEY}"
                }
                payload = {
                    "model": MODEL,
                    "messages": messages_with_time
                }
                response = requests.post(MISTRAL_ENDPOINT, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()


                

                # Extract assistant reply
                assistant_reply = data["choices"][0]["message"]["content"]
                # Display raw AI response
                print(f"\n{'-'*60}")
                print(f"🤖 RAW AI RESPONSE: {assistant_reply}")
                print(f"{'-'*60}\n")

                return assistant_reply
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    retries += 1
                    sleep_time = 2 ** retries  # Exponential back-off
                    print(f"⚠️  Mistral API rate limit hit. Retrying in {sleep_time} seconds... (Attempt {retries}/{max_retries})")
                    time.sleep(sleep_time)
                    continue  
                else:
                    print(f"❌ Mistral API HTTP error: {e}")
                    return f"<t>❌Sorry, I couldn't reach the AI service due to Mistral API HTTP error: {e}</t>"
            except Exception as e:
                print(f"❌ Mistral API error: {e}")
                return f"<t>❌ Mistral API error: {e}</t>"
                
        print(f"❌ Failed to get Mistral API response after {max_retries} retries due to rate limiting.")
        return f"<t>❌ Failed to get Mistral API response after {max_retries} retries due to rate limiting.</t>"
        
    def start_email_monitoring(self):
        """Start email monitoring in background"""
        last_email_processing = 0
        def email_monitor():
            while True:
                try:
                    if not hasattr(self, 'last_email_processing'):
                        self.last_email_processing = 0
                    # Skip if email was recently sent
                    if time.time() - self.last_email_sent_time < 30:
                        time.sleep(15)
                        continue
                    
                    msg_id, email_update = get_latest_unread_email(return_id=True)
                    
                    if msg_id and msg_id != self.last_email_id:
                        if time.time() - self.last_email_processing < 30:  # 30 second cooldown
                            time.sleep(15)
                            continue
                            
                        self.last_email_processing = time.time()
                        self.last_email_id = msg_id
                        clean_print("New email detected!", "SYSTEM")
                        clean_print(email_update, "SYSTEM")
                        
                        # Add to session history
                        self.session_history.append({
                            "role": "user",
                            "content": f"New arrival email: {email_update}"
                        })
                        
                        # Process the email notification
                        threading.Thread(target=self.process_email_notification, args=(email_update,), daemon=True).start()
                    
                    time.sleep(15)  # Check every 15 seconds
                except Exception as e:
                    clean_print(f"Email monitoring error: {e}", "ERROR")
                    time.sleep(30)
        
        threading.Thread(target=email_monitor, daemon=True).start()
    
    def process_email_notification(self, email_update):
        """Process new email notification"""
        try:
            # Get AI response for email notification
            temp_session = self.session_history.copy()
            ai_response = self.query_mistral(temp_session)
            
            self.session_history.append({"role": "assistant", "content": ai_response})
            
            # Parse response
            talk_lines, _ = self.parse_ai_response(ai_response)
            
            if talk_lines:
                response_text = "\n\n".join(talk_lines)
                self.socketio.emit('receive_message', {
                    'sender': 'Eva',
                    'message': response_text,
                    'is_user': False
                })
        except Exception as e:
            clean_print(f"Error processing email notification: {e}", "ERROR")

def run_flask():
    global chatbot_instance
    chatbot_instance = ChatApp()
    chatbot_instance.socketio.run(chatbot_instance.app, port=5000, debug=False)

if __name__ == '__main__':
    
    run_gui_setup()
    Config_get_data()



    # Clear terminal and show welcome message
    #clear_terminal()
    clean_print("Eva AI Desktop Assistant Starting...", "SYSTEM")
    clean_print("Initializing services and connections...", "SYSTEM")
    
    # Test calendar connection first
    clean_print("Testing calendar connection...", "SYSTEM")
    test_calendar_connection()
    
    # Start Telegram bot in background thread
    threading.Thread(target=telegram, daemon=True).start()
    
    # Start Flask in background thread
    threading.Thread(target=run_flask, daemon=True).start()
    
    clean_print("All services started successfully!", "SUCCESS")
    clean_print("Eva is ready to assist you!", "SUCCESS")
    
    # Telegram bot testing instructions
    clean_print("To test Telegram bot:", "SYSTEM")
    clean_print("1. Send /start to your bot in Telegram", "SYSTEM")
    clean_print("2. Use /test to send a test message", "SYSTEM")
    clean_print("3. Use /status to check bot status", "SYSTEM")
    clean_print("4. The bot can now send proactive messages!", "SYSTEM")
    
    window = webview.create_window(
        'Eva AI Desktop',
        f'http://localhost:5000',
        width=1000,
        height=700,
        resizable=True,
        text_select=True,
        confirm_close=True
    )

    webview.start()
