import streamlit as st
import os
from datetime import datetime
from collections import defaultdict

file_name = "expenses.txt"

st.set_page_config(page_title="Expense Tracker", page_icon="💰", layout="centered")

# ---------- Core Logic (same as your original script) ----------

def add_transaction(t_type, amount):
    now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    with open(file_name, "a") as file:
        file.write(f"{now},{t_type},{amount}\n")

def get_session_lines():
    """Only transactions added during this browser session."""
    if not os.path.exists(file_name):
        return []

    with open(file_name, "r") as file:
        lines = file.readlines()

    session_lines = []
    for line in lines:
        parts = line.strip().split(",")
        line_time = datetime.strptime(parts[0], "%d-%m-%Y %H:%M:%S")
        if line_time >= st.session_state.session_start:
            session_lines.append(line)

    return session_lines

def get_monthly_data():
    if not os.path.exists(file_name):
        return {}

    months = defaultdict(lambda: {"income": 0, "expense": 0})

    with open(file_name, "r") as file:
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

def reset_all_data():
    if os.path.exists(file_name):
        os.remove(file_name)


# ---------- Session State ----------

if "session_start" not in st.session_state:
    st.session_state.session_start = datetime.now()


# ---------- UI ----------

st.title("💰 Expense Tracker")

tab1, tab2, tab3, tab4 = st.tabs(["➕ Add", "⚖️ Balance", "📜 History", "📅 Monthly Report"])

# ---- Add Income / Expense ----
with tab1:
    st.subheader("Add Income")
    income_amount = st.number_input("Income Amount", min_value=0.0, step=100.0, key="income_amt")
    if st.button("Add Income"):
        if income_amount > 0:
            add_transaction("Income", income_amount)
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
            add_transaction("Expense - " + final_category, expense_amount)
            st.success(f"Expense of ₹{expense_amount} added under {final_category}!")
        else:
            st.warning("Enter a valid amount.")

# ---- Balance (This Session) ----
with tab2:
    st.subheader("Balance (This Session)")
    income = expense = 0
    for line in get_session_lines():
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
    if st.button("🗑️ Reset All Data (Permanent)"):
        reset_all_data()
        st.session_state.session_start = datetime.now()
        st.success("All data deleted!")
        st.rerun()

# ---- History (This Session) ----
with tab3:
    st.subheader("Transaction History (This Session)")
    lines = get_session_lines()
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
    months = get_monthly_data()
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
