
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

    # --------------------------------------------------
    # SESSION AND COOKIE
    # --------------------------------------------------

    def _init_cookies(self):
        try:
            self.session.get(self.base_url, timeout=15)
            time.sleep(1)

            self.session.get(
                f"{self.base_url}/option-chain",
                timeout=15
            )
            time.sleep(1)

            self.session.get(
                f"{self.base_url}/market-data/option-greek",
                timeout=15
            )

        except requests.RequestException:
            pass

    def _get_json(self, url):

        response = self.session.get(url, timeout=20)

        if response.status_code in (401, 403, 429):
            self._init_cookies()
            response = self.session.get(url, timeout=20)

        response.raise_for_status()

        return response.json()

    # --------------------------------------------------
    # COMMON FUNCTIONS
    # --------------------------------------------------

    @staticmethod
    def safe_number(value):

        if value is None or value == "":
            return np.nan

        try:
            result = float(value)

            if np.isfinite(result):
                return result

            return np.nan

        except (TypeError, ValueError):
            return np.nan

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
    def get_first_value(data, keys):

        if not isinstance(data, dict):
            return np.nan

        for key in keys:

            value = data.get(key)

            if value is not None and value != "":
                return value

        return np.nan

    # --------------------------------------------------
    # EXPIRY DATES
    # --------------------------------------------------

    def get_expiry_dates(self):

        url = (
            f"{self.base_url}/api/option-chain-v3"
            f"?type=Indices&symbol={self.symbol}"
        )

        raw_data = self._get_json(url)

        records = raw_data.get("records", {})
        expiry_dates = records.get("expiryDates", [])

        if not expiry_dates:
            filtered = raw_data.get("filtered", {})
            expiry_dates = filtered.get("expiryDates", [])

        if not expiry_dates:
            raise ValueError(
                "NSE API मधून Expiry Dates मिळाल्या नाहीत."
            )

        return expiry_dates

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
    # OPTION GREEKS API
    # --------------------------------------------------

    def fetch_option_greeks(self, expiry):

        url = (
            f"{self.base_url}/api/NextApi/apiClient/OptionGreekApi"
            f"?functionName=getOptionGreekTableData"
            f"&symbol={self.symbol}"
            f"&params=expiryDate={expiry}"
        )

        return self._get_json(url)

    # --------------------------------------------------
    # GREEK DATA NORMALIZATION
    # --------------------------------------------------

    def normalize_greek_side(self, side):

        if not isinstance(side, dict):
            return {}

        return {
            "delta": self.safe_number(
                self.get_first_value(
                    side,
                    ["ogdDelta", "delta", "Delta"]
                )
            ),

            "gamma": self.safe_number(
                self.get_first_value(
                    side,
                    ["ogdGamma", "gamma", "Gamma"]
                )
            ),

            "theta": self.safe_number(
                self.get_first_value(
                    side,
                    ["ogdTheta", "theta", "Theta"]
                )
            ),

            "vega": self.safe_number(
                self.get_first_value(
                    side,
                    ["ogdVega", "vega", "Vega"]
                )
            ),

            "iv": self.safe_number(
                self.get_first_value(
                    side,
                    [
                        "ogdIv",
                        "ogdIV",
                        "impliedVolatility",
                        "iv",
                        "IV"
                    ]
                )
            ),

            "ltp": self.safe_number(
                self.get_first_value(
                    side,
                    [
                        "ogdLtp",
                        "lastPrice",
                        "ltp",
                        "tradePrice"
                    ]
                )
            )
        }

    def build_greek_lookup(self, greek_raw, expiry):

        greek_lookup = {}

        if not isinstance(greek_raw, dict):
            return greek_lookup

        data = greek_raw.get("data", [])

        if isinstance(data, dict):

            for key in ["records", "result", "items"]:
                if isinstance(data.get(key), list):
                    data = data[key]
                    break

            else:
                data = list(data.values())

        if not isinstance(data, list):
            return greek_lookup

        selected_expiry = self.normalize_expiry(expiry)

        for item in data:

            if not isinstance(item, dict):
                continue

            strike = self.get_first_value(
                item,
                [
                    "strikePrice",
                    "ogdStrikePrice",
                    "strike",
                    "strike_price"
                ]
            )

            strike = self.safe_number(strike)

            if pd.isna(strike):
                continue

            item_expiry = self.get_first_value(
                item,
                [
                    "expiryDates",
                    "expiryDate",
                    "ogdExpiryDate"
                ]
            )

            if not pd.isna(item_expiry):

                normalized_item_expiry = self.normalize_expiry(
                    item_expiry
                )

                if (
                    normalized_item_expiry
                    and normalized_item_expiry != selected_expiry
                ):
                    continue

            ce = item.get("CE")
            pe = item.get("PE")

            # Nested CE / PE format
            if isinstance(ce, dict) or isinstance(pe, dict):

                greek_lookup[float(strike)] = {
                    "CE": self.normalize_greek_side(ce),
                    "PE": self.normalize_greek_side(pe)
                }

                continue

            # Flat CE / PE format
            option_type = str(
                self.get_first_value(
                    item,
                    ["optionType", "option_type", "type"]
                )
            ).upper()

            if option_type not in ["CE", "PE"]:
                continue

            if float(strike) not in greek_lookup:

                greek_lookup[float(strike)] = {
                    "CE": {},
                    "PE": {}
                }

            greek_lookup[float(strike)][option_type] = (
                self.normalize_greek_side(item)
            )

        return greek_lookup

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

        option_records = records_obj.get("data", [])

        if not option_records:

            option_records = (
                option_raw.get("filtered", {}).get("data", [])
            )

        underlying_price = self.safe_number(
            records_obj.get("underlyingValue")
        )

        if pd.isna(underlying_price):

            underlying_price = self.safe_number(
                option_raw.get("filtered", {}).get("underlyingValue")
            )

        if not option_records:
            raise ValueError(
                "Option Chain मध्ये डेटा उपलब्ध नाही."
            )

        selected_expiry_key = self.normalize_expiry(expiry)

        greek_lookup = self.build_greek_lookup(
            greek_raw,
            expiry
        )

        rows = []

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

            greek = greek_lookup.get(
                float(strike),
                {}
            )

            ce_greek = greek.get("CE", {})
            pe_greek = greek.get("PE", {})

            rows.append({

                "Strike": strike,

                # CALL DATA
                "Call_Gamma": ce_greek.get("gamma", np.nan),
                "Call_Delta": ce_greek.get("delta", np.nan),

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

                # PUT DATA
                "Put_IV": self.safe_number(
                    pe.get("impliedVolatility")
                ),

                "Put_LTP": self.safe_number(
                    pe.get("lastPrice")
                ),

                "Put_Change_OI": self.safe_number(
                    pe.get("changeinOpenInterest")
                ),

                "Put_OI": self.safe_number(
                    pe.get("openInterest")
                ),

                "Put_Delta": pe_greek.get("delta", np.nan),
                "Put_Gamma": pe_greek.get("gamma", np.nan),

                "Call_Theta": ce_greek.get("theta", np.nan),
                "Put_Theta": pe_greek.get("theta", np.nan),

                "Call_Vega": ce_greek.get("vega", np.nan),
                "Put_Vega": pe_greek.get("vega", np.nan)

            })

        if not rows:
            raise ValueError(
                "निवडलेल्या Expiry साठी Option Chain डेटा मिळाला नाही."
            )

        df = pd.DataFrame(rows)

        df = df.sort_values(
            "Strike"
        ).reset_index(drop=True)

        # --------------------------------------------------
        # ATM SELECTION
        # --------------------------------------------------

        if (
            pd.notna(underlying_price)
            and underlying_price > 0
        ):

            atm_idx = (
                df["Strike"] - underlying_price
            ).abs().idxmin()

            start_idx = max(0, atm_idx - 10)
            end_idx = min(len(df), atm_idx + 11)

            df = df.iloc[
                start_idx:end_idx
            ].copy().reset_index(drop=True)

        # --------------------------------------------------
        # REVERSAL CALCULATION
        # --------------------------------------------------

        df["Call_Rev"] = np.nan
        df["Put_Rev"] = np.nan

        for i in range(len(df)):

            # PUT REVERSAL
            if i > 0:

                call_delta = df.loc[i, "Call_Delta"]
                put_delta = df.loc[i - 1, "Put_Delta"]

                call_ltp = df.loc[i, "Call_LTP"]
                put_ltp = df.loc[i - 1, "Put_LTP"]

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

                    denominator = call_delta - put_delta

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

                call_delta = df.loc[i, "Call_Delta"]
                put_delta = df.loc[i + 1, "Put_Delta"]

                call_ltp = df.loc[i, "Call_LTP"]
                put_ltp = df.loc[i + 1, "Put_LTP"]

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

                    denominator = call_delta - put_delta

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
            len(greek_lookup),
            greek_raw
        )

    # --------------------------------------------------
    # FETCH ALL DATA
    # --------------------------------------------------

    def fetch_data(self, expiry):

        option_raw = self.fetch_option_chain(expiry)

        greek_error = None

        try:

            greek_raw = self.fetch_option_greeks(expiry)

        except Exception as e:

            greek_raw = {"data": []}
            greek_error = str(e)

        result = self.process_option_chain(
            option_raw,
            greek_raw,
            expiry
        )

        return (*result, greek_error)


