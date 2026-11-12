
import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
import traceback


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

    def _init_cookies(self):

        try:
            self.session.get(self.base_url, timeout=15)
            time.sleep(1)

            self.session.get(
                f"{self.base_url}/option-chain",
                timeout=15
            )

            time.sleep(1)

        except requests.RequestException:
            pass

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

    @staticmethod
    def safe_number(value):

        try:
            if value is None:
                return np.nan

            number = pd.to_numeric(
                value,
                errors="coerce"
            )

            if pd.isna(number):
                return np.nan

            return float(number)

        except (TypeError, ValueError):
            return np.nan

    def _get_json(self, url):

        response = self.session.get(
            url,
            timeout=20
        )

        if response.status_code in (401, 403, 429):

            self._init_cookies()

            response = self.session.get(
                url,
                timeout=20
            )

        response.raise_for_status()

        return response.json()

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

    def fetch_option_chain(self, expiry):

        url = (
            f"{self.base_url}/api/option-chain-v3"
            f"?type=Indices&symbol={self.symbol}&expiry={expiry}"
        )

        return self._get_json(url)

    def fetch_option_greeks(self, expiry):

        url = (
            f"{self.base_url}/api/NextApi/apiClient/OptionGreekApi"
            f"?functionName=getOptionGreekTableData"
            f"&symbol={self.symbol}&params=expiryDate={expiry}"
        )

        return self._get_json(url)

    def process_option_chain(
        self,
        option_raw,
        greek_raw,
        expiry
    ):

        records_obj = option_raw.get("records", {})

        option_records = records_obj.get("data", [])

        spot_price = self.safe_number(
            records_obj.get("underlyingValue")
        )

        if pd.isna(spot_price) or spot_price <= 0:
            raise ValueError(
                "NSE Option Chain मधून Spot Price मिळाली नाही."
            )

        if not option_records:

            raise ValueError(
                "Option Chain मध्ये कोणताही डेटा उपलब्ध नाही."
            )

        selected_expiry_key = self.normalize_expiry(expiry)

        # ---------------------------------
        # Build Greek Lookup
        # ---------------------------------

        greek_lookup = {}

        greek_records = greek_raw.get("data", [])

        if not isinstance(greek_records, list):
            greek_records = []

        for item in greek_records:

            strike = item.get("strikePrice")

            item_expiry = self.normalize_expiry(
                item.get("expiryDates") or item.get("expiryDate")
            )

            if (
                strike is None
                or item_expiry != selected_expiry_key
            ):
                continue

            strike_key = self.safe_number(strike)

            if pd.isna(strike_key):
                continue

            ce = item.get("CE") or {}
            pe = item.get("PE") or {}

            greek_lookup[strike_key] = {

                "Call_Delta": self.safe_number(
                    ce.get("ogdDelta")
                ),

                "Call_Gamma": self.safe_number(
                    ce.get("ogdGamma")
                ),

                "Put_Delta": self.safe_number(
                    pe.get("ogdDelta")
                ),

                "Put_Gamma": self.safe_number(
                    pe.get("ogdGamma")
                )
            }

        # ---------------------------------
        # Process Option Chain Records
        # ---------------------------------

        rows = []

        for record in option_records:

            record_expiry = (
                record.get("expiryDates")
                or record.get("expiryDate")
            )

            if (
                self.normalize_expiry(record_expiry)
                != selected_expiry_key
            ):
                continue

            strike = self.safe_number(
                record.get("strikePrice")
            )

            if pd.isna(strike):
                continue

            ce = record.get("CE") or {}
            pe = record.get("PE") or {}

            greek = greek_lookup.get(strike, {})

            rows.append({

                "Strike": strike,

                "Call_OI": self.safe_number(
                    ce.get("openInterest")
                ),

                "Call_Change_OI": self.safe_number(
                    ce.get("changeinOpenInterest")
                ),

                "Call_LTP": self.safe_number(
                    ce.get("lastPrice")
                ),

                "Call_IV": self.safe_number(
                    ce.get("impliedVolatility")
                ),

                "Call_Delta": greek.get(
                    "Call_Delta", np.nan
                ),

                "Call_Gamma": greek.get(
                    "Call_Gamma", np.nan
                ),

                "Put_OI": self.safe_number(
                    pe.get("openInterest")
                ),

                "Put_Change_OI": self.safe_number(
                    pe.get("changeinOpenInterest")
                ),

                "Put_LTP": self.safe_number(
                    pe.get("lastPrice")
                ),

                "Put_IV": self.safe_number(
                    pe.get("impliedVolatility")
                ),

                "Put_Delta": greek.get(
                    "Put_Delta", np.nan
                ),

                "Put_Gamma": greek.get(
                    "Put_Gamma", np.nan
                )

            })

        if not rows:

            raise ValueError(
                "निवडलेल्या Expiry साठी Option Chain डेटा मिळाला नाही."
            )

        df = pd.DataFrame(rows)

        df = df.sort_values(
            "Strike"
        ).reset_index(drop=True)

        # ---------------------------------
        # Select ATM + 10 Strikes Above/Below
        # ---------------------------------

        if len(df) > 21:

            atm_idx = (
                df["Strike"] - spot_price
            ).abs().idxmin()

            start_idx = max(0, atm_idx - 10)

            end_idx = min(
                len(df),
                atm_idx + 11
            )

            df = df.iloc[
                start_idx:end_idx
            ].copy().reset_index(drop=True)

        # ---------------------------------
        # Reversal Calculations
        # ---------------------------------

        df["Call_Rev"] = np.nan
        df["Put_Rev"] = np.nan

        # Strike interval according to index

        if self.symbol == "NIFTY":

            strike_step = 50

        elif self.symbol in ["BANKNIFTY", "FINNIFTY"]:

            strike_step = 100

        else:

            strike_step = 50

        strike_lookup = df.set_index("Strike")

        for i, row in df.iterrows():

            k = row["Strike"]

            # =================================
            # EOR - CALL REVERSAL
            #
            # EOR = S - [CE(K+step) - PE(K)]
            #           / [CE Delta(K+step) - PE Delta(K)]
            # =================================

            if k + strike_step in strike_lookup.index:

                ce_high = strike_lookup.loc[
                    k + strike_step
                ]

                pe_current = strike_lookup.loc[k]

                ce_ltp = self.safe_number(
                    ce_high["Call_LTP"]
                )

                pe_ltp = self.safe_number(
                    pe_current["Put_LTP"]
                )

                ce_delta = self.safe_number(
                    ce_high["Call_Delta"]
                )

                pe_delta = self.safe_number(
                    pe_current["Put_Delta"]
                )

                if all(
                    np.isfinite(x)
                    for x in [
                        ce_ltp,
                        pe_ltp,
                        ce_delta,
                        pe_delta
                    ]
                ):

                    numerator = ce_ltp - pe_ltp

                    denominator = ce_delta - pe_delta

                    if denominator != 0:

                        df.loc[i, "Call_Rev"] = (
                            spot_price
                            - numerator / denominator
                        )

            # =================================
            # EOS - PUT REVERSAL
            #
            # EOS = S - [CE(K) - PE(K-step)]
            #           / [CE Delta(K) - PE Delta(K-step)]
            # =================================

            if k - strike_step in strike_lookup.index:

                ce_current = strike_lookup.loc[k]

                pe_low = strike_lookup.loc[
                    k - strike_step
                ]

                ce_ltp = self.safe_number(
                    ce_current["Call_LTP"]
                )

                pe_ltp = self.safe_number(
                    pe_low["Put_LTP"]
                )

                ce_delta = self.safe_number(
                    ce_current["Call_Delta"]
                )

                pe_delta = self.safe_number(
                    pe_low["Put_Delta"]
                )

                if all(
                    np.isfinite(x)
                    for x in [
                        ce_ltp,
                        pe_ltp,
                        ce_delta,
                        pe_delta
                    ]
                ):

                    numerator = ce_ltp - pe_ltp

                    denominator = ce_delta - pe_delta

                    if denominator != 0:

                        df.loc[i, "Put_Rev"] = (
                            spot_price
                            - numerator / denominator
                        )

        return df, spot_price, len(greek_lookup)

    def fetch_data(self, expiry):

        option_raw = self.fetch_option_chain(expiry)

        # Greek API failure should not stop Option Chain data

        try:

            greek_raw = self.fetch_option_greeks(expiry)

        except Exception:

            greek_raw = {"data": []}

        return self.process_option_chain(
            option_raw,
            greek_raw,
            expiry
        )


