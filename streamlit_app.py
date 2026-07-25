import streamlit as st
import os
import uuid
import pandas as pd
from datetime import datetime
from collections import defaultdict

st.set_page_config(page_title="Expense Tracker", page_icon="💰", layout="centered")

users_file = "users.txt"


# ---------- File helpers ----------

def user_file(username):
    return f"expenses_{username}.txt"

def budget_file(username):
    return f"budget_{username}.txt"

def recurring_file(username):
    return f"recurring_{username}.txt"


# ---------- Auth Helpers ----------
# users.txt format: username|password|security_question|security_answer

def load_users():
    users = {}
    if os.path.exists(users_file):
        with open(users_file, "r") as file:
            for line in file:
                parts = line.rstrip("\n").split("|")
                if len(parts) == 4:
                    users[parts[0]] = {
                        "password": parts[1],
                        "security_question": parts[2],
                        "security_answer": parts[3],
                    }
    return users

def save_user(username, password, security_question, security_answer):
    with open(users_file, "a") as file:
        file.write(f"{username}|{password}|{security_question}|{security_answer}\n")

def update_password(username, new_password):
    users = load_users()
    if username not in users:
        return
    with open(users_file, "w") as file:
        for uname, info in users.items():
            pwd = new_password if uname == username else info["password"]
            file.write(f"{uname}|{pwd}|{info['security_question']}|{info['security_answer']}\n")


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


# ---------- Login / Signup / Forgot Password ----------

def login_screen():
    st.title("💰 Expense Tracker")
    st.subheader("Login / Sign Up")

    tab1, tab2, tab3 = st.tabs(["Login", "Sign Up", "Forgot Password"])
    users = load_users()

    with tab1:
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")
        if st.button("Login"):
            if username in users and users[username]["password"] == password:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.session_start = datetime.now()
                st.rerun()
            else:
                st.error("Invalid username or password.")

    with tab2:
        new_username = st.text_input("Choose Username", key="signup_user")
        new_password = st.text_input("Choose Password", type="password", key="signup_pass")
        security_question = st.text_input("Set a Security Question (e.g. Your pet's name?)", key="signup_question")
        security_answer = st.text_input("Answer to your Security Question", key="signup_security")
        if st.button("Sign Up"):
            if not new_username or not new_password or not security_question or not security_answer:
                st.warning("Please fill all fields.")
            elif new_username in users:
                st.error("Username already exists.")
            else:
                save_user(new_username, new_password, security_question.strip(), security_answer.strip().lower())
                st.success("Account created! Please login now.")

    with tab3:
        fp_username = st.text_input("Username", key="fp_user")
        if fp_username and fp_username in users:
            st.caption(f"Security Question: {users[fp_username]['security_question']}")
            fp_answer = st.text_input("Your Answer", key="fp_answer")
            fp_new_pass = st.text_input("New Password", type="password", key="fp_new_pass")
            if st.button("Reset Password"):
                if users[fp_username]["security_answer"] == fp_answer.strip().lower():
                    if fp_new_pass:
                        update_password(fp_username, fp_new_pass)
                        st.success("Password reset! Please login with your new password.")
                    else:
                        st.warning("Enter a new password.")
                else:
                    st.error("Answer is incorrect.")
        elif fp_username:
            st.error("Username not found.")


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

    tabs = st.tabs(["➕ Add", "⚖️ Balance", "📜 History", "📅 Monthly", "🎯 Budget", "🔁 Recurring", "⚙️ Settings"])
    tab_add, tab_balance, tab_history, tab_monthly, tab_budget, tab_recurring, tab_settings = tabs

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

    # ---- Settings (Password Change) ----
    with tab_settings:
        st.subheader("Change Password")
        current_pass = st.text_input("Current Password", type="password", key="cp_current")
        new_pass1 = st.text_input("New Password", type="password", key="cp_new1")
        new_pass2 = st.text_input("Confirm New Password", type="password", key="cp_new2")
        if st.button("Update Password"):
            users = load_users()
            if users[username]["password"] != current_pass:
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
