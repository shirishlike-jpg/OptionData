
import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
import math

from datetime import datetime, date, time as dt_time
from zoneinfo import ZoneInfo


st.set_page_config(
    page_title="NSE Option Chain & Reversal Dashboard",
    layout="wide"
)


# ======================================================
# BLACK-SCHOLES CALCULATION
# ======================================================

class BlackScholes:

    @staticmethod
    def normal_cdf(x):

        return 0.5 * (
            1 + math.erf(x / math.sqrt(2))
        )

    @staticmethod
    def normal_pdf(x):

        return (
            math.exp(-0.5 * x * x)
            / math.sqrt(2 * math.pi)
        )

    @staticmethod
    def calculate(
        spot,
        strike,
        iv,
        time_years,
        risk_free_rate,
        option_type
    ):

        try:

            if (
                pd.isna(spot)
                or pd.isna(strike)
                or pd.isna(iv)
                or pd.isna(time_years)
            ):
                return np.nan, np.nan

            if (
                spot <= 0
                or strike <= 0
                or iv <= 0
                or time_years <= 0
            ):
                return np.nan, np.nan

            sigma = iv

            r = risk_free_rate

            T = time_years

            d1 = (
                math.log(spot / strike)
                + (r + 0.5 * sigma ** 2) * T
            ) / (
                sigma * math.sqrt(T)
            )

            pdf_d1 = BlackScholes.normal_pdf(d1)

            if option_type == "CE":

                delta = BlackScholes.normal_cdf(d1)

            else:

                delta = (
                    BlackScholes.normal_cdf(d1) - 1
                )

            gamma = (
                pdf_d1
                / (
                    spot
                    * sigma
                    * math.sqrt(T)
                )
            )

            return delta, gamma

        except (
            ValueError,
            ZeroDivisionError,
            OverflowError
        ):

            return np.nan, np.nan


