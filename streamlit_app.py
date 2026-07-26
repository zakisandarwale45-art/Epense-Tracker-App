import streamlit as st
import os
import uuid
import hashlib
import secrets
import time
import base64
import requests
import pandas as pd
from datetime import datetime
from collections import defaultdict

st.set_page_config(page_title="Expense Tracker", page_icon="💰", layout="centered")

st.markdown("""
<style>
.chat-bubble-user {
    background-color: #DCF8C6;
    color: #1a1a1a;
    padding: 10px 14px;
    border-radius: 16px 16px 4px 16px;
    margin: 6px 0;
    max-width: 85%;
    margin-left: auto;
    font-size: 15px;
}
.chat-bubble-ai {
    background-color: #F1F0F0;
    color: #1a1a1a;
    padding: 10px 14px;
    border-radius: 16px 16px 16px 4px;
    margin: 6px 0;
    max-width: 85%;
    margin-right: auto;
    font-size: 15px;
}
</style>
""", unsafe_allow_html=True)

GEMINI_MODEL = "gemini-flash-latest"

AI_SYSTEM_INSTRUCTION = """You are a helpful assistant embedded inside a personal Expense Tracker app.
Only answer questions related to: the user's income/expenses, budgeting, spending categories,
financial habits based on the data provided, or how to use this app's features
(Add Income/Expense, Balance, History, Monthly Report, Budget limits, Recurring transactions, Settings).
If the user asks anything unrelated to their finances or this app, politely decline and steer them
back to asking about their expenses or the app. Keep answers short, friendly, and match the user's
language style (Hindi, Hinglish, or English - whichever they use). If the input is audio, first
briefly restate the question you understood, then answer it."""

def build_data_context(username):
    months = get_monthly_data(username)
    budgets = load_budgets(username)
    spend = get_category_spend_this_month(username)
    recent = get_all_transactions(username)[-10:]

    lines = ["Here is the user's current expense data:"]
    lines.append("\nMonthly summary:")
    for m, v in months.items():
        lines.append(f"- {m}: Income ₹{v['income']:.0f}, Expense ₹{v['expense']:.0f}, Balance ₹{v['income']-v['expense']:.0f}")

    if budgets:
        lines.append("\nBudget limits (this month):")
        for cat, limit in budgets.items():
            lines.append(f"- {cat}: limit ₹{limit:.0f}, spent ₹{spend.get(cat,0):.0f}")

    if recent:
        lines.append("\nRecent transactions:")
        for t in recent:
            lines.append(f"- {t[1]} | {t[2]} | ₹{t[3]}")

    return "\n".join(lines)

def call_gemini(api_key, user_text=None, audio_bytes=None, audio_mime=None, data_context=""):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    parts = [{"text": data_context}]
    if user_text:
        parts.append({"text": user_text})
    if audio_bytes:
        parts.append({"inline_data": {"mime_type": audio_mime or "audio/wav", "data": base64.b64encode(audio_bytes).decode()}})

    payload = {
        "system_instruction": {"parts": [{"text": AI_SYSTEM_INSTRUCTION}]},
        "contents": [{"role": "user", "parts": parts}]
    }
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": api_key
    }

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]

users_file = "users.txt"
attempts_file = "login_attempts.txt"

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 120  # 2 minutes
SESSION_TIMEOUT_SECONDS = 600  # 10 minutes of inactivity
MAX_SIGNUPS_PER_SESSION = 3
MAX_USERNAME_LEN = 30
MAX_PASSWORD_LEN = 64
MAX_TEXT_LEN = 100


# ---------- File helpers ----------

def user_file(username):
    return f"expenses_{username}.txt"

def budget_file(username):
    return f"budget_{username}.txt"

def recurring_file(username):
    return f"recurring_{username}.txt"


# ---------- Password Hashing ----------

def hash_value(value, salt):
    return hashlib.sha256((salt + value).encode()).hexdigest()

def make_salt():
    return secrets.token_hex(8)


# ---------- Login Attempt Limiting ----------

def load_attempts():
    attempts = {}
    if os.path.exists(attempts_file):
        with open(attempts_file, "r") as file:
            for line in file:
                parts = line.strip().split(",")
                if len(parts) == 3:
                    attempts[parts[0]] = {"fail_count": int(parts[1]), "locked_until": float(parts[2])}
    return attempts

