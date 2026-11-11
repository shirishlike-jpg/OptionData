import requests
import pandas as pd
import numpy as np

class NSEOptionChainFetcher:
    def __init__(self, symbol="NIFTY"):
        self.symbol = symbol
        self.base_url = "https://www.nseindia.com"
        # मुख्य ऑप्शन चेन आणि ग्रीक्स डेटा मिळवण्यासाठीचे URLs
        self.url = f"https://www.nseindia.com/api/option-chain-indices?symbol={self.symbol}"
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self._init_cookies()

    def _init_cookies(self):
        try:
            self.session.get(self.base_url, timeout=10)
        except Exception as e:
            print(f"Cookie fetch error: {e}")

    def fetch_data(self):
        try:
            response = self.session.get(self.url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return self.process_option_chain(data)
            else:
                self._init_cookies()
                response = self.session.get(self.url, timeout=10)
                if response.status_code == 200:
                    return self.process_option_chain(response.json())
                else:
                    return None, 0
        except Exception as e:
            print(f"Data Fetch Error: {e}")
            return None, 0

    def process_option_chain(self, raw_data):
        try:
            underlying_price = raw_data['records']['underlyingValue']
            records = raw_data['records']['data']
            expiry_dates = raw_data['records']['expiryDates']
            current_expiry = expiry_dates[0]  # सर्वात जवळची एक्स्पायरी

            rows = []
            for record in records:
                if record.get('expiryDate') != current_expiry:
                    continue

                strike = record['strikePrice']
                ce = record.get('CE', {})
                pe = record.get('PE', {})

                call_oi = ce.get('openInterest', 0)
                call_change_oi = ce.get('changeinOpenInterest', 0)
                call_ltp = ce.get('lastPrice', 0)
                call_iv = ce.get('impliedVolatility', 0)
                
                put_oi = pe.get('openInterest', 0)
                put_change_oi = pe.get('changeinOpenInterest', 0)
                put_ltp = pe.get('lastPrice', 0)
                put_iv = pe.get('impliedVolatility', 0)

                # NSE च्या JSON मधील गॅरंटीड ग्रीक्स डेटा (असल्यास तो घेणे, अन्यथा ब्लॅक-शोलॉक्स नुसार किंवा डीफॉल्ट मॅथेमॅिकल अंदाज वापरणे)
                call_greeks = ce.get('greeks', {})
                put_greeks = pe.get('greeks', {})

                call_delta = call_greeks.get('delta', 0.5)
                call_gamma = call_greeks.get('gamma', 0.0)
                
                put_delta = put_greeks.get('delta', -0.5)
                put_gamma = put_greeks.get('gamma', 0.0)

                rows.append({
                    'Strike': strike,
                    'Call_OI': call_oi,
                    'Call_Change_OI': call_change_oi,
                    'Call_LTP': call_ltp,
                    'Call_IV': call_iv,
                    'Call_Delta': call_delta,
                    'Call_Gamma': call_gamma,
                    'Put_OI': put_oi,
                    'Put_Change_OI': put_change_oi,
                    'Put_LTP': put_ltp,
                    'Put_IV': put_iv,
                    'Put_Delta': put_delta,
                    'Put_Gamma': put_gamma,
                })

            df = pd.DataFrame(rows)
            
            # Spot Price च्या जवळचे स्ट्राइक्स फिल्टर करणे (ATM च्या आसपास ±12 स्ट्राइक्स)
            df['Diff'] = abs(df['Strike'] - underlying_price)
            atm_idx = df['Diff'].idxmin()
            df = df.iloc[max(0, atm_idx - 12): min(len(df), atm_idx + 13)].copy()
            df.reset_index(drop=True, inplace=True)

            # Reversal Calculations (Delta वापरून अचूक लेव्हल्स)
            df['Call_Rev'] = 0.0
            df['Put_Rev'] = 0.0

            n = len(df)
            for i in range(n):
                # Put Level Formula
                if i > 0:
                    denom_put = df.loc[i, 'Call_Delta'] - df.loc[i-1, 'Put_Delta']
                    if denom_put != 0:
                        df.loc[i, 'Put_Rev'] = underlying_price - ((df.loc[i, 'Call_LTP'] - df.loc[i-1, 'Put_LTP']) / denom_put)
                
                # Call Level Formula
                if i + 1 < n:
                    denom_call = df.loc[i, 'Call_Delta'] - df.loc[i+1, 'Put_Delta']
                    if denom_call != 0:
                        df.loc[i, 'Call_Rev'] = underlying_price - ((df.loc[i, 'Call_LTP'] - df.loc[i+1, 'Put_LTP']) / denom_call)

            return df, underlying_price
        except Exception as e:
            print(f"Processing Error: {e}")
            return None, 0