# ======================================================
# NSE OPTION CHAIN FETCHER
# ======================================================

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

            "Accept": (
                "application/json, text/javascript, */*; q=0.01"
            ),

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
    # SESSION AND COOKIE
    # --------------------------------------------------

    def _init_cookies(self):

        try:

            self.session.get(
                self.base_url,
                timeout=15
            )

            time.sleep(1)

            self.session.get(
                f"{self.base_url}/option-chain",
                timeout=15
            )

        except requests.RequestException:
            pass

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

        try:

            return response.json()

        except ValueError:

            raise ValueError(
                "NSE कडून JSON डेटा मिळाला नाही. "
                f"HTTP Status: {response.status_code}. "
                f"Response: {response.text[:500]}"
            )

    # --------------------------------------------------
    # COMMON FUNCTIONS
    # --------------------------------------------------

    @staticmethod
    def safe_number(value):

        if value is None or value == "":
            return np.nan

        try:

            if isinstance(value, str):

                value = value.replace(",", "").strip()

            result = float(value)

            return result if np.isfinite(result) else np.nan

        except (TypeError, ValueError):

            return np.nan

    @staticmethod
    def normalize_expiry(value):

        if not value:
            return None

        for fmt in (
            "%d-%m-%Y",
            "%d-%b-%Y",
            "%Y-%m-%d"
        ):

            parsed = pd.to_datetime(
                value,
                format=fmt,
                errors="coerce"
            )

            if not pd.isna(parsed):

                return parsed.strftime("%Y-%m-%d")

        parsed = pd.to_datetime(
            value,
            errors="coerce",
            dayfirst=True
        )

        if pd.isna(parsed):
            return None

        return parsed.strftime("%Y-%m-%d")

    # --------------------------------------------------
    # IV NORMALIZATION
    # --------------------------------------------------

    @staticmethod
    def normalize_iv(value):

        iv = NSEOptionChainFetcher.safe_number(value)

        if pd.isna(iv) or iv <= 0:
            return np.nan

        # NSE Option Chain IV is expressed in percentage.
        # Example: 15.50 means 15.50%.
        return iv / 100.0

    # --------------------------------------------------
    # TIME TO EXPIRY
    # --------------------------------------------------

    @staticmethod
    def calculate_time_to_expiry(expiry):

        try:

            expiry_normalized = (
                NSEOptionChainFetcher.normalize_expiry(expiry)
            )

            if not expiry_normalized:
                return np.nan

            expiry_date = datetime.strptime(
                expiry_normalized,
                "%Y-%m-%d"
            ).date()

            ist = ZoneInfo("Asia/Kolkata")

            current_time = datetime.now(ist)

            expiry_datetime = datetime.combine(
                expiry_date,
                dt_time(15, 30),
                tzinfo=ist
            )

            remaining_seconds = (
                expiry_datetime - current_time
            ).total_seconds()

            if remaining_seconds <= 0:
                return np.nan

            return (
                remaining_seconds
                / (365.0 * 24 * 60 * 60)
            )

        except Exception:

            return np.nan

    # --------------------------------------------------
    # EXPIRY DATES
    # --------------------------------------------------

    def get_expiry_dates(self):

        url = (
            f"{self.base_url}/api/option-chain-contract-info"
            f"?symbol={self.symbol}"
        )

        raw_data = self._get_json(url)

        if not isinstance(raw_data, dict):

            raise ValueError(
                "Expiry API कडून चुकीचा Response मिळाला."
            )

        expiry_dates = raw_data.get(
            "expiryDates",
            []
        )

        if not expiry_dates:

            records = raw_data.get("records", {})

            if isinstance(records, dict):

                expiry_dates = records.get(
                    "expiryDates",
                    []
                )

        if not expiry_dates:

            filtered = raw_data.get("filtered", {})

            if isinstance(filtered, dict):

                expiry_dates = filtered.get(
                    "expiryDates",
                    []
                )

        if not expiry_dates:

            raise ValueError(
                "NSE API मधून Expiry Dates मिळाल्या नाहीत. "
                f"Response: {str(raw_data)[:1000]}"
            )

        return list(dict.fromkeys(
            str(x) for x in expiry_dates if x
        ))

    # --------------------------------------------------
    # OPTION CHAIN API
    # --------------------------------------------------

    def fetch_option_chain(self, expiry):

        url = (
            f"{self.base_url}/api/option-chain-v3"
            f"?type=Indices&symbol={self.symbol}"
            f"&expiry={expiry}"
        )

        return self._get_json(url)

    # --------------------------------------------------
    # PROCESS OPTION CHAIN AND CALCULATE GREEKS
    # --------------------------------------------------

    def process_option_chain(
        self,
        option_raw,
        expiry,
        risk_free_rate
    ):

        records_obj = option_raw.get(
            "records",
            {}
        )

        if not isinstance(records_obj, dict):
            records_obj = {}

        option_records = records_obj.get(
            "data",
            []
        )

        filtered = option_raw.get(
            "filtered",
            {}
        )

        if (
            not option_records
            and isinstance(filtered, dict)
        ):

            option_records = filtered.get(
                "data",
                []
            )

        # NSE SPOT PRICE

        underlying_price = self.safe_number(
            records_obj.get("underlyingValue")
        )

        if (
            pd.isna(underlying_price)
            and isinstance(filtered, dict)
        ):

            underlying_price = self.safe_number(
                filtered.get("underlyingValue")
            )

        if not option_records:

            raise ValueError(
                "Option Chain मध्ये डेटा उपलब्ध नाही."
            )

        if (
            pd.isna(underlying_price)
            or underlying_price <= 0
        ):

            raise ValueError(
                "NSE कडून योग्य Underlying Spot Price मिळाला नाही."
            )

        selected_expiry = self.normalize_expiry(expiry)

        time_years = self.calculate_time_to_expiry(
            expiry
        )

        rows = []

        ce_valid_count = 0
        pe_valid_count = 0

        ce_iv_count = 0
        pe_iv_count = 0

        for record in option_records:

            if not isinstance(record, dict):
                continue

            record_expiry = (
                record.get("expiryDates")
                or record.get("expiryDate")
            )

            if (
                record_expiry
                and self.normalize_expiry(record_expiry)
                != selected_expiry
            ):

                continue

            strike = self.safe_number(
                record.get("strikePrice")
            )

            if pd.isna(strike):
                continue

            ce = record.get("CE") or {}

            pe = record.get("PE") or {}

            # ------------------------------------------
            # CE DATA FROM NSE
            # ------------------------------------------

            call_iv_raw = self.safe_number(
                ce.get("impliedVolatility")
            )

            call_iv = self.normalize_iv(
                call_iv_raw
            )

            call_ltp = self.safe_number(
                ce.get("lastPrice")
            )

            call_oi = self.safe_number(
                ce.get("openInterest")
            )

            call_change_oi = self.safe_number(
                ce.get("changeinOpenInterest")
            )

            # ------------------------------------------
            # PE DATA FROM NSE
            # ------------------------------------------

            put_iv_raw = self.safe_number(
                pe.get("impliedVolatility")
            )

            put_iv = self.normalize_iv(
                put_iv_raw
            )

            put_ltp = self.safe_number(
                pe.get("lastPrice")
            )

            put_oi = self.safe_number(
                pe.get("openInterest")
            )

            put_change_oi = self.safe_number(
                pe.get("changeinOpenInterest")
            )

            # ------------------------------------------
            # CE DELTA AND GAMMA
            # ------------------------------------------

            call_delta, call_gamma = BlackScholes.calculate(

                spot=underlying_price,

                strike=strike,

                iv=call_iv,

                time_years=time_years,

                risk_free_rate=risk_free_rate,

                option_type="CE"
            )

            # ------------------------------------------
            # PE DELTA AND GAMMA
            # ------------------------------------------

            put_delta, put_gamma = BlackScholes.calculate(

                spot=underlying_price,

                strike=strike,

                iv=put_iv,

                time_years=time_years,

                risk_free_rate=risk_free_rate,

                option_type="PE"
            )

            # ------------------------------------------
            # COUNT AVAILABLE VALUES
            # ------------------------------------------

            if pd.notna(call_iv):
                ce_iv_count += 1

            if pd.notna(put_iv):
                pe_iv_count += 1

            if pd.notna(call_delta):
                ce_valid_count += 1

            if pd.notna(put_delta):
                pe_valid_count += 1

            # ------------------------------------------
            # BUILD ROW
            # ------------------------------------------

            rows.append({

                "Strike": strike,

                # CALL

                "Call_Gamma": call_gamma,

                "Call_Delta": call_delta,

                "Call_OI": call_oi,

                "Call_Change_OI": call_change_oi,

                "Call_LTP": call_ltp,

                "Call_IV": call_iv_raw,

                # PUT

                "Put_IV": put_iv_raw,

                "Put_LTP": put_ltp,

                "Put_Change_OI": put_change_oi,

                "Put_OI": put_oi,

                "Put_Delta": put_delta,

                "Put_Gamma": put_gamma

            })

        if not rows:

            raise ValueError(
                "निवडलेल्या Expiry साठी Option Chain डेटा मिळाला नाही."
            )

        df = pd.DataFrame(rows)

        df = df.sort_values(
            "Strike"
        ).reset_index(drop=True)

        # ----------------------------------------------
        # ATM SELECTION
        # ----------------------------------------------

        atm_idx = (
            df["Strike"] - underlying_price
        ).abs().idxmin()

        start_idx = max(
            0,
            atm_idx - 10
        )

        end_idx = min(
            len(df),
            atm_idx + 11
        )

        df = df.iloc[
            start_idx:end_idx
        ].copy().reset_index(drop=True)

        # ----------------------------------------------
        # REVERSAL CALCULATION
        # ----------------------------------------------

        df["Call_Rev"] = np.nan

        df["Put_Rev"] = np.nan

        for i in range(len(df)):

            # PUT REVERSAL

            if i > 0:

                call_delta = df.loc[
                    i,
                    "Call_Delta"
                ]

                put_delta = df.loc[
                    i - 1,
                    "Put_Delta"
                ]

                call_ltp = df.loc[
                    i,
                    "Call_LTP"
                ]

                put_ltp = df.loc[
                    i - 1,
                    "Put_LTP"
                ]

                if all(
                    pd.notna(x)
                    for x in [
                        call_delta,
                        put_delta,
                        call_ltp,
                        put_ltp,
                        underlying_price
                    ]
                ):

                    denominator = (
                        call_delta - put_delta
                    )

                    if denominator != 0:

                        df.loc[i, "Put_Rev"] = (

                            underlying_price

                            - (
                                (call_ltp - put_ltp)
                                / denominator
                            )
                        )

            # CALL REVERSAL

            if i + 1 < len(df):

                call_delta = df.loc[
                    i,
                    "Call_Delta"
                ]

                put_delta = df.loc[
                    i + 1,
                    "Put_Delta"
                ]

                call_ltp = df.loc[
                    i,
                    "Call_LTP"
                ]

                put_ltp = df.loc[
                    i + 1,
                    "Put_LTP"
                ]

                if all(
                    pd.notna(x)
                    for x in [
                        call_delta,
                        put_delta,
                        call_ltp,
                        put_ltp,
                        underlying_price
                    ]
                ):

                    denominator = (
                        call_delta - put_delta
                    )

                    if denominator != 0:

                        df.loc[i, "Call_Rev"] = (

                            underlying_price

                            - (
                                (call_ltp - put_ltp)
                                / denominator
                            )
                        )

        return (
            df,
            underlying_price,
            ce_valid_count,
            pe_valid_count,
            ce_iv_count,
            pe_iv_count,
            time_years,
            option_records
        )

    # --------------------------------------------------
    # FETCH ALL DATA
    # --------------------------------------------------

    def fetch_data(
        self,
        expiry,
        risk_free_rate
    ):

        option_raw = self.fetch_option_chain(
            expiry
        )

        return self.process_option_chain(
            option_raw,
            expiry,
            risk_free_rate
        )