def save_attempts(attempts):
    with open(attempts_file, "w") as file:
        for uname, info in attempts.items():
            file.write(f"{uname},{info['fail_count']},{info['locked_until']}\n")

def is_locked_out(username):
    attempts = load_attempts()
    info = attempts.get(username)
    if info and info["locked_until"] > time.time():
        remaining = int(info["locked_until"] - time.time())
        return True, remaining
    return False, 0

def record_failed_attempt(username):
    attempts = load_attempts()
    info = attempts.get(username, {"fail_count": 0, "locked_until": 0})
    info["fail_count"] += 1
    if info["fail_count"] >= MAX_FAILED_ATTEMPTS:
        info["locked_until"] = time.time() + LOCKOUT_SECONDS
        info["fail_count"] = 0
    attempts[username] = info
    save_attempts(attempts)

def clear_attempts(username):
    attempts = load_attempts()
    if username in attempts:
        del attempts[username]
        save_attempts(attempts)


# ---------- Auth Helpers ----------
# users.txt format: username|password_hash|password_salt|security_question|answer_hash|answer_salt

def load_users():
    users = {}
    if os.path.exists(users_file):
        with open(users_file, "r") as file:
            for line in file:
                parts = line.rstrip("\n").split("|")
                if len(parts) == 6:
                    users[parts[0]] = {
                        "password_hash": parts[1],
                        "password_salt": parts[2],
                        "security_question": parts[3],
                        "answer_hash": parts[4],
                        "answer_salt": parts[5],
                    }
    return users

def save_user(username, password, security_question, security_answer):
    pwd_salt = make_salt()
    ans_salt = make_salt()
    pwd_hash = hash_value(password, pwd_salt)
    ans_hash = hash_value(security_answer.strip().lower(), ans_salt)
    with open(users_file, "a") as file:
        file.write(f"{username}|{pwd_hash}|{pwd_salt}|{security_question}|{ans_hash}|{ans_salt}\n")

def verify_password(username, password, users):
    info = users.get(username)
    if not info:
        return False
    return hash_value(password, info["password_salt"]) == info["password_hash"]

def verify_security_answer(username, answer, users):
    info = users.get(username)
    if not info:
        return False
    return hash_value(answer.strip().lower(), info["answer_salt"]) == info["answer_hash"]

def update_password(username, new_password):
    users = load_users()
    if username not in users:
        return
    with open(users_file, "w") as file:
        for uname, info in users.items():
            if uname == username:
                pwd_salt = make_salt()
                pwd_hash = hash_value(new_password, pwd_salt)
            else:
                pwd_hash = info["password_hash"]
                pwd_salt = info["password_salt"]
            file.write(f"{uname}|{pwd_hash}|{pwd_salt}|{info['security_question']}|{info['answer_hash']}|{info['answer_salt']}\n")


# ---------- Transaction Logic ----------

def add_transaction(username, t_type, amount):
    now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    tid = uuid.uuid4().hex[:8]
    with open(user_file(username), "a") as file:
        file.write(f"{tid},{now},{t_type},{amount}\n")

def get_all_transactions(username):
    fname = user_file(username)
    if not os.path.exists(fname):
        return []
    with open(fname, "r") as file:
        lines = [l.strip() for l in file if l.strip()]
    return [l.split(",") for l in lines]  # [id, date, type, amount]

def save_all_transactions(username, transactions):
    with open(user_file(username), "w") as file:
        for t in transactions:
            file.write(",".join(t) + "\n")

def delete_transaction(username, tid):
    transactions = get_all_transactions(username)
    transactions = [t for t in transactions if t[0] != tid]
    save_all_transactions(username, transactions)

def update_transaction(username, tid, new_type, new_amount):
    transactions = get_all_transactions(username)
    for t in transactions:
        if t[0] == tid:
            t[2] = new_type
            t[3] = str(new_amount)
    save_all_transactions(username, transactions)

def get_session_lines(username):
    result = []
    for t in get_all_transactions(username):
        line_time = datetime.strptime(t[1], "%d-%m-%Y %H:%M:%S")
        if line_time >= st.session_state.session_start:
            result.append(t)
    return result

