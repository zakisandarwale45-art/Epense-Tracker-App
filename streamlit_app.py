import streamlit as st
import os
from datetime import datetime
from collections import defaultdict

st.set_page_config(page_title="Expense Tracker", page_icon="💰", layout="centered")

users_file = "users.txt"


# ---------- Auth Helpers ----------

def load_users():
    users = {}
    if os.path.exists(users_file):
        with open(users_file, "r") as file:
            for line in file:
                parts = line.strip().split(",")
                if len(parts) == 2:
                    users[parts[0]] = parts[1]
    return users

def save_user(username, password):
    with open(users_file, "a") as file:
        file.write(f"{username},{password}\n")

def user_file(username):
    return f"expenses_{username}.txt"


# ---------- Core Logic ----------

def add_transaction(username, t_type, amount):
    now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    with open(user_file(username), "a") as file:
        file.write(f"{now},{t_type},{amount}\n")

def get_session_lines(username):
    fname = user_file(username)
    if not os.path.exists(fname):
        return []

    with open(fname, "r") as file:
        lines = file.readlines()

    session_lines = []
    for line in lines:
        parts = line.strip().split(",")
        line_time = datetime.strptime(parts[0], "%d-%m-%Y %H:%M:%S")
        if line_time >= st.session_state.session_start:
            session_lines.append(line)

    return session_lines

def get_monthly_data(username):
    fname = user_file(username)
    if not os.path.exists(fname):
        return {}

    months = defaultdict(lambda: {"income": 0, "expense": 0})

    with open(fname, "r") as file:
        for line in file:
            parts = line.strip().split(",")
            date, t_type = parts[0], parts[1]
            amount = float(parts[2])
            month_key = date.split(" ")[0][3:]  # "MM-YYYY"

            if t_type.startswith("Income"):
                months[month_key]["income"] += amount
            else:
                months[month_key]["expense"] += amount

    return months

def reset_all_data(username):
    fname = user_file(username)
    if os.path.exists(fname):
        os.remove(fname)


# ---------- Session State ----------

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = None


# ---------- Login / Signup Screen ----------

def login_screen():
    st.title("💰 Expense Tracker")
    st.subheader("Login / Sign Up")

    tab1, tab2 = st.tabs(["Login", "Sign Up"])
    users = load_users()

    with tab1:
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")
        if st.button("Login"):
            if username in users and users[username] == password:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.session_start = datetime.now()
                st.rerun()
            else:
                st.error("Invalid username or password.")

    with tab2:
        new_username = st.text_input("Choose Username", key="signup_user")
        new_password = st.text_input("Choose Password", type="password", key="signup_pass")
        if st.button("Sign Up"):
            if not new_username or not new_password:
                st.warning("Please fill both fields.")
            elif new_username in users:
                st.error("Username already exists.")
            else:
                save_user(new_username, new_password)
                st.success("Account created! Please login now.")


# ---------- Main App (after login) ----------

def main_app():
    username = st.session_state.username

    st.title("💰 Expense Tracker")
    st.caption(f"Logged in as: **{username}**")
    if st.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.username = None
        st.rerun()

    tab1, tab2, tab3, tab4 = st.tabs(["➕ Add", "⚖️ Balance", "📜 History", "📅 Monthly Report"])

    # ---- Add Income / Expense ----
    with tab1:
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
        categories = ["Food", "Travel", "Shopping", "Recharge", "Medical", "Other"]
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
            else:
                st.warning("Enter a valid amount.")

    # ---- Balance (This Session) ----
    with tab2:
        st.subheader("Balance (This Session)")
        income = expense = 0
        for line in get_session_lines(username):
            date, t_type, amount = line.strip().split(",")
            amount = float(amount)
            if t_type.startswith("Income"):
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

    # ---- History (This Session) ----
    with tab3:
        st.subheader("Transaction History (This Session)")
        lines = get_session_lines(username)
        if not lines:
            st.info("No transactions added yet in this session.")
        else:
            rows = []
            for line in lines:
                date, t_type, amount = line.strip().split(",")
                rows.append({"Date": date, "Type": t_type, "Amount": f"₹{float(amount):.0f}"})
            st.table(rows)

    # ---- Monthly Report (All Data) ----
    with tab4:
        st.subheader("Monthly Report (All Months)")
        months = get_monthly_data(username)
        if not months:
            st.info("No transactions found.")
        else:
            for month_key in sorted(months.keys(), key=lambda m: datetime.strptime(m, "%m-%Y")):
                income = months[month_key]["income"]
                expense = months[month_key]["expense"]
                with st.expander(f"📅 {month_key}", expanded=True):
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Income", f"₹{income:.0f}")
                    col2.metric("Expense", f"₹{expense:.0f}")
                    col3.metric("Balance", f"₹{income - expense:.0f}")


# ---------- App Entry Point ----------

if st.session_state.logged_in:
    main_app()
else:
    login_screen()
