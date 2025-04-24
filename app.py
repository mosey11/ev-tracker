import streamlit as st
st.set_page_config(layout="wide")  # Must be first command

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
from datetime import date

# === Google Sheets Authentication using Streamlit Secrets ===
# Make sure you've added your full service-account JSON under [gcp_service_account] in Secrets
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ],
)
client = gspread.authorize(creds)
ws = client.open("EV Tracker").worksheet("Sheet1")

# === Load all rows ===
all_values = ws.get_all_values()
if len(all_values) < 2:
    st.error("No data found in the sheet.")
    st.stop()
headers = all_values[0]
records = [dict(zip(headers, row + [""]*(len(headers)-len(row)))) for row in all_values[1:]]
df = pd.DataFrame(records)

# === Ensure expected columns ===
expected_cols = ["Date Placed","Stake ($)","EV","Odds","Profit/Loss","Result","Game Name","Sport"]
for col in expected_cols:
    if col not in df.columns:
        df[col] = ""

# === Clean & normalize data ===
df["Stake ($)"] = df["Stake ($)"].replace('[\$,]', '', regex=True).fillna('0').astype(float)
df["Profit/Loss"] = df["Profit/Loss"].replace('[\$,]', '', regex=True).fillna('0').astype(float)
def parse_ev(val):
    try:
        return float(val)
    except:
        try:
            return float(val.replace('%',''))/100
        except:
            return 0.0
df['EV'] = df['EV'].apply(parse_ev)
df['Result'] = df['Result'].fillna('').replace('', 'Pending')
df['Sport'] = df['Sport'].fillna('').replace('', 'Unknown')

# === Profit calculations ===
def calc_real(r):
    if r['Result']=='Win': return r['Profit/Loss'] - r['Stake ($)']
    if r['Result']=='Loss': return -r['Stake ($)']
    if r['Result']=='Cashed Out': return r['Profit/Loss'] - r['Stake ($)']
    return 0
def calc_expected(r): return r['Stake ($)'] * r['EV']
df['Real Profit'] = df.apply(calc_real, axis=1)
df['Expected Profit'] = df.apply(calc_expected, axis=1)

# === Sidebar: Add New Bet ===
st.sidebar.header("➕ Add New Bet")
with st.sidebar.form("add_bet_form"):
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
# === Sidebar: Filters & Settings ===
selected_results = st.sidebar.multiselect(
    "Result", df['Result'].unique().tolist(), default=df['Result'].unique().tolist()
)
selected_sports = st.sidebar.multiselect(
    "Sport", [s for s in df['Sport'].unique() if s!='Unknown'],
    default=[s for s in df['Sport'].unique() if s!='Unknown']
)
initial_capital = st.sidebar.number_input("Initial Capital (A$)", min_value=0.0, value=500.0, step=50.0)

# === Filter data ===
df_f = df[df['Result'].isin(selected_results) & df['Sport'].isin(selected_sports)].copy()
if not df_f.empty:
    df_f['Date Placed'] = pd.to_datetime(df_f['Date Placed'], dayfirst=True, errors='coerce')
    df_f = df_f.dropna(subset=['Date Placed'])

# === Metrics ===
st.title("📊 EV Betting Tracker Dashboard")
profit = df_f['Real Profit'].sum()
turnover = df_f['Stake ($)'].sum()
yield_pct = profit/turnover*100 if turnover else 0
roi_pct = profit/initial_capital*100 if initial_capital else 0
bets_count = len(df_f)
cols = st.columns(5)
cols[0].metric("Profit", f"A${profit:,.2f}")
cols[1].metric("Bets", f"{bets_count}")
cols[2].metric("Turnover", f"A${turnover:,.2f}")
cols[3].metric("Yield", f"{yield_pct:.2f}%")
cols[4].metric("ROI", f"{roi_pct:.2f}%")

# === Chart ===
st.subheader("📈 Profit & Expected Profit Over Time")
chart_df = df_f.groupby('Date Placed')[['Real Profit','Expected Profit']].sum().cumsum().reset_index()
fig = px.line(
    chart_df,
    x='Date Placed',
    y=['Expected Profit','Real Profit'],
    title='Profit vs Expected Over Time',
    labels={'value':'Cumulative Profit (A$)'}
)
fig.update_layout(xaxis=dict(rangeslider=dict(visible=True), type='date'))
st.plotly_chart(fig, use_container_width=True)

# === Table ===
st.subheader("📋 Bet Details")
st.dataframe(df_f[expected_cols])