def get_monthly_data(username):
    months = defaultdict(lambda: {"income": 0, "expense": 0})
    for t in get_all_transactions(username):
        date, t_type, amount = t[1], t[2], float(t[3])
        month_key = date.split(" ")[0][3:]  # MM-YYYY
        if t_type.startswith("Income"):
            months[month_key]["income"] += amount
        else:
            months[month_key]["expense"] += amount
    return months

def get_category_spend_this_month(username):
    current_month = datetime.now().strftime("%m-%Y")
    spend = defaultdict(float)
    for t in get_all_transactions(username):
        date, t_type, amount = t[1], t[2], float(t[3])
        month_key = date.split(" ")[0][3:]
        if month_key == current_month and t_type.startswith("Expense - "):
            category = t_type.replace("Expense - ", "")
            spend[category] += amount
    return spend

def reset_all_data(username):
    fname = user_file(username)
    if os.path.exists(fname):
        os.remove(fname)


# ---------- Budget Logic ----------

def load_budgets(username):
    fname = budget_file(username)
    budgets = {}
    if os.path.exists(fname):
        with open(fname, "r") as file:
            for line in file:
                parts = line.strip().split(",")
                if len(parts) == 2:
                    budgets[parts[0]] = float(parts[1])
    return budgets

def save_budgets(username, budgets):
    with open(budget_file(username), "w") as file:
        for cat, limit in budgets.items():
            file.write(f"{cat},{limit}\n")


# ---------- Recurring Transactions ----------

def load_recurring(username):
    fname = recurring_file(username)
    items = []
    if os.path.exists(fname):
        with open(fname, "r") as file:
            for line in file:
                parts = line.strip().split(",")
                if len(parts) == 5:
                    items.append({
                        "id": parts[0], "t_type": parts[1], "label": parts[2],
                        "amount": float(parts[3]), "last_added": parts[4]
                    })
    return items

def save_recurring(username, items):
    with open(recurring_file(username), "w") as file:
        for it in items:
            file.write(f"{it['id']},{it['t_type']},{it['label']},{it['amount']},{it['last_added']}\n")

def add_recurring(username, t_type, label, amount):
    items = load_recurring(username)
    items.append({"id": uuid.uuid4().hex[:8], "t_type": t_type, "label": label, "amount": amount, "last_added": ""})
    save_recurring(username, items)

def delete_recurring(username, rid):
    items = load_recurring(username)
    items = [it for it in items if it["id"] != rid]
    save_recurring(username, items)

def process_recurring(username):
    """Auto-add recurring transactions once per month."""
    current_month = datetime.now().strftime("%m-%Y")
    items = load_recurring(username)
    changed = False
    for it in items:
        if it["last_added"] != current_month:
            if it["t_type"] == "Income":
                add_transaction(username, "Income", it["amount"])
            else:
                add_transaction(username, "Expense - " + it["label"], it["amount"])
            it["last_added"] = current_month
            changed = True
    if changed:
        save_recurring(username, items)


# ---------- Session State ----------

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = None
if "session_start" not in st.session_state:
    st.session_state.session_start = datetime.now()
if "last_activity" not in st.session_state:
    st.session_state.last_activity = time.time()
if "signup_count" not in st.session_state:
    st.session_state.signup_count = 0

# Auto-logout after inactivity
if st.session_state.logged_in:
    if time.time() - st.session_state.last_activity > SESSION_TIMEOUT_SECONDS:
        st.session_state.logged_in = False
        st.session_state.username = None
        st.warning("Session timed out due to inactivity. Please log in again.")
    else:
        st.session_state.last_activity = time.time()


# ---------- Login / Signup / Forgot Password ----------

