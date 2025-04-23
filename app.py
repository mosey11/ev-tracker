import streamlit as st
st.set_page_config(layout="wide")  # Must be first Streamlit command

# === Password Protection ===
password = st.sidebar.text_input("Enter App Password:", type="password")
if "APP_PASSWORD" not in st.secrets or password != st.secrets["APP_PASSWORD"]:
    st.error("🔒 Incorrect password. Access denied.")
    st.stop()

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
from matplotlib.dates import DateFormatter
from datetime import date

# === Google Sheets Authentication using Streamlit Secrets ===
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ],
)
client = gspread.authorize(creds)
ws = client.open("EV Tracker").worksheet("Sheet1")

# === Load all rows from Google Sheet ===
all_values = ws.get_all_values()
if not all_values or len(all_values) < 2:
    st.error("No data found in the sheet.")
    st.stop()
headers = all_values[0]
records = []
for row in all_values[1:]:
    row_ext = row + [""] * (len(headers) - len(row))
    records.append(dict(zip(headers, row_ext)))
df = pd.DataFrame(records)
if not df.empty:
    df['SheetRow'] = df.index + 2

# === Standardize expected columns ===
expected_cols = ["Date Placed", "Stake ($)", "EV", "Odds", "Profit/Loss", "Result", "Game Name", "Sport"]
for col in expected_cols:
    if col not in df.columns:
        df[col] = ""
df = df[expected_cols + ['SheetRow']]

# === Clean and normalize data ===
df["Stake ($)"] = df["Stake ($)"].replace('[\$,]', '', regex=True).replace('', '0').astype(float)
df["Profit/Loss"] = df["Profit/Loss"].replace('[\$,]', '', regex=True).replace('', '0').astype(float)
# EV stored as decimal (e.g. 0.2 = 20%)
try:
    df['EV'] = df['EV'].astype(float)
except:
    df['EV'] = df['EV'].replace('%', '', regex=True).replace('', '0').astype(float)
# Normalize missing values
df['Result'] = df['Result'].fillna('').replace('', 'Pending')
df['Sport'] = df['Sport'].fillna('').replace('', 'Unknown')

# === Profit calculations ===
def calc_real(r):
    if r['Result'] == 'Win':
        return r['Profit/Loss'] - r['Stake ($)']
    if r['Result'] == 'Loss':
        return -r['Stake ($)']
    if r['Result'] == 'Cashed Out':
        return r['Profit/Loss'] - r['Stake ($)']
    return 0
def calc_expected(r):
    return r['Stake ($)'] * r['EV']
df['Real Profit'] = df.apply(calc_real, axis=1)
df['Expected Profit'] = df.apply(calc_expected, axis=1)

# === Sidebar: Entry Form ===
st.sidebar.header("➕ Add New Bet")
with st.sidebar.form("add_bet_form"):
    new_date   = st.date_input("Date Placed", value=date.today())
    new_stake  = st.number_input("Stake ($)", min_value=0.0, format="%.2f")
    new_ev     = st.number_input("EV (decimal)", min_value=0.0, format="%.3f")
    new_odds   = st.text_input("Odds")
    new_profit = st.number_input("Profit/Loss ($)", format="%.2f")
    new_result = st.selectbox("Result", ["Win","Loss","Cashed Out","Pending"], index=3)
    new_game   = st.text_input("Game Name")
    new_sport  = st.selectbox("Sport", ["Basketball","Football"], index=0)
    if st.form_submit_button("Add Bet"):
        ws.append_row([
            new_date.strftime("%d-%m-%Y"), new_stake, new_ev, new_odds, new_profit,
            new_result, new_game, new_sport
        ], value_input_option="USER_ENTERED")
        st.sidebar.success("Bet added! Refresh to update.")

st.sidebar.markdown("---")
# === Sidebar: Filters & Settings ===
st.sidebar.header("🔍 Filters & Settings")
dyn_results = df['Result'].unique().tolist()
dyn_sports = [s for s in df['Sport'].unique().tolist() if s!='Unknown']
selected_results = st.sidebar.multiselect("Result", dyn_results, default=dyn_results)
selected_sports = st.sidebar.multiselect("Sport", dyn_sports, default=dyn_sports)
initial_capital = st.sidebar.number_input("Initial Capital (A$)", min_value=0.0, value=500.0, step=50.0)

# === Filter data ===
df_filtered = df[df['Result'].isin(selected_results) & df['Sport'].isin(selected_sports)].copy()
if not df_filtered.empty:
    df_filtered['Date Placed'] = pd.to_datetime(df_filtered['Date Placed'], dayfirst=True, errors='coerce')
    df_filtered = df_filtered.dropna(subset=['Date Placed'])

# === Main Dashboard Metrics ===
st.title("📊 EV Betting Tracker Dashboard")
profit = df_filtered['Real Profit'].sum()
turnover = df_filtered['Stake ($)'].sum()
yield_pct = profit / turnover * 100 if turnover else 0
roi_pct = profit / initial_capital * 100 if initial_capital else 0
bets_count = len(df_filtered)
cols = st.columns(5)
cols[0].metric("Profit", f"A${profit:,.2f}")
cols[1].metric("Bets", f"{bets_count}")
cols[2].metric("Turnover", f"A${turnover:,.2f}")
cols[3].metric("Yield", f"{yield_pct:.2f}%")
cols[4].metric("ROI", f"{roi_pct:.2f}%")

# === Profit & Expected Chart with Range Slider ===
st.subheader("📈 Profit & Expected Profit Over Time")
chart_df = df_filtered.groupby('Date Placed')[['Real Profit','Expected Profit']].sum().cumsum().reset_index()
fig = px.line(
    chart_df,
    x='Date Placed',
    y=['Expected Profit','Real Profit'],
    labels={'value':'Cumulative Profit (A$)','variable':'Series','Date Placed':'Date'},
    title='Profit vs Expected Over Time'
)
fig.update_layout(
    xaxis_title='Date',
    yaxis_title='Cumulative Profit (A$)',
    xaxis=dict(rangeslider=dict(visible=True), type='date')
)
st.plotly_chart(fig, use_container_width=True)

# === Bet Details Table ===
st.subheader("📋 Bet Details")
st.dataframe(df_filtered[expected_cols])

st.markdown("---")
st.caption("Synced live with EV Tracker (Google Sheets)")
