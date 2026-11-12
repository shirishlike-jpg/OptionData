
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
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://www.nseindia.com/option-chain",
            "X-Requested-With": "XMLHttpRequest",
            "Connection": "keep-alive"
        }

        self.session = requests.Session()
        self.session.headers.update(self.headers)

        self._init_cookies()

    # --------------------------------------------------
    # INITIALIZE NSE COOKIES
    # --------------------------------------------------

    def _init_cookies(self):

        urls = [
            self.base_url,
            self.base_url + "/option-chain",
            self.base_url + "/market-data/option-greek"
        ]

        for url in urls:
            try:
                response = self.session.get(
                    url,
                    timeout=15
                )
                print(
                    "Cookie URL:",
                    url,
                    response.status_code
                )
            except Exception as e:
                print("Cookie Error:", e)

    # --------------------------------------------------
    # SAFE NUMBER CONVERSION
    # --------------------------------------------------

    @staticmethod
    def safe_number(value):

        try:
            number = pd.to_numeric(
                value,
                errors="coerce"
            )

            if pd.isna(number):
                return np.nan

            number = float(number)

            if not np.isfinite(number):
                return np.nan

            return number

        except Exception:
            return np.nan

    # --------------------------------------------------
    # EXPIRY NORMALIZATION
    # --------------------------------------------------

    @staticmethod
    def normalize_expiry(value):

        try:
            date_value = pd.to_datetime(
                value,
                errors="coerce",
                dayfirst=True
            )

            if pd.isna(date_value):
                return None

            return date_value.strftime("%Y-%m-%d")

        except Exception:
            return None

    # --------------------------------------------------
    # GET JSON
    # --------------------------------------------------

    def _get_json(self, url):

        response = self.session.get(
            url,
            timeout=25
        )

        if response.status_code in [401, 403, 429]:

            self._init_cookies()

            response = self.session.get(
                url,
                timeout=25
            )

        response.raise_for_status()

        return response.json()

    # --------------------------------------------------
    # GET EXPIRY DATES
    # --------------------------------------------------

    def get_expiry_dates(self):

        url = (
            f"{self.base_url}/api/"
            f"option-chain-contract-info?"
            f"symbol={self.symbol}"
        )

        data = self._get_json(url)

        expiry_dates = (
            data.get("expiryDates")
            or data.get("records", {}).get("expiryDates")
            or []
        )

        return expiry_dates

    # --------------------------------------------------
    # FETCH OPTION CHAIN
    # --------------------------------------------------

    def fetch_option_chain(self, expiry):

        url = (
            f"{self.base_url}/api/option-chain-v3?"
            f"type=Indices&symbol={self.symbol}"
            f"&expiry={expiry}"
        )

        return self._get_json(url)

    # --------------------------------------------------
    # FETCH OPTION GREEKS
    # --------------------------------------------------

    def fetch_option_greeks(self, expiry):

        url = (
            f"{self.base_url}/api/NextApi/apiClient/"
            f"OptionGreekApi?"
            f"functionName=getOptionGreekTableData"
            f"&symbol={self.symbol}"
            f"&params=expiryDate={expiry}"
        )

        self.session.headers.update({
            "Referer": (
                "https://www.nseindia.com/"
                "market-data/option-greek"
            )
        })

        response = self.session.get(
            url,
            timeout=25
        )

        print("Greek API Status:", response.status_code)
        print("Greek API Content:", response.text[:500])

        response.raise_for_status()

        return response.json()

    # --------------------------------------------------
    # PROCESS OPTION CHAIN
    # --------------------------------------------------

    def process_option_chain(
        self,
        option_raw,
        greek_raw,
        expiry
    ):

        records_obj = option_raw.get("records", {})

        # Validate Spot Price
        spot_price = pd.to_numeric(
            records_obj.get("underlyingValue"),
            errors="coerce"
        )

        if pd.isna(spot_price) or spot_price <= 0:
            raise ValueError(
                "NSE कडून योग्य Spot Price मिळाली नाही."
            )

        spot_price = float(spot_price)

        option_data = records_obj.get("data", [])

        selected_expiry = self.normalize_expiry(expiry)

        # --------------------------------------------------
        # FILTER EXPIRY
        # --------------------------------------------------

        filtered_data = []

        for item in option_data:

            item_expiry = self.normalize_expiry(
                item.get("expiryDate")
            )

            if item_expiry == selected_expiry:
                filtered_data.append(item)

        # --------------------------------------------------
        # GREEK LOOKUP
        # --------------------------------------------------

        greek_lookup = {}

        greek_data = (
            greek_raw.get("data", [])
            if isinstance(greek_raw, dict)
            else []
        )

        for item in greek_data:

            try:
                strike = self.safe_number(
                    item.get("strikePrice")
                )

                if pd.isna(strike):
                    strike = self.safe_number(
                        item.get("ogdStrikePrice")
                    )

                if pd.isna(strike):
                    continue

                greek_lookup[strike] = {
                    "CE": item.get("CE", {}),
                    "PE": item.get("PE", {})
                }

            except Exception as e:
                print("Greek Parsing Error:", e)

        # --------------------------------------------------
        # BUILD OPTION CHAIN ROWS
        # --------------------------------------------------

        rows = []

        for item in filtered_data:

            strike = self.safe_number(
                item.get("strikePrice")
            )

            if pd.isna(strike):
                continue

            ce = item.get("CE") or {}
            pe = item.get("PE") or {}

            greek = greek_lookup.get(
                strike,
                {}
            )

            ce_greek = greek.get("CE") or {}
            pe_greek = greek.get("PE") or {}

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

                "Call_Delta": self.safe_number(
                    ce_greek.get("ogdDelta")
                ),

                "Call_Gamma": self.safe_number(
                    ce_greek.get("ogdGamma")
                ),

                "Call_Theta": self.safe_number(
                    ce_greek.get("ogdTheta")
                ),

                "Call_Vega": self.safe_number(
                    ce_greek.get("ogdVega")
                ),

                "Call_IV_Greek": self.safe_number(
                    ce_greek.get("ogdIv")
                ),

                "Call_Trade_Price": self.safe_number(
                    ce_greek.get("ogdLtp")
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

                "Put_Delta": self.safe_number(
                    pe_greek.get("ogdDelta")
                ),

                "Put_Gamma": self.safe_number(
                    pe_greek.get("ogdGamma")
                ),

                "Put_Theta": self.safe_number(
                    pe_greek.get("ogdTheta")
                ),

                "Put_Vega": self.safe_number(
                    pe_greek.get("ogdVega")
                ),

                "Put_IV_Greek": self.safe_number(
                    pe_greek.get("ogdIv")
                ),

                "Put_Trade_Price": self.safe_number(
                    pe_greek.get("ogdLtp")
                )

            })

        df = pd.DataFrame(rows)

        if df.empty:
            raise ValueError(
                "निवडलेल्या Expiry साठी Option Chain डेटा उपलब्ध नाही."
            )

        df = df.sort_values(
            "Strike"
        ).reset_index(drop=True)

        # --------------------------------------------------
        # NUMERIC CONVERSION
        # --------------------------------------------------

        numeric_columns = [
            col for col in df.columns
            if col != "Strike"
        ]

        for col in numeric_columns:
            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            )

        # --------------------------------------------------
        # REVERSAL CALCULATIONS
        # --------------------------------------------------

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

            if pd.isna(k):
                continue

            # ----------------------------------------------
            # CALL REVERSAL
            # ----------------------------------------------

            next_strike = k + strike_step

            if next_strike in strike_lookup.index:

                ce_high = strike_lookup.loc[next_strike]
                pe_current = strike_lookup.loc[k]

                ce_ltp = ce_high["Call_LTP"]
                pe_ltp = pe_current["Put_LTP"]

                ce_delta = ce_high["Call_Delta"]
                pe_delta = pe_current["Put_Delta"]

                values = [
                    ce_ltp,
                    pe_ltp,
                    ce_delta,
                    pe_delta
                ]

                if all(pd.notna(v) for v in values):

                    numerator = ce_ltp - pe_ltp
                    denominator = ce_delta - pe_delta

                    if denominator != 0:

                        reversal = (
                            spot_price
                            - numerator / denominator
                        )

                        if np.isfinite(reversal):
                            df.loc[i, "Call_Rev"] = reversal

            # ----------------------------------------------
            # PUT REVERSAL
            # ----------------------------------------------

            previous_strike = k - strike_step

            if previous_strike in strike_lookup.index:

                ce_current = strike_lookup.loc[k]
                pe_low = strike_lookup.loc[previous_strike]

                ce_ltp = ce_current["Call_LTP"]
                pe_ltp = pe_low["Put_LTP"]

                ce_delta = ce_current["Call_Delta"]
                pe_delta = pe_low["Put_Delta"]

                values = [
                    ce_ltp,
                    pe_ltp,
                    ce_delta,
                    pe_delta
                ]

                if all(pd.notna(v) for v in values):

                    numerator = ce_ltp - pe_ltp
                    denominator = ce_delta - pe_delta

                    if denominator != 0:

                        reversal = (
                            spot_price
                            - numerator / denominator
                        )

                        if np.isfinite(reversal):
                            df.loc[i, "Put_Rev"] = reversal

        # --------------------------------------------------
        # SELECT ATM +/- 10 STRIKES
        # --------------------------------------------------

        atm_index = (
            df["Strike"] - spot_price
        ).abs().idxmin()

        start_index = max(
            0,
            atm_index - 10
        )

        end_index = min(
            len(df),
            atm_index + 11
        )

        df = df.iloc[
            start_index:end_index
        ].copy()

        df = df.reset_index(
            drop=True
        )

        return df, spot_price, len(greek_lookup)

    # --------------------------------------------------
    # FETCH ALL DATA
    # --------------------------------------------------

    def fetch_data(self, expiry):

        option_raw = self.fetch_option_chain(
            expiry
        )

        try:

            greek_raw = self.fetch_option_greeks(
                expiry
            )

        except Exception as e:

            print("Greek Fetch Error:", e)

            st.warning(
                f"Option Greeks डेटा मिळाला नाही: {e}"
            )

            greek_raw = {
                "data": []
            }

        return self.process_option_chain(
            option_raw,
            greek_raw,
            expiry
        )


