import streamlit as st
st.set_page_config(layout="wide")  # Must be first Streamlit command
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import matplotlib.pyplot as plt
import plotly.express as px
from matplotlib.dates import DateFormatter
from datetime import date

# === Google Sheets Authentication ===
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_file(
    "ev-tracker-457704-9151025d6906.json",
    scopes=scope
)
client = gspread.authorize(creds)

# === Load all rows from Google Sheet ===
ws = client.open("EV Tracker").worksheet("Sheet1")
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

# Standardize expected columns
expected_cols = ["Date Placed", "Stake ($)", "EV", "Odds", "Profit/Loss", "Result", "Game Name", "Sport"]
for col in expected_cols:
    if col not in df.columns:
        df[col] = ""
df = df[expected_cols + ['SheetRow']]

# Clean and normalize data
df["Stake ($)"] = df["Stake ($)"].replace('[\$,]', '', regex=True).replace('', '0').astype(float)
df["Profit/Loss"] = df["Profit/Loss"].replace('[\$,]', '', regex=True).replace('', '0').astype(float)
# EV is now stored as decimal (e.g. 0.2 for 20%), so just cast
try:
    df['EV'] = df['EV'].astype(float)
except:
    df['EV'] = df['EV'].replace('%','', regex=True).replace('', '0').astype(float)

# Normalize missing values
df['Result'] = df['Result'].fillna('').replace('', 'Pending')
df['Sport'] = df['Sport'].fillna('').replace('', 'Unknown')

# Profit and Expected Profit calculations
def calc_real(r):
    if r['Result']=='Win': return r['Profit/Loss'] - r['Stake ($)']
    if r['Result']=='Loss': return -r['Stake ($)']
    if r['Result']=='Cashed Out': return r['Profit/Loss'] - r['Stake ($)']
    return 0

def calc_expected(r):
    # EV is decimal fraction, so expected profit = stake * EV
    return r['Stake ($)'] * r['EV']

df['Real Profit'] = df.apply(calc_real, axis=1)
df['Expected Profit'] = df.apply(calc_expected, axis=1)

# === Sidebar: Entry Form ===
st.sidebar.header("➕ Add New Bet")
with st.sidebar.form("add_bet_form"):
    new_date   = st.date_input("Date Placed", value=date.today())
    new_stake  = st.number_input("Stake ($)", min_value=0.0, format="%.2f")
    new_ev     = st.number_input("EV", min_value=0.0, format="%.3f")
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
# === Filters ===
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

# === Main Dashboard ===
st.title("📊 EV Betting Tracker Dashboard")
profit = df_filtered['Real Profit'].sum()
turnover = df_filtered['Stake ($)'].sum()
yield_pct = profit/turnover*100 if turnover else 0
roi_pct = profit/initial_capital*100 if initial_capital else 0
bets_count = len(df_filtered)
cols = st.columns(5)
cols[0].metric("Profit", f"A${profit:,.2f}")
cols[1].metric("Bets", f"{bets_count}")
cols[2].metric("Turnover", f"A${turnover:,.2f}")
cols[3].metric("Yield", f"{yield_pct:.2f}%")
cols[4].metric("ROI", f"{roi_pct:.2f}%")

# === Profit & Expected Chart with Range Slider and Hover ===
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
