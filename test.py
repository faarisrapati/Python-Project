import streamlit as st
import yfinance as yf
import talib as ta

st.title("CandleCall - Deployment Test")

ticker = st.selectbox(
    "Choose a stock",
    ["AAPL", "MSFT", "NVDA"]
)

@st.cache_data(ttl=3600)
def get_stock_data(symbol):
    return yf.Ticker(symbol).history(
        period="1y",
        auto_adjust=True
    )

try:
    df = get_stock_data(ticker)

    if df.empty:
        st.error("No stock data returned.")
        st.stop()

    df["EMA_20"] = ta.EMA(
        df["Close"],
        timeperiod=20
    )

    df["RSI"] = ta.RSI(
        df["Close"],
        timeperiod=14
    )

    st.success("TA-Lib is working!")

    st.line_chart(
        df[["Close", "EMA_20"]]
    )

    st.metric(
        "Latest RSI",
        f"{df['RSI'].iloc[-1]:.2f}"
    )

except Exception as e:
    st.error(f"Test failed: {e}")