def login_screen():
    st.title("💰 Expense Tracker")
    st.subheader("Login / Sign Up")

    tab1, tab2, tab3 = st.tabs(["Login", "Sign Up", "Forgot Password"])
    users = load_users()

    with tab1:
        username = st.text_input("Username", key="login_user", max_chars=MAX_USERNAME_LEN)
        password = st.text_input("Password", type="password", key="login_pass", max_chars=MAX_PASSWORD_LEN)
        if st.button("Login"):
            locked, remaining = is_locked_out(username)
            if locked:
                st.error(f"Too many failed attempts. Try again in {remaining} seconds.")
            elif username in users and verify_password(username, password, users):
                clear_attempts(username)
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.session_start = datetime.now()
                st.session_state.last_activity = time.time()
                st.rerun()
            else:
                if username in users:
                    record_failed_attempt(username)
                st.error("Invalid username or password.")

    with tab2:
        new_username = st.text_input("Choose Username", key="signup_user", max_chars=MAX_USERNAME_LEN)
        new_password = st.text_input("Choose Password", type="password", key="signup_pass", max_chars=MAX_PASSWORD_LEN)
        security_question = st.text_input("Set a Security Question (e.g. Your pet's name?)", key="signup_question", max_chars=MAX_TEXT_LEN)
        security_answer = st.text_input("Answer to your Security Question", key="signup_security", max_chars=MAX_TEXT_LEN)
        if st.button("Sign Up"):
            if st.session_state.signup_count >= MAX_SIGNUPS_PER_SESSION:
                st.error("Too many sign-up attempts. Please refresh and try again later.")
            elif not new_username or not new_password or not security_question or not security_answer:
                st.warning("Please fill all fields.")
            elif len(new_password) < 6:
                st.warning("Password should be at least 6 characters.")
            elif new_username in users:
                st.error("Username already exists.")
            else:
                save_user(new_username, new_password, security_question.strip(), security_answer.strip().lower())
                st.session_state.signup_count += 1
                st.success("Account created! Please login now.")

    with tab3:
        fp_username = st.text_input("Username", key="fp_user", max_chars=MAX_USERNAME_LEN)
        user_exists = fp_username in users
        question_text = users[fp_username]["security_question"] if user_exists else "Security Question"
        if fp_username:
            st.caption(f"Security Question: {question_text}")
            fp_answer = st.text_input("Your Answer", key="fp_answer", max_chars=MAX_TEXT_LEN)
            fp_new_pass = st.text_input("New Password", type="password", key="fp_new_pass", max_chars=MAX_PASSWORD_LEN)
            if st.button("Reset Password"):
                if user_exists and verify_security_answer(fp_username, fp_answer, users):
                    if fp_new_pass and len(fp_new_pass) >= 6:
                        update_password(fp_username, fp_new_pass)
                        clear_attempts(fp_username)
                        st.success("Password reset! Please login with your new password.")
                    else:
                        st.warning("New password must be at least 6 characters.")
                else:
                    st.error("Invalid username or answer.")


# ---------- Main App ----------