# ======================================================
# DATAFRAME STYLING
# ======================================================

def style_option_chain(df, spot_price):

    strike_col = (
        "Strike Price"
        if "Strike Price" in df.columns
        else "Strike"
    )

    if df.empty or pd.isna(spot_price):

        return df.style.format(
            na_rep="-"
        )

    atm_idx = (
        df[strike_col] - spot_price
    ).abs().idxmin()

    atm_value = df.loc[
        atm_idx,
        strike_col
    ]

    def apply_styles(row):

        styles = [""] * len(row)

        strike = row[strike_col]

        if strike == atm_value:

            return [
                "background-color: #fff2cc; font-weight: bold;"
            ] * len(row)

        for i, col in enumerate(row.index):

            if col.startswith("Call "):

                if strike < spot_price:

                    styles[i] = (
                        "background-color: #e2f0d9;"
                    )

                elif strike > spot_price:

                    styles[i] = (
                        "background-color: #ddebf7;"
                    )

            elif col.startswith("Put "):

                if strike > spot_price:

                    styles[i] = (
                        "background-color: #e2f0d9;"
                    )

                elif strike < spot_price:

                    styles[i] = (
                        "background-color: #ddebf7;"
                    )

        return styles

    return df.style.apply(
        apply_styles,
        axis=1
    ).format(
        {
            col: "{:.2f}"
            for col in df.columns
            if col != strike_col
        },
        na_rep="-"
    ).format(
        {strike_col: "{:.0f}"}
    )


