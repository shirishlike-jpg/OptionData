        help="हा फक्त nearest reversal rows च्या OI Change वर आधारित प्राथमिक bias आहे."
    )

    st.caption(
        f"Signal detail: {signal_detail} "
        "OI Change एकट्याने writing किंवा trade direction सिद्ध होत नाही. "
        "Spot price action, volume, premium movement आणि breakout/retest ने confirmation घ्या."
    )

    st.caption(
        "Movement हा मागील app rerun snapshot शी तुलना करतो. "
        "पहिल्या run ला previous snapshot नसल्यामुळे Waiting दिसेल."
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
    # DEBUG INFORMATION
    # --------------------------------------------------

    if show_debug:

        st.subheader(
            "Calculation Debug Information"
        )

        st.write("Calculation Model:", "Black-Scholes")
        st.write("Underlying:", "NSE Spot Price")

        st.write(
            "Risk-Free Interest Rate Used:",
            f"{risk_free_rate_percent:.4f}%"
        )

        st.write(
            "Risk-Free Rate Decimal:",
            risk_free_rate
        )

        st.write(
            "RBI Rate Status:",
            st.session_state.get("rbi_rate_status", "unknown")
        )

        st.write(
            "Time to Expiry (Years):",
            time_years
        )

        st.write(
            "Total Option Chain Records:",
            len(option_records)
        )

        st.write("CE IV Available:", ce_iv_count)
        st.write("PE IV Available:", pe_iv_count)
        st.write("CE Delta Available:", ce_valid_count)
        st.write("PE Delta Available:", pe_valid_count)

        st.write(
            "First 3 NSE Option Chain Records:",
            option_records[:3]
        )

        st.write(
            "Calculated Data Sample:",
            df.head(5)
        )

        st.write(
            "Call Gamma Raw Values:",
            df["Call_Gamma"].head(5).tolist()
        )

        st.write(
            "Put Gamma Raw Values:",
            df["Put_Gamma"].head(5).tolist()
        )

    st.caption(
        "ATM: Light Yellow and Bold | "
        "ITM: Light Green | OTM: Light Blue | "
        "Greeks: Black-Scholes Calculation"
    )

    st.caption(
        "Call Rev and Put Rev are displayed as whole numbers. "
        "Their calculations retain full precision."
    )

    st.caption(
        "Gamma is displayed up to 8 decimal places."
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