# ==========================================
# STREAMLIT DASHBOARD
# ==========================================

st.title(
    "📊 NSE Live Option Chain & Reversal Levels"
)

st.sidebar.header(
    "Dashboard Controls"
)

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

    col1.metric(
        "Index",
        symbol
    )

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
            "Greeks मिळाले नाहीत. Delta आणि Gamma रिकामे दाखवले जातील."
        )

    # ---------------------------------
    # Prepare Dashboard Table
    # ---------------------------------

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

    # Rename Columns

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
        "PUT Delta",
        "PUT Gamma"

    ]

    # ---------------------------------
    # Integer Formatting
    # ---------------------------------

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

    # ---------------------------------
    # Display Table
    # ---------------------------------

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

            "PUT Delta": "{:.4f}",
            "PUT Gamma": "{:.4f}"

        }, na_rep=""),

        width="stretch",
        hide_index=True

    )

    st.caption(
        "LTP, OI, Change in OI आणि IV हे Option Chain API मधून घेतले आहेत. "
        "Delta आणि Gamma हे स्वतंत्र Option Greek API मधून घेतले आहेत."
    )

except Exception as e:

    st.error(
        "NSE डेटा मिळवताना अडचण आली. काही वेळाने पुन्हा प्रयत्न करा."
    )

    st.error(f"तांत्रिक तपशील: {e}")

    st.code(
        traceback.format_exc()
    )


# ---------------------------------
# Auto Refresh
# ---------------------------------

if auto_refresh:

    time.sleep(refresh_rate)

    st.rerun()