# ======================================================
# DATAFRAME STYLING
# ======================================================

def style_option_chain(df, spot_price):

    atm_strike = (
        df["Strike"] - spot_price
    ).abs().idxmin()

    def apply_styles(row):

        styles = [""] * len(row)

        strike = row["Strike"]

        columns = list(row.index)

        # ATM ROW
        if strike == df.loc[atm_strike, "Strike"]:

            return [
                "background-color: #fff2cc; font-weight: bold;"
            ] * len(row)

        for i, col in enumerate(columns):

            # CALL ITM / OTM
            if col.startswith("Call_"):

                if strike < spot_price:
                    styles[i] = "background-color: #e2f0d9;"

                elif strike > spot_price:
                    styles[i] = "background-color: #ddebf7;"

            # PUT ITM / OTM
            elif col.startswith("Put_"):

                if strike > spot_price:
                    styles[i] = "background-color: #e2f0d9;"

                elif strike < spot_price:
                    styles[i] = "background-color: #ddebf7;"

        return styles

    return df.style.apply(
        apply_styles,
        axis=1
    ).format(
        {
            col: "{:.2f}"
            for col in df.columns
            if col != "Strike"
        },
        na_rep="-"
    ).format(
        {"Strike": "{:.0f}"}
    )


# ======================================================
# STREAMLIT DASHBOARD
# ======================================================