def main_app():
    username = st.session_state.username
    process_recurring(username)

    st.title("💰 Expense Tracker")
    st.caption(f"Logged in as: **{username}**")
    if st.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.username = None
        st.rerun()

    tabs = st.tabs(["➕ Add", "⚖️ Balance", "📜 History", "📅 Monthly", "🎯 Budget", "🔁 Recurring", "🤖 AI Assistant", "⚙️ Settings"])
    tab_add, tab_balance, tab_history, tab_monthly, tab_budget, tab_recurring, tab_ai, tab_settings = tabs

    categories = ["Food", "Travel", "Shopping", "Recharge", "Medical", "Other"]

    # ---- Add ----
    with tab_add:
        st.subheader("Add Income")
        income_amount = st.number_input("Income Amount", min_value=0.0, step=100.0, key="income_amt")
        if st.button("Add Income"):
            if income_amount > 0:
                add_transaction(username, "Income", income_amount)
                st.success(f"Income of ₹{income_amount} added!")
            else:
                st.warning("Enter a valid amount.")

        st.divider()

        st.subheader("Add Expense")
        category = st.selectbox("Category", categories)
        if category == "Other":
            custom_category = st.text_input("Enter Category Name")
            final_category = custom_category.strip() if custom_category.strip() else "Other"
        else:
            final_category = category

        expense_amount = st.number_input("Expense Amount", min_value=0.0, step=50.0, key="expense_amt")
        if st.button("Add Expense"):
            if expense_amount > 0:
                add_transaction(username, "Expense - " + final_category, expense_amount)
                st.success(f"Expense of ₹{expense_amount} added under {final_category}!")

                budgets = load_budgets(username)
                if final_category in budgets:
                    spend = get_category_spend_this_month(username)
                    if spend[final_category] > budgets[final_category]:
                        st.warning(f"⚠️ Budget exceeded for {final_category}! Limit: ₹{budgets[final_category]:.0f}, Spent: ₹{spend[final_category]:.0f}")
            else:
                st.warning("Enter a valid amount.")

    # ---- Balance (Session) ----
    with tab_balance:
        st.subheader("Balance (This Session)")
        income = expense = 0
        for t in get_session_lines(username):
            amount = float(t[3])
            if t[2].startswith("Income"):
                income += amount
            else:
                expense += amount

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Income", f"₹{income:.0f}")
        col2.metric("Total Expense", f"₹{expense:.0f}")
        col3.metric("Balance", f"₹{income - expense:.0f}")

        st.divider()
        if st.button("🗑️ Reset My Data (Permanent)"):
            reset_all_data(username)
            st.session_state.session_start = datetime.now()
            st.success("All your data deleted!")
            st.rerun()

    # ---- History (All) with Edit/Delete/Export ----
    with tab_history:
        st.subheader("Transaction History (All)")
        transactions = get_all_transactions(username)

        if not transactions:
            st.info("No transactions found.")
        else:
            df = pd.DataFrame(transactions, columns=["id", "Date", "Type", "Amount"])
            df["Amount_num"] = df["Amount"].astype(float)
            df_display = df.iloc[::-1]  # newest first

            export_df = df_display[["Date", "Type", "Amount"]]
            csv = export_df.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Export as CSV", csv, "expense_history.csv", "text/csv")

            def highlight_row(row):
                is_income = row["Type"].startswith("Income")
                color = "background-color: #d4f7d4; color: #1a5c1a" if is_income else "background-color: #f9d6d6; color: #8b1a1a"
                return [color] * len(row)

            styled = df_display[["Date", "Type", "Amount"]].style.apply(highlight_row, axis=1)
            st.dataframe(styled, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("Edit / Delete a Transaction")
            options = {f"{t[1]} | {t[2]} | ₹{t[3]}": t[0] for t in transactions}
            selected_label = st.selectbox("Select transaction", list(options.keys()))
            selected_id = options[selected_label]
            selected_txn = next(t for t in transactions if t[0] == selected_id)

            new_amount = st.number_input("New Amount", min_value=0.0, value=float(selected_txn[3]), step=10.0, key="edit_amt")
            col_edit, col_delete = st.columns(2)
            with col_edit:
                if st.button("✏️ Update Amount"):
                    update_transaction(username, selected_id, selected_txn[2], new_amount)
                    st.success("Transaction updated!")
                    st.rerun()
            with col_delete:
                if st.button("🗑️ Delete Transaction"):
                    delete_transaction(username, selected_id)
                    st.success("Transaction deleted!")
                    st.rerun()

    # ---- Monthly Report ----
    with tab_monthly:
        st.subheader("Monthly Report (All Months)")
        months = get_monthly_data(username)
        if not months:
            st.info("No transactions found.")
        else:
            for month_key in sorted(months.keys(), key=lambda m: datetime.strptime(m, "%m-%Y")):
                income = months[month_key]["income"]
                expense = months[month_key]["expense"]
                with st.expander(f"📅 {month_key}", expanded=True):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Income", f"₹{income:.0f}")
                    c2.metric("Expense", f"₹{expense:.0f}")
                    c3.metric("Balance", f"₹{income - expense:.0f}")

    # ---- Budget ----
    with tab_budget:
        st.subheader("Monthly Budget Limits")
        budgets = load_budgets(username)
        spend = get_category_spend_this_month(username)

        budget_categories = ["Food", "Travel", "Shopping", "Recharge", "Medical", "Other"]
        for cat in budget_categories:
            current_limit = budgets.get(cat, 0.0)
            new_limit = st.number_input(f"{cat} limit (₹)", min_value=0.0, value=current_limit, step=100.0, key=f"budget_{cat}")
            if new_limit != current_limit:
                budgets[cat] = new_limit
                save_budgets(username, budgets)

            spent = spend.get(cat, 0.0)
            if new_limit > 0:
                pct = min(spent / new_limit, 1.0)
                st.progress(pct, text=f"₹{spent:.0f} / ₹{new_limit:.0f} spent this month")
                if spent > new_limit:
                    st.error(f"⚠️ Over budget in {cat}!")

    # ---- Recurring ----
    with tab_recurring:
        st.subheader("Recurring Transactions (Auto-added Monthly)")
        st.caption("These will be automatically added once every month (e.g. rent, salary).")

        r_type = st.radio("Type", ["Income", "Expense"], horizontal=True)
        r_label = st.text_input("Label (e.g. Salary, Rent)")
        r_amount = st.number_input("Amount", min_value=0.0, step=100.0, key="recurring_amt")
        if st.button("Add Recurring"):
            if r_label.strip() and r_amount > 0:
                add_recurring(username, r_type, r_label.strip(), r_amount)
                st.success("Recurring transaction added! It will auto-add every month.")
                st.rerun()
            else:
                st.warning("Enter a label and valid amount.")

        st.divider()
        items = load_recurring(username)
        if not items:
            st.info("No recurring transactions set up.")
        else:
            for it in items:
                col1, col2 = st.columns([4, 1])
                col1.write(f"**{it['t_type']}** - {it['label']} - ₹{it['amount']:.0f} (last added: {it['last_added'] or 'never'})")
                if col2.button("🗑️", key=f"del_rec_{it['id']}"):
                    delete_recurring(username, it["id"])
                    st.rerun()

    # ---- AI Assistant ----
    with tab_ai:
        st.subheader("🤖 Ask AI about your expenses")

        if "gemini_api_key" not in st.session_state:
            st.session_state.gemini_api_key = ""
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        with st.expander("🔑 Gemini API Key", expanded=not st.session_state.gemini_api_key):
            st.caption("Get a free key from [Google AI Studio](https://aistudio.google.com/app/apikey). It's only kept for this session, never saved to a file.")
            key_input = st.text_input("API Key", type="password", value=st.session_state.gemini_api_key)
            if key_input != st.session_state.gemini_api_key:
                st.session_state.gemini_api_key = key_input

        # Render chat history as styled bubbles
        for msg in st.session_state.chat_history:
            bubble_class = "chat-bubble-user" if msg["role"] == "user" else "chat-bubble-ai"
            label = "🧑 You" if msg["role"] == "user" else "🤖 AI"
            st.markdown(f'<div class="{bubble_class}"><b>{label}</b><br>{msg["content"]}</div>', unsafe_allow_html=True)

        st.write("")

        col_text, col_mic = st.columns([3, 1])
        with col_text:
            typed_question = st.chat_input("Apna sawaal type karein...")
        with col_mic:
            voice_clip = st.audio_input("🎤 Ya bolke poochein", label_visibility="collapsed")

        def ask_ai(user_text=None, audio_bytes=None, audio_mime=None, display_text=None):
            if not st.session_state.gemini_api_key:
                st.error("Pehle apni Gemini API key upar daalein.")
                return
            st.session_state.chat_history.append({"role": "user", "content": display_text or user_text or "🎤 Voice question"})
            with st.spinner("Soch raha hoon..."):
                try:
                    context = build_data_context(username)
                    answer = call_gemini(
                        st.session_state.gemini_api_key,
                        user_text=user_text,
                        audio_bytes=audio_bytes,
                        audio_mime=audio_mime,
                        data_context=context
                    )
                except Exception as e:
                    answer = f"Error: {e}"
            st.session_state.chat_history.append({"role": "assistant", "content": answer})
            st.rerun()

        if typed_question:
            ask_ai(user_text=typed_question, display_text=typed_question)

        if voice_clip is not None:
            audio_bytes = voice_clip.read()
            ask_ai(audio_bytes=audio_bytes, audio_mime="audio/wav", display_text="🎤 Voice question")

        if st.session_state.chat_history and st.button("🗑️ Clear Chat"):
            st.session_state.chat_history = []
            st.rerun()

    # ---- Settings (Password Change) ----
    with tab_settings:
        st.subheader("Change Password")
        current_pass = st.text_input("Current Password", type="password", key="cp_current")
        new_pass1 = st.text_input("New Password", type="password", key="cp_new1")
        new_pass2 = st.text_input("Confirm New Password", type="password", key="cp_new2")
        if st.button("Update Password"):
            users = load_users()
            if not verify_password(username, current_pass, users):
                st.error("Current password is incorrect.")
            elif not new_pass1:
                st.warning("Enter a new password.")
            elif new_pass1 != new_pass2:
                st.error("New passwords do not match.")
            else:
                update_password(username, new_pass1)
                st.success("Password updated successfully!")


# ---------- App Entry Point ----------

if st.session_state.logged_in:
    main_app()
else:
    login_screen()
