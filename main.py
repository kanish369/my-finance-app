import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# ---------------------------------------------------------
# DATABASE INITIALIZATION & CORE HELPERS
# ---------------------------------------------------------
DB_NAME = "finance.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Profiles table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS profiles (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            default_theme TEXT DEFAULT 'Coral Peach 🍑'
        )
    ''')
    
    # Expenses table linked to profile
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            title TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Categories table linked to profile
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            name TEXT NOT NULL,
            UNIQUE(username, name)
        )
    ''')
    
    # Budget table linked to profile
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS budget (
            username TEXT PRIMARY KEY,
            amount REAL NOT NULL
        )
    ''')
    
    # Monthly archives linked to profile
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS monthly_archives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            month_year TEXT NOT NULL,
            budget REAL NOT NULL,
            total_spent REAL NOT NULL,
            savings REAL NOT NULL,
            date_closed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_profile_data(username):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, default_theme FROM profiles WHERE username = ?", (username,))
    res = cursor.fetchone()
    conn.close()
    return res

def create_profile(username, password, default_theme):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO profiles (username, password_hash, default_theme) VALUES (?, ?, ?)",
                       (username, hash_password(password), default_theme))
        cursor.execute("INSERT INTO budget (username, amount) VALUES (?, ?)", (username, 20000.0))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def update_default_theme(username, theme):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE profiles SET default_theme = ? WHERE username = ?", (theme, username))
    conn.commit()
    conn.close()

def get_budget(username):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT amount FROM budget WHERE username = ?", (username,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else 20000.0

def update_budget(username, new_amount):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO budget (username, amount) VALUES (?, ?)", (username, new_amount))
    conn.commit()
    conn.close()

def add_expense(username, title, amount, category):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO expenses (username, title, amount, category) VALUES (?, ?, ?, ?)", (username, title, amount, category))
    conn.commit()
    conn.close()

def update_expense(expense_id, title, amount, category):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE expenses SET title = ?, amount = ?, category = ? WHERE id = ?", (title, amount, category, expense_id))
    conn.commit()
    conn.close()

def delete_expense(expense_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()

def get_expenses(username):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, amount, category, date FROM expenses WHERE username = ? ORDER BY id DESC", (username,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_categories(username):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM categories WHERE username = ?", (username,))
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

def add_category(username, category_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO categories (username, name) VALUES (?, ?)", (username, category_name))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

def delete_category(username, category_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM categories WHERE username = ? AND name = ?", (username, category_name))
    conn.commit()
    conn.close()

def archive_current_month(username, month_year, budget, total_spent, savings):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO monthly_archives (username, month_year, budget, total_spent, savings) VALUES (?, ?, ?, ?, ?)",
                   (username, month_year, budget, total_spent, savings))
    cursor.execute("DELETE FROM expenses WHERE username = ?", (username,))
    conn.commit()
    conn.close()

def get_monthly_archives(username):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, month_year, budget, total_spent, savings, date_closed FROM monthly_archives WHERE username = ? ORDER BY id DESC", (username,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_total_accumulated_savings(username):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(savings) FROM monthly_archives WHERE username = ?", (username,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res[0] is not None else 0.0

# ---------------------------------------------------------
# PDF GENERATOR FUNCTION
# ---------------------------------------------------------
def generate_pdf_report(title_text, df_expenses, budget_val, spent_val, savings_val):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#334155'), spaceAfter=12)
    meta_style = ParagraphStyle('MetaStyle', parent=styles['Normal'], fontSize=11, leading=14, textColor=colors.HexColor('#0F172A'))
    
    story.append(Paragraph(f"<b>Budget Tracker Report - {title_text}</b>", title_style))
    story.append(Spacer(1, 10))
    
    summary_text = f"<b>Allocated Budget:</b> ₹{budget_val:,.2f} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Total Spent:</b> ₹{spent_val:,.2f} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Month Savings:</b> ₹{savings_val:,.2f}"
    story.append(Paragraph(summary_text, meta_style))
    story.append(Spacer(1, 15))
    
    if not df_expenses.empty:
        table_data = [["Item / Title", "Category", "Amount (₹)", "Date"]]
        for _, row in df_expenses.iterrows():
            table_data.append([str(row["title"]), str(row["category"]), f"₹{row['amount']:,.2f}", str(row["date"])])
            
        t = Table(table_data, colWidths=[180, 120, 100, 140])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8FAFC')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("<i>No specific expense itemization logged for this period.</i>", meta_style))
        
    doc.build(story)
    buffer.seek(0)
    return buffer

# ---------------------------------------------------------
# PAGE CONFIG & INIT
# ---------------------------------------------------------
st.set_page_config(page_title="Secure Budget Tracker 📊", page_icon="🧸", layout="wide")
init_db()

# Session state initialization for login
if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = None

# ---------------------------------------------------------
# AUTHENTICATION / PROFILE LOGIN SCREEN
# ---------------------------------------------------------
if not st.session_state.logged_in_user:
    st.title("🔒 Private & Secure Budget Tracker")
    st.markdown("##### *Log in to your private profile or create a new account to keep your finances secure.*")
    st.write("")

    auth_tab1, auth_tab2 = st.tabs(["🔑 Log In", "✨ Create Profile"])

    with auth_tab1:
        st.subheader("Profile Login")
        with st.form("login_form"):
            login_user = st.text_input("Username").strip()
            login_pass = st.text_input("Password", type="password")
            login_submit = st.form_submit_button("🔓 Unlock Profile")

            if login_submit:
                if not login_user or not login_pass:
                    st.warning("Please fill in both username and password.")
                else:
                    profile_record = get_profile_data(login_user)
                    if profile_record and profile_record[0] == hash_password(login_pass):
                        st.session_state.logged_in_user = login_user
                        st.session_state.current_theme = profile_record[1]
                        st.success(f"Welcome back, **{login_user}**! 🌸")
                        st.rerun()
                    else:
                        st.error("Invalid username or password. Please try again.")

    with auth_tab2:
        st.subheader("Create New Private Profile")
        with st.form("signup_form"):
            new_user = st.text_input("Choose Username").strip()
            new_pass = st.text_input("Choose Secure Password", type="password")
            chosen_theme = st.selectbox(
                "Preferred Default Theme",
                ["Coral Peach 🍑", "Night Theme 🌙", "Light Slate 🌫️"]
            )
            signup_submit = st.form_submit_button("✨ Register Profile")

            if signup_submit:
                if not new_user or not new_pass:
                    st.warning("Please provide both username and password.")
                else:
                    success = create_profile(new_user, new_pass, chosen_theme)
                    if success:
                        st.success(f"Profile **{new_user}** created successfully! You can now log in.")
                    else:
                        st.error("Username already exists. Please choose a different name.")

    st.stop()  # Halt execution until authenticated

# ---------------------------------------------------------
# LOAD USER CONFIG & THEME STYLING
# ---------------------------------------------------------
current_user = st.session_state.logged_in_user
profile_info = get_profile_data(current_user)
default_saved_theme = profile_info[1] if profile_info else "Coral Peach 🍑"

if "current_theme" not in st.session_state:
    st.session_state.current_theme = default_saved_theme

# ---------------------------------------------------------
# SIDEBAR NAVIGATION & THEME SELECTION
# ---------------------------------------------------------
st.sidebar.markdown(f"### 🪞 *Profile: {current_user}*")
if st.sidebar.button("🔒 Lock & Switch Profile", use_container_width=True):
    st.session_state.logged_in_user = None
    st.rerun()

st.sidebar.markdown("---")

theme_choice = st.sidebar.selectbox(
    "🎨 Workspace Theme",
    ["Coral Peach 🍑", "Night Theme 🌙", "Light Slate 🌫️"],
    index=["Coral Peach 🍑", "Night Theme 🌙", "Light Slate 🌫️"].index(st.session_state.current_theme)
)

if theme_choice != st.session_state.current_theme:
    st.session_state.current_theme = theme_choice

if st.sidebar.button("⭐ Save as Default Theme", use_container_width=True):
    update_default_theme(current_user, theme_choice)
    st.sidebar.success("Default theme saved!")

st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "Select View 🩰", 
    ["Overview 🌿", "Add Expense 🪻", "Manage & Edit Expenses ✏️", "Monthly Archives & PDF 📑", "Budget & Categories 🕯️"]
)

st.sidebar.markdown("---")
st.sidebar.caption("✨ *Private, Secure & Intentional Spending*")

# ---------------------------------------------------------
# THEME DYNAMIC STYLING & WHITE TITLE COLORS
# ---------------------------------------------------------
if "Coral Peach" in theme_choice:
    bg_color = "#FDE2D4"
    text_color = "#3D2314"
    sidebar_bg = "#FAD0C0"
    box_bg_1 = "#EBC4A7"
    box_bg_2 = "#DFA888"
    card_border = "#D89A7A"
    form_bg = "#FFF0E8"
    btn_bg = "#B86246"
    btn_hover = "#964B33"
    btn_text = "#FFFFFF"
    input_bg = "#FFFFFF"
    input_text = "#3D2314"
    banner_bg = "#E87A5D"
    banner_title_color = "#FFFFFF"  # White title text as requested

elif "Night Theme" in theme_choice:
    bg_color = "#18181B"
    text_color = "#F4F4F5"
    sidebar_bg = "#27272A"
    box_bg_1 = "#3F3F46"
    box_bg_2 = "#52525B"
    card_border = "#3F3F46"
    form_bg = "#27272A"
    btn_bg = "#52525B"
    btn_hover = "#71717A"
    btn_text = "#FFFFFF"
    input_bg = "#27272A"
    input_text = "#FFFFFF"
    banner_bg = "#3F3F46"
    banner_title_color = "#FFFFFF"

else:  # Light Slate (Slate Blue look)
    bg_color = "#E2E8F0"
    text_color = "#0F172A"
    sidebar_bg = "#CBD5E1"
    box_bg_1 = "#94A3B8"
    box_bg_2 = "#64748B"
    card_border = "#94A3B8"
    form_bg = "#F1F5F9"
    btn_bg = "#334155"
    btn_hover = "#1E293B"
    btn_text = "#FFFFFF"
    input_bg = "#FFFFFF"
    input_text = "#0F172A"
    banner_bg = "#1E3A8A"       # Deep Slate Blue banner
    banner_title_color = "#FFFFFF"  # White title text as requested

st.markdown(f"""
    <style>
    .stApp {{
        background-color: {bg_color};
        color: {text_color};
        font-family: 'Avenir', 'Nunito', 'Segoe UI', sans-serif;
    }}
    h1, h2, h3 {{
        color: {text_color} !important;
        font-family: 'Georgia', serif;
    }}
    label, [data-testid="stWidgetLabel"] p {{
        color: {text_color} !important;
        font-weight: 700 !important;
        font-size: 1rem !important;
    }}
    .stTextInput input, .stNumberInput input, div[data-baseweb="select"] > div {{
        color: {input_text} !important;
        background-color: {input_bg} !important;
        border-radius: 12px !important;
        border: 2px solid {card_border} !important;
        font-weight: 600 !important;
    }}
    div[data-baseweb="select"] span {{
        color: {input_text} !important;
        font-weight: 700 !important;
    }}
    div[role="listbox"] li {{
        color: #0F172A !important;
        background-color: #FFFFFF !important;
        font-weight: 600 !important;
    }}
    [data-testid="stSidebar"] {{
        background-color: {sidebar_bg} !important;
        border-right: 1px solid {card_border};
    }}
    [data-testid="stSidebar"] * {{
        color: {text_color} !important;
        font-weight: 600 !important;
    }}
    .theme-box-1 {{
        background-color: {box_bg_1};
        color: {text_color};
        padding: 22px;
        border-radius: 18px;
        box-shadow: 0px 4px 12px rgba(0,0,0,0.05);
        border: 1px solid {card_border};
        text-align: center;
        margin-bottom: 15px;
    }}
    .theme-box-1 h4 {{
        color: {text_color} !important;
        margin-bottom: 6px;
        font-size: 0.95rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}
    .theme-box-1 p {{
        color: {text_color} !important;
        font-size: 2.1rem;
        font-weight: 800;
        margin: 0;
    }}
    .theme-box-2 {{
        background-color: {box_bg_2};
        color: {text_color};
        padding: 22px;
        border-radius: 18px;
        box-shadow: 0px 4px 12px rgba(0,0,0,0.05);
        border: 1px solid {card_border};
        text-align: center;
        margin-bottom: 15px;
    }}
    .theme-box-2 h4 {{
        color: {text_color} !important;
        margin-bottom: 6px;
        font-size: 0.95rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}
    .theme-box-2 p {{
        color: {text_color} !important;
        font-size: 2.1rem;
        font-weight: 800;
        margin: 0;
    }}
    [data-testid="stForm"] {{
        background-color: {form_bg};
        border: 2px dashed {card_border};
        border-radius: 20px;
        padding: 25px;
    }}
    .stButton > button, div[data-testid="stFormSubmitButton"] > button {{
        background-color: {btn_bg} !important;
        color: {btn_text} !important;
        border-radius: 25px !important;
        border: none !important;
        padding: 10px 24px !important;
        font-weight: 700 !important;
        box-shadow: 0 4px 10px rgba(0,0,0,0.15) !important;
    }}
    .stButton > button *, div[data-testid="stFormSubmitButton"] > button * {{
        color: {btn_text} !important;
        font-weight: 700 !important;
    }}
    .stButton > button:hover, div[data-testid="stFormSubmitButton"] > button:hover {{
        background-color: {btn_hover} !important;
        color: {btn_text} !important;
    }}
    .warning-banner {{
        background-color: {banner_bg};
        color: {text_color};
        padding: 18px 22px;
        border-radius: 16px;
        border: 2px solid #FFFFFF;
        margin-bottom: 25px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.15);
    }}
    .warning-banner h3 {{
        color: {banner_title_color} !important;
        margin-top: 0;
        margin-bottom: 6px;
        font-size: 1.25rem;
    }}
    .warning-banner p {{
        color: {banner_title_color} !important;
        margin: 0;
        font-size: 1rem;
        font-weight: 600;
    }}
    .stDataFrame {{
        border-radius: 14px;
        overflow: hidden;
        border: 1px solid {card_border};
    }}
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# VIEW 1: OVERVIEW / DASHBOARD
# ---------------------------------------------------------
if menu == "Overview 🌿":
    st.title(f"📊 Budget Tracker ({current_user})")
    st.caption("🍵 *Keep track of your peaceful flow of income, savings & expenses*")
    st.write("")

    current_budget = get_budget(current_user)
    expenses = get_expenses(current_user)
    
    total_spent = sum(e[2] for e in expenses)
    remaining_balance = current_budget - total_spent
    total_accumulated_savings = get_total_accumulated_savings(current_user)

    # Persistent Low Savings Banner on the page (Automatic trigger when < 5000)
    if remaining_balance < 5000.0:
        st.markdown(f"""
            <div class="warning-banner">
                <h3>⚠️ Low Savings Alert</h3>
                <p>
                    Your current month savings have dropped to <b>₹{remaining_balance:,.2f}</b>, which is below your target threshold of <b>₹5,000</b>. Consider reviewing your recent expenses to maintain your financial goals! 🌸
                </p>
            </div>
        """, unsafe_allow_html=True)

    # Metric Dashboard Layout
    c1, c2, c3, c4 = st.columns(4)
    
    with c1:
        st.markdown(f"""
            <div class="theme-box-1">
                <h4>☁️ Current Budget</h4>
                <p>₹{current_budget:,.2f}</p>
            </div>
        """, unsafe_allow_html=True)
        
    with c2:
        st.markdown(f"""
            <div class="theme-box-2">
                <h4>🕯️ Total Spent</h4>
                <p>₹{total_spent:,.2f}</p>
            </div>
        """, unsafe_allow_html=True)
        
    with c3:
        st.markdown(f"""
            <div class="theme-box-1">
                <h4>🌱 Current Month Savings</h4>
                <p>₹{remaining_balance:,.2f}</p>
            </div>
        """, unsafe_allow_html=True)

    with c4:
        st.markdown(f"""
            <div class="theme-box-2">
                <h4>🏦 Total Savings (All Months)</h4>
                <p>₹{total_accumulated_savings + max(0, remaining_balance):,.2f}</p>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # SECTION TO CLOSE CURRENT MONTH AND ARCHIVE SAVINGS
    st.subheader("🗓️ Close Month & Save Remaining Balance")
    st.caption("Save your month's unspent savings to your accumulated total and reset for next month.")

    with st.expander("✨ End Current Month Tracker"):
        with st.form("archive_month_form"):
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                month_name = st.selectbox("Select Month", ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"])
            with col_m2:
                year_val = st.number_input("Year", min_value=2024, max_value=2035, value=2026, step=1)
                
            archive_btn = st.form_submit_button("🔒 Lock & Save Month")
            
            if archive_btn:
                period_str = f"{month_name} {year_val}"
                archive_current_month(current_user, period_str, current_budget, total_spent, remaining_balance)
                st.success(f"🎉 **{period_str}** archived successfully! Savings of **₹{remaining_balance:,.2f}** added to total savings.")
                st.rerun()

    st.markdown("---")

    col_left, col_right = st.columns([1.2, 1])

    with col_left:
        st.subheader("🧺 Active Month Transactions")
        if expenses:
            df = pd.DataFrame(expenses, columns=["ID", "Item / Note", "Amount (₹)", "Category", "Date"])
            st.dataframe(
                df[["Item / Note", "Category", "Amount (₹)", "Date"]], 
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("🌸 *No active transactions recorded for this month.*")

    with col_right:
        st.subheader("🎨 Spending Breakdown")
        if expenses:
            df = pd.DataFrame(expenses, columns=["ID", "Item / Note", "Amount (₹)", "Category", "Date"])
            cat_summary = df.groupby("Category")["Amount (₹)"].sum().reset_index()
            st.bar_chart(cat_summary, x="Category", y="Amount (₹)", color=btn_bg)
        else:
            st.write("🍵 *No data to plot yet.*")

# ---------------------------------------------------------
# VIEW 2: ADD EXPENSE
# ---------------------------------------------------------
elif menu == "Add Expense 🪻":
    st.title("🪻 Log an Expense")
    st.caption("🕯️ *Record your purchases for the current active month*")
    st.write("")

    categories = get_categories(current_user)
    
    with st.form("expense_form", clear_on_submit=True):
        title = st.text_input("🏷️ Expense Details (e.g., Grocery, Stationery, Transport)")
        amount = st.number_input("💵 Amount (₹)", min_value=0.01, step=10.0)
        
        category_options = categories if categories else ["General 🩰"]
        category = st.selectbox("📌 Category", category_options)
        
        submitted = st.form_submit_button("✨ Save Purchase")
        
        if submitted:
            if not title.strip():
                st.warning("Please add a name for this purchase! 🌸")
            else:
                add_expense(current_user, title, amount, category)
                st.success(f"🌷 Saved **{title}** (₹{amount:.2f}) under **{category}**!")

# ---------------------------------------------------------
# VIEW 3: MANAGE & EDIT EXPENSES
# ---------------------------------------------------------
elif menu == "Manage & Edit Expenses ✏️":
    st.title("✏️ Edit or Delete Transactions")
    st.caption("🌾 *Modify or clean up recorded transactions*")
    st.write("")

    expenses = get_expenses(current_user)
    categories = get_categories(current_user)
    category_options = categories if categories else ["General 🩰"]

    if expenses:
        expense_dict = {f"#{e[0]} - {e[1]} (₹{e[2]:,.2f})": e for e in expenses}
        selected_key = st.selectbox("📌 Select Transaction to Modify", list(expense_dict.keys()))
        
        selected_expense = expense_dict[selected_key]
        exp_id, exp_title, exp_amount, exp_cat, exp_date = selected_expense

        col_edit, col_del = st.columns([1.5, 1])

        with col_edit:
            st.markdown("### ✏️ Edit Transaction Details")
            with st.form("edit_expense_form"):
                new_title = st.text_input("Expense Details", value=exp_title)
                new_amount = st.number_input("Amount (₹)", value=float(exp_amount), min_value=0.01, step=10.0)
                
                default_idx = category_options.index(exp_cat) if exp_cat in category_options else 0
                new_cat = st.selectbox("Category", category_options, index=default_idx)

                save_changes = st.form_submit_button("💾 Update Transaction")

                if save_changes:
                    if not new_title.strip():
                        st.warning("Please enter a valid detail name.")
                    else:
                        update_expense(exp_id, new_title, new_amount, new_cat)
                        st.success(f"🌷 Updated transaction **#{exp_id}** successfully!")
                        st.rerun()

        with col_del:
            st.markdown("### 🗑️ Delete Transaction")
            st.write(f"Are you sure you want to permanently delete **{exp_title}** (₹{exp_amount:,.2f})?")
            st.write("")
            if st.button("🗑️ Permanent Delete Transaction", use_container_width=True):
                delete_expense(exp_id)
                st.success(f"🍃 Deleted transaction **{exp_title}**!")
                st.rerun()

    else:
        st.info("🌸 *No active transactions available to edit or delete.*")

# ---------------------------------------------------------
# VIEW 4: MONTHLY ARCHIVES & PDF EXPORT
# ---------------------------------------------------------
elif menu == "Monthly Archives & PDF 📑":
    st.title("📑 Monthly History & PDF Reports")
    st.caption("🏦 *Review previous months, total savings, and download PDF summaries*")
    st.write("")

    archives = get_monthly_archives(current_user)
    total_savings = get_total_accumulated_savings(current_user)

    st.markdown(f"""
        <div class="theme-box-1" style="max-width: 400px; margin: 0 auto 25px auto;">
            <h4>💰 Total Savings Across All Months</h4>
            <p>₹{total_savings:,.2f}</p>
        </div>
    """, unsafe_allow_html=True)

    col_p1, col_p2 = st.columns(2)

    with col_p1:
        st.subheader("📄 Export Active Month PDF")
        expenses = get_expenses(current_user)
        curr_budget = get_budget(current_user)
        curr_spent = sum(e[2] for e in expenses)
        curr_savings = curr_budget - curr_spent
        
        df_curr = pd.DataFrame(expenses, columns=["id", "title", "amount", "category", "date"]) if expenses else pd.DataFrame()
        
        pdf_curr_data = generate_pdf_report("Active Month", df_curr, curr_budget, curr_spent, curr_savings)
        
        st.download_button(
            label="📥 Download Current Month PDF Report",
            data=pdf_curr_data,
            file_name="Active_Month_Budget_Report.pdf",
            mime="application/pdf",
            use_container_width=True
        )

    with col_p2:
        st.subheader("📂 Archived Monthly Records")
        if archives:
            df_arch = pd.DataFrame(archives, columns=["ID", "Month & Year", "Budget (₹)", "Spent (₹)", "Saved Amount (₹)", "Closed Date"])
            st.dataframe(df_arch[["Month & Year", "Budget (₹)", "Spent (₹)", "Saved Amount (₹)"]], use_container_width=True, hide_index=True)
        else:
            st.info("No closed months in the archives yet.")

# ---------------------------------------------------------
# VIEW 5: BUDGET & CATEGORIES
# ---------------------------------------------------------
elif menu == "Budget & Categories 🕯️":
    st.title("🕯️ Workspace Settings")
    st.caption("🌿 *Adjust your budget target and expense categories*")
    st.write("")

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("☁️ Monthly Target Allocation")
        current_budget = get_budget(current_user)
        
        new_budget = st.number_input(
            "Monthly Target (₹)", 
            value=float(current_budget), 
            min_value=0.0, 
            step=500.0
        )
        if st.button("💾 Update Monthly Target"):
            update_budget(current_user, new_budget)
            st.success("🌷 Budget target updated!")

    with col_b:
        st.subheader("🪴 Manage Categories")
        
        st.markdown("##### ➕ Add New Category")
        new_cat = st.text_input("New Category Name (e.g., 🥐 Food, 📚 Books)")
        
        if st.button("➕ Add Category"):
            if new_cat.strip():
                add_category(current_user, new_cat.strip())
                st.success(f"🌸 Created new category **{new_cat}**!")
                st.rerun()
            else:
                st.warning("Please type a category name first.")

        st.markdown("---")

        st.markdown("##### 🗑️ Delete Existing Category")
        existing_cats = get_categories(current_user)
        
        if existing_cats:
            cat_to_delete = st.selectbox("Select Category to Remove", existing_cats)
            if st.button("🗑️ Remove Category"):
                delete_category(current_user, cat_to_delete)
                st.success(f"🍃 Deleted category **{cat_to_delete}**!")
                st.rerun()
        else:
            st.info("No custom categories available to delete.")