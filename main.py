import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Personal Finance & Budget Tracker",
    page_icon="💰",
    layout="centered"
)

# --- DATABASE SETUP WITH AUTO-REPAIR ---
def init_db():
    conn = sqlite3.connect('finance.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Profiles table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Expenses table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER,
            date TEXT,
            category TEXT,
            amount REAL,
            note TEXT,
            FOREIGN KEY (profile_id) REFERENCES profiles (id)
        )
    ''')
    
    # Budgets & Settings table (stores custom savings warning limit per profile)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            profile_id INTEGER PRIMARY KEY,
            monthly_income REAL,
            savings_limit REAL,
            FOREIGN KEY (profile_id) REFERENCES profiles (id)
        )
    ''')
    conn.commit()
    return conn

conn = init_db()
cursor = conn.cursor()

# --- ENSURE DEFAULT PROFILE & SETTINGS EXIST ---
try:
    cursor.execute("SELECT COUNT(*) FROM profiles")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO profiles (name) VALUES (?)", ("Default Profile",))
        conn.commit()
        default_id = cursor.lastrowid
        cursor.execute("INSERT INTO settings (profile_id, monthly_income, savings_limit) VALUES (?, ?, ?)", (default_id, 0.0, 5000.0))
        conn.commit()
except sqlite3.OperationalError:
    cursor.execute("DROP TABLE IF EXISTS settings")
    cursor.execute("DROP TABLE IF EXISTS expenses")
    cursor.execute("DROP TABLE IF EXISTS profiles")
    conn.commit()
    conn = init_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO profiles (name) VALUES (?)", ("Default Profile",))
    conn.commit()
    default_id = cursor.lastrowid
    cursor.execute("INSERT INTO settings (profile_id, monthly_income, savings_limit) VALUES (?, ?, ?)", (default_id, 0.0, 5000.0))
    conn.commit()

# --- APP HEADER ---
st.title("💰 Smart Personal Finance & Budget Tracker")
st.markdown("Manage your multi-profile budgets, track expenses, generate reports, and build secure savings habits!")

# --- SIDEBAR: PROFILE MANAGEMENT & SWITCHER ---
st.sidebar.header("👤 Profile Switcher")
cursor.execute("SELECT name FROM profiles")
profiles = [row[0] for row in cursor.fetchall()]
selected_profile = st.sidebar.selectbox("Choose Profile", profiles)

# Get selected profile ID safely
cursor.execute("SELECT id FROM profiles WHERE name = ?", (selected_profile,))
profile_id_row = cursor.fetchone()
profile_id = profile_id_row[0] if profile_id_row else 1

# Sidebar expander for adding new profiles
with st.sidebar.expander("Manage Profiles"):
    add_name = st.text_input("New Profile Name")
    if st.button("Add Profile"):
        if add_name.strip():
            try:
                cursor.execute("INSERT INTO profiles (name) VALUES (?)", (add_name.strip(),))
                new_id = cursor.lastrowid
                cursor.execute("INSERT INTO settings (profile_id, monthly_income, savings_limit) VALUES (?, ?, ?)", (new_id, 0.0, 5000.0))
                conn.commit()
                st.success(f"Added {add_name}!")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("Profile name already exists.")
        else:
            st.error("Please enter a valid name.")

# --- FETCH PROFILE SETTINGS ---
cursor.execute("SELECT monthly_income, savings_limit FROM settings WHERE profile_id = ?", (profile_id,))
settings_data = cursor.fetchone()
if not settings_data:
    cursor.execute("INSERT INTO settings (profile_id, monthly_income, savings_limit) VALUES (?, ?, ?)", (profile_id, 0.0, 5000.0))
    conn.commit()
    monthly_income, savings_limit = 0.0, 5000.0
else:
    monthly_income, savings_limit = settings_data
    if savings_limit is None:
        savings_limit = 5000.0

# --- FETCH EXPENSES DATA ---
query = "SELECT id, date, category, amount, note FROM expenses WHERE profile_id = ?"
df_expenses = pd.read_sql_query(query, conn, params=(profile_id,))

total_spent = df_expenses['amount'].sum() if not df_expenses.empty else 0.0
current_savings = monthly_income - total_spent

# ==========================================
# --- SMART WARNING & ENCOURAGEMENT SYSTEM ---
# ==========================================
st.subheader("💡 Financial Health & Savings Watcher")

# Allow user to configure custom savings warning limit
with st.expander("⚙️ Configure Custom Savings Warning Limit"):
    new_limit = st.number_input(
        "Set your customized savings warning limit:",
        min_value=0.0,
        value=float(savings_limit),
        step=100.0
    )
    if st.button("Save Warning Limit"):
        cursor.execute("UPDATE settings SET savings_limit = ? WHERE profile_id = ?", (new_limit, profile_id))
        conn.commit()
        st.success("Savings limit updated successfully!")
        st.rerun()

is_tight_budget = monthly_income > 0 and monthly_income < 5000.0

# Dismissible Banner State for tight budgets
if "dismiss_banner" not in st.session_state:
    st.session_state.dismiss_banner = False