# ======================================================
# STREAMLIT DASHBOARD
# ======================================================

st.title(
    "NSE Option Chain & Reversal Dashboard"
)

st.sidebar.header(
    "Dashboard Controls"
)

symbol = st.sidebar.selectbox(
    "Select Index",
    [
        "NIFTY",
        "BANKNIFTY",
        "FINNIFTY"
    ]
)

refresh_rate = st.sidebar.slider(
    "Auto Refresh Interval (Seconds)",
    5,
    60,
    10
)

auto_refresh = st.sidebar.checkbox(
    "Enable Auto Refresh",
    value=False
)

show_debug = st.sidebar.checkbox(
    "Show Calculation Debug Information",
    value=False
)

risk_free_rate_percent = st.sidebar.number_input(
    "Risk-Free Interest Rate (%)",
    min_value=0.0,
    max_value=20.0,
    value=6.5,
    step=0.25
)

risk_free_rate = (
    risk_free_rate_percent / 100
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
        "NSE Option Chain डेटा घेत आहे आणि Delta-Gamma Calculate करत आहे..."
    ):

        (
            df,
            underlying_price,
            ce_valid_count,
            pe_valid_count,
            ce_iv_count,
            pe_iv_count,
            time_years,
            option_records
        ) = fetcher.fetch_data(
            selected_expiry,
            risk_free_rate
        )

    # --------------------------------------------------
    # MARKET INFORMATION
    # --------------------------------------------------

    st.success(
        f"Live {symbol} Spot Price: ₹{underlying_price:,.2f}"
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Index",
        symbol
    )

    col2.metric(
        "Underlying Spot Price",
        f"₹{underlying_price:,.2f}"
    )

    col3.metric(
        "Expiry",
        selected_expiry
    )

    col4.metric(
        "Calculated Strikes",
        ce_valid_count + pe_valid_count
    )

    # --------------------------------------------------
    # CALCULATION COUNTS
    # --------------------------------------------------

    g1, g2, g3, g4 = st.columns(4)

    g1.metric(
        "CE Delta Available",
        ce_valid_count
    )

    g2.metric(
        "PE Delta Available",
        pe_valid_count
    )

    g3.metric(
        "CE IV Available",
        ce_iv_count
    )

    g4.metric(
        "PE IV Available",
        pe_iv_count
    )

    if ce_valid_count == 0 and pe_valid_count == 0:

        st.warning(
            "Delta आणि Gamma Calculate करता आले नाहीत. "
            "NSE Option Chain मधील IV तपासा."
        )

    # --------------------------------------------------
    # DISPLAY COLUMNS
    # --------------------------------------------------

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

    display_names = {

        "Call_Gamma": "Call Gamma",

        "Call_Delta": "Call Delta",

        "Call_OI": "Call OI",

        "Call_Change_OI": "Call Change OI",

        "Call_LTP": "Call LTP",

        "Call_IV": "Call IV",

        "Call_Rev": "Call Rev",

        "Strike": "Strike Price",

        "Put_Rev": "Put Rev",

        "Put_IV": "Put IV",

        "Put_LTP": "Put LTP",

        "Put_Change_OI": "Put Change OI",

        "Put_OI": "Put OI",

        "Put_Delta": "Put Delta",

        "Put_Gamma": "Put Gamma"

    }

    display_df = df[
        display_columns
    ].rename(
        columns=display_names
    )

    styled_df = style_option_chain(
        display_df,
        underlying_price
    )

    st.dataframe(
        styled_df,
        use_container_width=True,
        hide_index=True
    )

    # --------------------------------------------------
    # CALCULATION DEBUG INFORMATION
    # --------------------------------------------------

    if show_debug:

        st.subheader(
            "Calculation Debug Information"
        )

        st.write(
            "Calculation Model:",
            "Black-Scholes"
        )

        st.write(
            "Underlying:",
            "NSE Spot Price"
        )

        st.write(
            "Risk-Free Interest Rate:",
            f"{risk_free_rate_percent:.2f}%"
        )

        st.write(
            "Time to Expiry (Years):",
            time_years
        )

        st.write(
            "Total Option Chain Records:",
            len(option_records)
        )

        st.write(
            "CE IV Available:",
            ce_iv_count
        )

        st.write(
            "PE IV Available:",
            pe_iv_count
        )

        st.write(
            "CE Delta Available:",
            ce_valid_count
        )

        st.write(
            "PE Delta Available:",
            pe_valid_count
        )

        st.write(
            "First 3 NSE Option Chain Records:",
            option_records[:3]
        )

        st.write(
            "Calculated Data Sample:",
            df.head(5)
        )

    st.caption(
        "ATM: Light Yellow and Bold | "
        "ITM: Light Green | OTM: Light Blue | "
        "Greeks: Black-Scholes Calculation"
    )

    st.caption(
        "Note: Calculated Delta and Gamma are model estimates. "
        "They may differ from NSE published Greeks."
    )

except Exception as e:

    st.error(
        "NSE डेटा मिळवताना अडचण आली. काही वेळाने पुन्हा प्रयत्न करा."
    )

    st.caption(
        f"Technical Details: {e}"
    )


# ======================================================
# AUTO REFRESH
# ======================================================

if auto_refresh:

    time.sleep(refresh_rate)

    st.rerun()