# ======================================================
# STREAMLIT DASHBOARD
# ======================================================

st.title(
    "NSE Option Chain & Reversal Dashboard"
)

# ------------------------------------------------------
# SIDEBAR
# ------------------------------------------------------

st.sidebar.header("Dashboard Settings")

symbol = st.sidebar.selectbox(
    "Select Symbol",
    [
        "NIFTY",
        "BANKNIFTY",
        "FINNIFTY"
    ]
)

refresh_rate = st.sidebar.slider(
    "Refresh Interval (Seconds)",
    min_value=5,
    max_value=60,
    value=10
)

auto_refresh = st.sidebar.checkbox(
    "Auto Refresh",
    value=False
)

manual_refresh = st.sidebar.button(
    "Refresh Data"
)

# ------------------------------------------------------
# FETCHER
# ------------------------------------------------------

fetcher = NSEOptionChainFetcher(
    symbol
)

try:

    with st.spinner(
        "Fetching NSE Option Chain Data..."
    ):

        expiry_dates = fetcher.get_expiry_dates()

        if not expiry_dates:

            st.error(
                "NSE कडून Expiry Dates मिळाल्या नाहीत."
            )

            st.stop()

        expiry = st.selectbox(
            "Select Expiry Date",
            expiry_dates
        )

        df, spot_price, greek_count = (
            fetcher.fetch_data(expiry)
        )

    # --------------------------------------------------
    # SPOT PRICE
    # --------------------------------------------------

    st.subheader("Market Information")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Underlying Spot Price",
        f"{spot_price:,.2f}"
    )

    col2.metric(
        "Selected Expiry",
        expiry
    )

    col3.metric(
        "Greek Records",
        greek_count
    )

    if greek_count == 0:

        st.warning(
            "Option Greeks डेटा उपलब्ध नाही. "
            "Reversal Levels साठी Delta आवश्यक आहे."
        )

    # --------------------------------------------------
    # DISPLAY DATA
    # --------------------------------------------------

    st.subheader(
        "Option Chain & Reversal Levels"
    )

    display_columns = [

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

    ]

    display_df = df[
        display_columns
    ].copy()

    # --------------------------------------------------
    # RENAME COLUMNS
    # --------------------------------------------------

    display_df = display_df.rename(
        columns={

            "Call_Gamma": "Gamma",
            "Call_Delta": "Delta",
            "Call_OI": "OI",
            "Call_Change_OI": "Change OI",
            "Call_LTP": "LTP",
            "Call_IV": "IV",
            "Call_Rev": "Call Rev",

            "Strike": "SP",

            "Put_Rev": "Put Rev",
            "Put_IV": "IV",
            "Put_LTP": "LTP",
            "Put_Change_OI": "Change OI",
            "Put_OI": "OI",
            "Put_Delta": "Delta",
            "Put_Gamma": "Gamma"

        }
    )

    # --------------------------------------------------
    # ROUNDING
    # --------------------------------------------------

    display_df["SP"] = (
        display_df["SP"].round(0).astype("Int64")
    )

    display_df["Call Rev"] = (
        display_df["Call Rev"].round(0).astype("Int64")
    )

    display_df["Put Rev"] = (
        display_df["Put Rev"].round(0).astype("Int64")
    )

    # --------------------------------------------------
    # ATM / ITM / OTM STYLING
    # --------------------------------------------------

    def style_option_chain(data):

        styles = pd.DataFrame(
            "",
            index=data.index,
            columns=data.columns
        )

        for idx in data.index:

            strike = pd.to_numeric(
                data.loc[idx, "SP"],
                errors="coerce"
            )

            if pd.isna(strike):
                continue

            # ATM ROW
            if np.isclose(
                float(strike),
                spot_price,
                atol=0.01
            ):

                styles.loc[idx, :] = (
                    "background-color: #fff2cc; "
                    "font-weight: bold;"
                )

            else:

                # CALL ITM / OTM
                if strike < spot_price:

                    styles.loc[idx, [
                        "Gamma",
                        "Delta",
                        "OI",
                        "Change OI",
                        "LTP",
                        "IV",
                        "Call Rev"
                    ]] = (
                        "background-color: #e8f5e9;"
                    )

                else:

                    styles.loc[idx, [
                        "Gamma",
                        "Delta",
                        "OI",
                        "Change OI",
                        "LTP",
                        "IV",
                        "Call Rev"
                    ]] = (
                        "background-color: #e3f2fd;"
                    )

                # PUT ITM / OTM
                if strike > spot_price:

                    styles.loc[idx, [
                        "Put Rev",
                        "IV",
                        "LTP",
                        "Change OI",
                        "OI",
                        "Delta",
                        "Gamma"
                    ]] = (
                        "background-color: #e8f5e9;"
                    )

                else:

                    styles.loc[idx, [
                        "Put Rev",
                        "IV",
                        "LTP",
                        "Change OI",
                        "OI",
                        "Delta",
                        "Gamma"
                    ]] = (
                        "background-color: #e3f2fd;"
                    )

        return styles

    # --------------------------------------------------
    # NUMBER FORMATTING
    # --------------------------------------------------

    styled_df = (
        display_df.style
        .apply(
            style_option_chain,
            axis=None
        )
        .format(
            precision=2,
            na_rep="-"
        )
    )

    st.dataframe(
        styled_df,
        width="stretch",
        height=650,
        hide_index=True
    )

except Exception as e:

    st.error(
        f"Dashboard Error: {e}"
    )

    st.exception(e)


# ------------------------------------------------------
# AUTO REFRESH
# ------------------------------------------------------

if auto_refresh:

    time.sleep(refresh_rate)

    st.rerun()