# Condition 1: For budgets below 5000 (Tight Budget)
if is_tight_budget:
    # Show encouraging message with dismissible 'X' button
    if not st.session_state.dismiss_banner:
        b_col1, b_col2 = st.columns([9, 1])
        with b_col1:
            st.info(
                "✨ **I know already your budget is tight, spend wisely and save for later!** "
                "Every single penny saved builds your path to financial freedom. You've got this! 💪",
                icon="🌟"
            )
        with b_col2:
            if st.button("❌", help="Dismiss reminder"):
                st.session_state.dismiss_banner = True
                st.rerun()

    # Only warn if savings go below their custom input limit (don't force default 5000 warning)
    if savings_limit > 0 and current_savings <= savings_limit:
        st.warning(f"🚨 **Alert:** Your savings have dropped below your custom warning threshold of {savings_limit:.2f}!", icon="⚠️")

# Condition 2: Standard Budgets (>= 5000 or income not set yet)
else:
    effective_limit = savings_limit if savings_limit > 0 else 5000.0
    
    # Warning when savings are close to limit (within 1000 above limit)
    if current_savings <= (effective_limit + 1000) and current_savings > effective_limit:
        st.warning(f"⚠️ **Spend Carefully:** Your savings ({current_savings:,.2f}) are getting close to your warning limit ({effective_limit:,.2f})!", icon="🟡")
    
    # Warning when savings drop below limit
    elif current_savings <= effective_limit:
        st.warning(f"🚨 **Warning:** Your savings have dropped below your safety limit of {effective_limit:,.2f}!", icon="🔴")


# --- MAIN APP TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "➕ Add Expense", "⚙️ Budget Setup", "📄 Reports"])

with tab1:
    st.header(f"Financial Overview for {selected_profile}")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Monthly Income", f"₹{monthly_income:,.2f}")
    col2.metric("Total Spent", f"₹{total_spent:,.2f}")
    col3.metric("Current Savings", f"₹{current_savings:,.2f}", delta=f"₹{current_savings:,.2f}")
    
    st.divider()
    st.subheader("Recent Expenses")
    if not df_expenses.empty:
        st.dataframe(df_expenses[['date', 'category', 'amount', 'note']], use_container_width=True)
    else:
        st.info("No expenses recorded yet. Use the 'Add Expense' tab to add your first transaction!")

with tab2:
    st.header("Add New Expense")
    with st.form("expense_form", clear_on_submit=True):
        date = st.date_input("Date", value=datetime.today())
        category = st.selectbox("Category", ["Food & Dining", "Bills & Utilities", "Shopping", "Transport", "Entertainment", "Health", "Other"])
        amount = st.number_input("Amount (₹)", min_value=0.0, step=1.0)
        note = st.text_area("Note / Description")
        
        submit_btn = st.form_submit_button("Add Expense")
        if submit_btn:
            if amount > 0:
                cursor.execute(
                    "INSERT INTO expenses (profile_id, date, category, amount, note) VALUES (?, ?, ?, ?, ?)",
                    (profile_id, str(date), category, amount, note)
                )
                conn.commit()
                st.success("Expense added successfully!")
                st.rerun()
            else:
                st.error("Please enter a valid amount greater than zero.")

with tab3:
    st.header("Budget & Profile Settings")
    new_income = st.number_input("Update Monthly Income (₹)", min_value=0.0, value=float(monthly_income), step=500.0)
    if st.button("Update Income"):
        cursor.execute("UPDATE settings SET monthly_income = ? WHERE profile_id = ?", (new_income, profile_id))
        conn.commit()
        st.success("Monthly income updated successfully!")
        st.rerun()

with tab4:
    st.header("Reports & PDF Summary")
    st.markdown("Download an organized summary report of your expenses and savings status.")
    
    if st.button("Generate PDF Report"):
        pdf_filename = f"{selected_profile}_finance_report.pdf"
        doc = SimpleDocTemplate(pdf_filename, pagesize=letter)
        elements = []
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1f4e78'),
            spaceAfter=12
        )
        
        elements.append(Paragraph(f"Financial Report: {selected_profile}", title_style))
        elements.append(Paragraph(f"Generated on: {datetime.today().strftime('%Y-%m-%d')}", styles['Normal']))
        elements.append(Spacer(1, 12))
        
        summary_data = [
            ["Metric", "Amount (₹)"],
            ["Monthly Income", f"{monthly_income:,.2f}"],
            ["Total Spent", f"{total_spent:,.2f}"],
            ["Current Savings", f"{current_savings:,.2f}"]
        ]
        t = Table(summary_data, colWidths=[200, 200])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1f4e78')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#f2f2f2')),
            ('GRID', (0,0), (-1,-1), 1, colors.black)
        ]))
        elements.append(t)
        doc.build(elements)
        
        with open(pdf_filename, "rb") as pdf_file:
            st.download_button(
                label="📥 Download PDF File",
                data=pdf_file,
                file_name=pdf_filename,
                mime="application/pdf"
            )
