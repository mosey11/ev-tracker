import streamlit as st
st.set_page_config(layout="wide")  # Must be first command

# === Password Protection ===
password = st.sidebar.text_input("Enter App Password:", type="password")
if "APP_PASSWORD" not in st.secrets or password != st.secrets["APP_PASSWORD"]:
    st.error("🔒 Incorrect password. Access denied.")
    st.stop()

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
from datetime import date

# === Google Sheets Authentication using Streamlit Secrets ===
service_account_info = st.secrets.get("gcp_service_account")
if service_account_info is None:
    st.error("GCP service account credentials not found in secrets.")
    st.stop()
# Fix newline escaping
if "private_key" in service_account_info:
    service_account_info["private_key"] = service_account_info["private_key"].replace('\\n', '\n')
creds = Credentials.from_service_account_info(
    service_account_info,
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ],
)
client = gspread.authorize(creds)
ws = client.open("EV Tracker").worksheet("Sheet1")

# === Load data ===
all_values = ws.get_all_values()
if len(all_values) < 2:
    st.error("No data found in the sheet.")
    st.stop()
headers = all_values[0]
records = [dict(zip(headers, row + [""]*(len(headers)-len(row)))) for row in all_values[1:]]
df = pd.DataFrame(records)

# === Standardize expected columns ===
expected_cols = ["Date Placed","Stake ($)","EV","Odds","Profit/Loss","Result","Game Name","Sport"]
for col in expected_cols:
    if col not in df.columns:
        df[col] = ""
df['SheetRow'] = df.index + 2

# === Clean & Normalize ===
df["Stake ($)"] = df["Stake ($)"].replace('[\$,]', '', regex=True).replace('', '0').astype(float)
df["Profit/Loss"] = df["Profit/Loss"].replace('[\$,]', '', regex=True).replace('', '0').astype(float)
# EV as decimal or percent fallback
def parse_ev(val):
    try:
        return float(val)
    except:
        try:
            return float(val.replace('%',''))/100
        except:
            return 0.0

df['EV'] = df['EV'].apply(parse_ev)
# Normalize missing
for col in ['Result','Sport']:
    df[col] = df[col].fillna('').replace('', 'Pending' if col=='Result' else 'Unknown')

# === Profit calculations ===
def calc_real(r):
    if r['Result']=='Win': return r['Profit/Loss'] - r['Stake ($)']
    if r['Result']=='Loss': return -r['Stake ($)']
    if r['Result']=='Cashed Out': return r['Profit/Loss'] - r['Stake ($)']
    return 0
def calc_expected(r):
    return r['Stake ($)'] * r['EV']

df['Real Profit'] = df.apply(calc_real, axis=1)
df['Expected Profit'] = df.apply(calc_expected, axis=1)

# === Sidebar: Add Bet ===
st.sidebar.header("➕ Add New Bet")
with st.sidebar.form("add_form"):
    new_date = st.date_input("Date Placed", value=date.today())
    new_stake = st.number_input("Stake ($)", min_value=0.0, format="%.2f")
    new_ev = st.number_input("EV (decimal)", min_value=0.0, format="%.3f")
    new_odds = st.text_input("Odds")
    new_profit = st.number_input("Profit/Loss ($)", format="%.2f")
    new_result = st.selectbox("Result", ["Win","Loss","Cashed Out","Pending"], index=3)
    new_game = st.text_input("Game Name")
    new_sport = st.selectbox("Sport", ["Basketball","Football"], index=0)
    if st.form_submit_button("Add Bet"):
        ws.append_row([
            new_date.strftime("%d-%m-%Y"), new_stake, new_ev, new_odds, new_profit,
            new_result, new_game, new_sport
        ], value_input_option="USER_ENTERED")
        st.sidebar.success("Bet added! Refresh to update.")

st.sidebar.markdown("---")
st.sidebar.header("🔍 Filters & Settings")
dyn_results = df['Result'].unique().tolist()
dyn_sports = [s for s in df['Sport'].unique() if s!='Unknown']
selected_results = st.sidebar.multiselect("Result", dyn_results, default=dyn_results)
selected_sports = st.sidebar.multiselect("Sport", dyn_sports, default=dyn_sports)
initial_capital = st.sidebar.number_input("Initial Capital (A$)", min_value=0.0, value=500.0, step=50.0)

# === Filter data ===
df_f = df[df['Result'].isin(selected_results) & df['Sport'].isin(selected_sports)].copy()
if not df_f.empty:
    df_f['Date Placed'] = pd.to_datetime(df_f['Date Placed'], dayfirst=True, errors='coerce')
    df_f = df_f.dropna(subset=['Date Placed'])

# === Main metrics ===
st.title("📊 EV Betting Tracker Dashboard")
profit = df_f['Real Profit'].sum()
turnover = df_f['Stake ($)'].sum()
yield_pct = profit/turnover*100 if turnover else 0
roi_pct = profit/initial_capital*100 if initial_capital else 0
bets = len(df_f)
cols = st.columns(5)
cols[0].metric("Profit", f"A${profit:,.2f}")
cols[1].metric("Bets", f"{bets}")
cols[2].metric("Turnover", f"A${turnover:,.2f}")
cols[3].metric("Yield", f"{yield_pct:.2f}%")
cols[4].metric("ROI", f"{roi_pct:.2f}%")

# === Chart ===
st.subheader("📈 Profit & Expected Over Time")
chart_df = df_f.groupby('Date Placed')[['Real Profit','Expected Profit']].sum().cumsum().reset_index()
fig=px.line(chart_df,x='Date Placed',y=['Expected Profit','Real Profit'],labels={'value':'Cumulative Profit (A$)'},title='Profit vs Expected')
fig.update_layout(xaxis=dict(rangeslider=dict(visible=True),type='date'))
st.plotly_chart(fig,use_container_width=True)

# === Table ===
st.subheader("📋 Bet Details")
st.dataframe(df_f[expected_cols])