st.title("NSE Option Chain & Reversal Dashboard")

st.sidebar.header("Dashboard Controls")

symbol = st.sidebar.selectbox(
    "Select Index",
    ["NIFTY", "BANKNIFTY", "FINNIFTY"]
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
    "Show Greek API Debug Information",
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

        (
            df,
            underlying_price,
            greek_count,
            greek_raw,
            greek_error
        ) = fetcher.fetch_data(selected_expiry)

    st.success(
        f"Live {symbol} Price: ₹{underlying_price:,.2f}"
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Index", symbol)

    col2.metric(
        "Underlying Price",
        f"₹{underlying_price:,.2f}"
    )

    col3.metric(
        "Expiry",
        selected_expiry
    )

    col4.metric(
        "Greek Strikes",
        greek_count
    )

    if greek_count == 0:

        st.warning(
            "Option Chain डेटा मिळाला आहे; परंतु Greek API मधून "
            "उपयुक्त Strike डेटा वाचता आलेला नाही."
        )

    if greek_error:

        st.warning(
            f"Greek API Error: {greek_error}"
        )

    # DISPLAY COLUMNS
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

    display_df = df[display_columns].rename(
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

    # OPTIONAL GREEK DEBUG
    if show_debug:

        st.subheader("Greek API Debug Information")

        if isinstance(greek_raw, dict):

            st.write(
                "Greek API Top Keys:",
                list(greek_raw.keys())
            )

            greek_data = greek_raw.get("data", [])

            if isinstance(greek_data, list):

                st.write(
                    "Greek API Records:",
                    len(greek_data)
                )

                st.write(
                    "Greek API Sample:",
                    greek_data[:2]
                )

            else:

                st.write(
                    "Greek API Data:",
                    str(greek_data)[:3000]
                )

        else:

            st.write(str(greek_raw)[:3000])

    st.caption(
        "ATM row: Light Yellow and Bold | "
        "ITM: Light Green | OTM: Light Blue"
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
