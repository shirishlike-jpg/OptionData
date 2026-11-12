import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
import math
import re

from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo
from html.parser import HTMLParser
from urllib.parse import urljoin


st.set_page_config(
    page_title="NSE Option Chain & Reversal Dashboard",
    layout="wide"
)


# ======================================================
# RBI 91-DAY T-BILL YIELD FETCHER
# ======================================================

class RBIYieldFetcher:

    BASE_URL = "https://www.rbi.org.in"
    LIST_URL = "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9"
    }

    class AnchorParser(HTMLParser):

        def __init__(self):
            super().__init__()
            self.links = []
            self.current_href = None
            self.current_text = []

        def handle_starttag(self, tag, attrs):
            if tag.lower() == "a":
                attrs = dict(attrs)
                self.current_href = attrs.get("href")
                self.current_text = []

        def handle_data(self, data):
            if self.current_href:
                self.current_text.append(data)

        def handle_endtag(self, tag):
            if tag.lower() == "a" and self.current_href:
                text_value = " ".join(self.current_text).strip()
                self.links.append((text_value, self.current_href))
                self.current_href = None
                self.current_text = []

    @staticmethod
    def get_page_text(html):

        parser = RBIYieldFetcher.AnchorParser()
        parser.feed(html)

        class TextParser(HTMLParser):

            def __init__(self):
                super().__init__()
                self.parts = []

            def handle_data(self, data):
                self.parts.append(data)

        text_parser = TextParser()
        text_parser.feed(html)

        return " ".join(text_parser.parts), parser.links

    @staticmethod
    def parse_yield(html):

        text, _ = RBIYieldFetcher.get_page_text(html)
        text = re.sub(r"\s+", " ", text)

        date_match = re.search(
            r"Date\s*:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
            text,
            re.IGNORECASE
        )
