
import streamlit as st
import pandas as pd
import numpy as np
import requests
import time


st.set_page_config(
    page_title="NSE Option Chain & Reversal Dashboard",
    layout="wide"
)


class NSEOptionChainFetcher:

    def __init__(self, symbol="NIFTY"):
        self.symbol = symbol.upper()
        self.base_url = "https://www.nseindia.com"

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://www.nseindia.com/option-chain",
            "X-Requested-With": "XMLHttpRequest",
            "Connection": "keep-alive"
        }

        self.session = requests.Session()
        self.session.headers.update(self.headers)

        self._init_cookies()

    # ---------------- COOKIE INITIALIZATION ----------------

    def _init_cookies(self):

        try:
            pages = [
                self.base_url,
                f"{self.base_url}/option-chain",
                f"{self.base_url}/market-data/option-greek"
            ]

            for page in pages:

                response = self.session.get(
                    page,
                    timeout=20
                )

                print("NSE Page:", page)
                print("Status:", response.status_code)

                time.sleep(1)

            print(
                "Cookie Names:",
                list(self.session.cookies.keys())
            )

        except requests.RequestException as e:
            print("NSE Cookie Error:", str(e))

    # ---------------- EXPIRY NORMALIZATION ----------------

    @staticmethod
    def normalize_expiry(value):

        if not value:
            return None

        parsed = pd.to_datetime(
            value,
            errors="coerce",
            dayfirst=True
        )

        if pd.isna(parsed):
            return None

        return parsed.strftime("%Y-%m-%d")

    # ---------------- JSON REQUEST ----------------

    def _get_json(self, url):

        response = self.session.get(
            url,
            timeout=25
        )

        if response.status_code in (401, 403, 429):

            print("NSE Request Error:", response.status_code)

            self._init_cookies()

            response = self.session.get(
                url,
                timeout=25
            )

        response.raise_for_status()

        return response.json()

    # ---------------- EXPIRY DATES ----------------

    def get_expiry_dates(self):

        url = (
            f"{self.base_url}/api/option-chain-contract-info"
            f"?symbol={self.symbol}"
        )

        raw_data = self._get_json(url)

        expiry_dates = raw_data.get("expiryDates", [])

        if not expiry_dates:

            records = raw_data.get("records", {})

            if isinstance(records, dict):
                expiry_dates = records.get("expiryDates", [])

        if not expiry_dates:

            raise ValueError(
                "NSE API मधून Expiry Dates मिळाल्या नाहीत. "
                f"Response: {str(raw_data)[:500]}"
            )

        return expiry_dates

    # ---------------- OPTION CHAIN API ----------------

    def fetch_option_chain(self, expiry):

        url = (
            f"{self.base_url}/api/option-chain-v3"
            f"?type=Indices&symbol={self.symbol}&expiry={expiry}"
        )

        return self._get_json(url)

    # ---------------- OPTION GREEK API ----------------

    def fetch_option_greeks(self, expiry):

        url = (
            f"{self.base_url}/api/NextApi/apiClient/OptionGreekApi"
            f"?functionName=getOptionGreekTableData"
            f"&symbol={self.symbol}&params=expiryDate={expiry}"
        )

        headers = {
            "Referer": (
                "https://www.nseindia.com/market-data/option-greek"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest"
        }

        response = self.session.get(
            url,
            headers=headers,
            timeout=25
        )

        print("Greek API Status:", response.status_code)

        print(
            "Greek Content Type:",
            response.headers.get("Content-Type")
        )

        print(
            "Greek Response:",
            response.text[:500]
        )

        response.raise_for_status()

        return response.json()

    # ---------------- PROCESS OPTION CHAIN ----------------

    def process_option_chain(self, option_raw, greek_raw, expiry):

        records_obj = option_raw.get("records", {})

        option_records = records_obj.get("data", [])

        spot_price = records_obj.get("underlyingValue", 0)

        if not option_records:
            raise ValueError(
                "Option Chain मध्ये कोणताही डेटा उपलब्ध नाही."
            )

        selected_expiry_key = self.normalize_expiry(expiry)

        greek_lookup = {}

        greek_data = greek_raw.get("data", [])

        if not isinstance(greek_data, list):
            greek_data = []

        for item in greek_data:

            strike = item.get("strikePrice")

            item_expiry = self.normalize_expiry(
                item.get("expiryDates") or item.get("expiryDate")
            )

            if strike is None or item_expiry != selected_expiry_key:
                continue

            try:
                strike_key = float(strike)
            except (TypeError, ValueError):
                continue

            ce_greek = item.get("CE") or {}
            pe_greek = item.get("PE") or {}

            greek_lookup[strike_key] = {

                "Call_Delta": ce_greek.get(
                    "ogdDelta", np.nan
                ),

                "Call_Gamma": ce_greek.get(
                    "ogdGamma", np.nan
                ),

                "Call_Theta": ce_greek.get(
                    "ogdTheta", np.nan
                ),

                "Call_Vega": ce_greek.get(
                    "ogdVega", np.nan
                ),

                "Call_IV_Greek": ce_greek.get(
                    "ogdIv", np.nan
                ),

                "Call_Trade_Price": ce_greek.get(
                    "ogdLtp", np.nan
                ),

                "Put_Delta": pe_greek.get(
                    "ogdDelta", np.nan
                ),

                "Put_Gamma": pe_greek.get(
                    "ogdGamma", np.nan
                ),

                "Put_Theta": pe_greek.get(
                    "ogdTheta", np.nan
                ),

                "Put_Vega": pe_greek.get(
                    "ogdVega", np.nan
                ),

                "Put_IV_Greek": pe_greek.get(
                    "ogdIv", np.nan
                ),

                "Put_Trade_Price": pe_greek.get(
                    "ogdLtp", np.nan
                )
            }

        rows = []

        for record in option_records:

            record_expiry = (
                record.get("expiryDates") or
                record.get("expiryDate")
            )

            if self.normalize_expiry(record_expiry) != selected_expiry_key:
                continue

            strike = record.get("strikePrice")

            if strike is None:
                continue

            try:
                strike_key = float(strike)
            except (TypeError, ValueError):
                continue

            ce = record.get("CE") or {}
            pe = record.get("PE") or {}

            greek = greek_lookup.get(strike_key, {})

            rows.append({

                "Strike": strike_key,

                "Call_OI": ce.get("openInterest", 0),
                "Call_Change_OI": ce.get("changeinOpenInterest", 0),
                "Call_LTP": ce.get("lastPrice", 0),
                "Call_IV": ce.get("impliedVolatility", 0),

                "Call_Delta": greek.get("Call_Delta", np.nan),
                "Call_Gamma": greek.get("Call_Gamma", np.nan),
                "Call_Theta": greek.get("Call_Theta", np.nan),
                "Call_Vega": greek.get("Call_Vega", np.nan),

                "Call_IV_Greek": greek.get("Call_IV_Greek", np.nan),
                "Call_Trade_Price": greek.get("Call_Trade_Price", np.nan),

                "Put_OI": pe.get("openInterest", 0),
                "Put_Change_OI": pe.get("changeinOpenInterest", 0),
                "Put_LTP": pe.get("lastPrice", 0),
                "Put_IV": pe.get("impliedVolatility", 0),

                "Put_Delta": greek.get("Put_Delta", np.nan),
                "Put_Gamma": greek.get("Put_Gamma", np.nan),
                "Put_Theta": greek.get("Put_Theta", np.nan),
                "Put_Vega": greek.get("Put_Vega", np.nan),

                "Put_IV_Greek": greek.get("Put_IV_Greek", np.nan),
                "Put_Trade_Price": greek.get("Put_Trade_Price", np.nan)
            })

        if not rows:

            raise ValueError(
                "निवडलेल्या Expiry साठी Option Chain डेटा मिळाला नाही."
            )

        df = pd.DataFrame(rows)

        df = df.sort_values("Strike").reset_index(drop=True)

        # ATM + 10 strikes above and below

        if spot_price and spot_price > 0:

            atm_idx = (
                df["Strike"] - spot_price
            ).abs().idxmin()

            start_idx = max(0, atm_idx - 10)

            end_idx = min(len(df), atm_idx + 11)

            df = df.iloc[
                start_idx:end_idx
            ].copy().reset_index(drop=True)

        # ---------------- REVERSAL CALCULATIONS ----------------

        df["Call_Rev"] = np.nan
        df["Put_Rev"] = np.nan

        if self.symbol == "NIFTY":
            strike_step = 50

        elif self.symbol in ["BANKNIFTY", "FINNIFTY"]:
            strike_step = 100

        else:
            strike_step = 50

        strike_lookup = df.set_index("Strike")

        for i, row in df.iterrows():

            k = row["Strike"]

            if k + strike_step in strike_lookup.index:

                ce_high = strike_lookup.loc[k + strike_step]
                pe_current = strike_lookup.loc[k]

                numerator = (
                    ce_high["Call_LTP"] -
                    pe_current["Put_LTP"]
                )

                denominator = (
                    ce_high["Call_Delta"] -
                    pe_current["Put_Delta"]
                )

                if (
                    pd.notna(numerator)
                    and pd.notna(denominator)
                    and denominator != 0
                ):

                    df.loc[i, "Call_Rev"] = (
                        spot_price - numerator / denominator
                    )

            if k - strike_step in strike_lookup.index:

                ce_current = strike_lookup.loc[k]
                pe_low = strike_lookup.loc[k - strike_step]

                numerator = (
                    ce_current["Call_LTP"] -
                    pe_low["Put_LTP"]
                )

                denominator = (
                    ce_current["Call_Delta"] -
                    pe_low["Put_Delta"]
                )

                if (
                    pd.notna(numerator)
                    and pd.notna(denominator)
                    and denominator != 0
                ):

                    df.loc[i, "Put_Rev"] = (
                        spot_price - numerator / denominator
                    )

        return df, spot_price, len(greek_lookup)

    # ---------------- FETCH ALL DATA ----------------

    def fetch_data(self, expiry):

        option_raw = self.fetch_option_chain(expiry)

        try:

            greek_raw = self.fetch_option_greeks(expiry)

        except Exception as e:

            print("Greek API Error:", str(e))

            st.warning(
                f"Option Greek API Error: {str(e)}"
            )

            greek_raw = {"data": []}

        return self.process_option_chain(
            option_raw,
            greek_raw,
            expiry
        )


# ============================================================
# STREAMLIT DASHBOARD
# ============================================================

st.title("📊 NSE Live Option Chain & Reversal Levels")

st.sidebar.header("Dashboard Controls")

symbol = st.sidebar.selectbox(
    "Select Index",
    ["NIFTY", "BANKNIFTY", "FINNIFTY"]
)

refresh_rate = st.sidebar.slider(
    "Auto-Refresh Interval (Seconds)",
    5,
    60,
    10
)

auto_refresh = st.sidebar.checkbox(
    "Enable Auto Refresh",
    value=False
)

manual_refresh = st.sidebar.button(
    "🔄 REFRESH NSE DATA",
    use_container_width=True
)

fetcher = NSEOptionChainFetcher(symbol)

try:

    expiry_dates = fetcher.get_expiry_dates()

    selected_expiry = st.sidebar.selectbox(
        "Select Expiry",
        expiry_dates,
        index=0
    )

    with st.spinner(
        "NSE मधून Option Chain आणि Greeks डेटा घेत आहे..."
    ):

        df, spot_price, greek_count = fetcher.fetch_data(
            selected_expiry
        )

    st.success(
        f"Live {symbol} Spot Price: ₹{spot_price:,.2f}"
    )

    col1, col2, col3 = st.columns(3)

    col1.metric("Index", symbol)

    col2.metric(
        "Spot Price",
        f"₹{spot_price:,.2f}"
    )

    col3.metric(
        "Expiry",
        selected_expiry
    )

    if greek_count == 0:

        st.warning(
            "Option Chain डेटा मिळाला आहे; पण Option Greek API मधून "
            "Greeks मिळाले नाहीत."
        )

    # ---------------- DISPLAY TABLE ----------------

    display_df = df[[

        "Call_Gamma",
        "Call_Delta",
        "Call_OI",
        "Call_Change_OI",
        "Call_LTP",
        "Call_IV",
        "Call_Rev",
        "Strike",
        "Put_Rev",
        "Put_IV",
        "Put_LTP",
        "Put_Change_OI",
        "Put_OI",
        "Put_Delta",
        "Put_Gamma"

    ]].copy()

    display_df.columns = [

        "CALL Gamma",
        "CALL Delta",
        "CALL OI",
        "CALL Change In OI",
        "CALL LTP",
        "CALL IV",
        "Call Rev LTP/Spot",
        "SP",
        "Put Rev LTP/Spot",
        "PUT IV",
        "PUT LTP",
        "PUT Change In OI",
        "PUT OI",
        "Put Delta",
        "Put Gamma"

    ]

    integer_columns = [
        "SP",
        "Call Rev LTP/Spot",
        "Put Rev LTP/Spot"
    ]

    for col in integer_columns:

        display_df[col] = pd.to_numeric(
            display_df[col],
            errors="coerce"
        ).round(0).astype("Int64")

    st.dataframe(

        display_df.style.format({

            "CALL Gamma": "{:.4f}",
            "CALL Delta": "{:.4f}",
            "CALL OI": "{:,.0f}",
            "CALL Change In OI": "{:,.0f}",
            "CALL LTP": "{:.2f}",
            "CALL IV": "{:.2f}",
            "PUT IV": "{:.2f}",
            "PUT LTP": "{:.2f}",
            "PUT Change In OI": "{:,.0f}",
            "PUT OI": "{:,.0f}",
            "Put Delta": "{:.4f}",
            "Put Gamma": "{:.4f}"

        }, na_rep=""),

        use_container_width=True,
        hide_index=True
    )

    st.caption(
        "LTP, OI, Change in OI आणि IV हे Option Chain API मधून घेतले आहेत. "
        "Delta, Gamma, Theta आणि Vega हे Option Greek API मधून घेतले आहेत."
    )

except Exception as e:

    st.error(
        "NSE डेटा मिळवताना अडचण आली. काही वेळाने पुन्हा प्रयत्न करा."
    )

    st.caption(
        f"तांत्रिक तपशील: {e}"
    )


# ---------------- AUTO REFRESH ----------------

if auto_refresh:

    time.sleep(refresh_rate)

    st.rerun()
