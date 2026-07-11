import os
import pandas as pd
import yfinance as yf
import time

# =========================================================================
# 🎛️ CONFIGURATION
# =========================================================================
SPREADSHEET_ID = "13JWuBGKiLVe8dgvIcXLM3JZbo2rO83rN6aujpP0IKCY"
SOURCE_SHEET_NAME = "ALL_STOCKS_NAME"
STOCK_RANGE = "B2:B201"  
INTERVAL = "1h"
RANGE = "90y" 

def get_stocks_from_exact_range():
    try:
        url = (
            f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?"
            f"format=csv&sheet={SOURCE_SHEET_NAME}&range={STOCK_RANGE}"
        )
        df = pd.read_csv(url, header=None)
        raw_symbols = df[0].dropna().astype(str).tolist()

        clean_symbols = []
        for s in raw_symbols:
            sym = s.strip()
            if sym == "" or sym.lower() == "nan" or sym.lower() == "null":
                continue
            if ":" in sym:
                sym = sym.split(":")[-1].strip()
            if "/" in sym:
                sym = sym.split("/")[-1].strip()
                
            sym = sym.upper()
            if not sym.endswith(".NS"):
                sym = sym + ".NS"
                
            if sym not in clean_symbols:
                clean_symbols.append(sym)
        return clean_symbols
    except Exception as e:
        print(f"❌ Google Sheet read error: {e}")
        return []

def main():
    symbols = get_stocks_from_exact_range()
    if not symbols:
        print("❌ Di gayi range me koi valid stock symbol nahi mila.")
        return

    print(f"📊 Sheet se total {len(symbols)} stocks load ho gaye hain.")
    print(f"🚀 Fetching hourly data with Smart Retry Engine...")

    # Master structure: Pehle se data frame ka base ready rakhna
    close_prices = pd.DataFrame()
    missing_stocks = []

    # ⚡ SINGLE-STREAM RETRY LOOP: Har ek stock ko nikalne ka solid tarika
    for idx, ticker in enumerate(symbols, 1):
        clean_name = ticker.replace(".NS", "")
        success = False
        
        # Ek stock ke liye 3 baar koshish karega agar data drop hota hai
        for attempt in range(3):
            try:
                # Group_by hatakar direct single ticker pull
                stock_data = yf.download(ticker, period=RANGE, interval=INTERVAL, progress=False, threads=False)
                
                if not stock_data.empty and 'Close' in stock_data.columns:
                    # Series extraction data check
                    series_data = stock_data['Close']
                    if not series_data.dropna().empty:
                        # Pehle stock se master index set hoga
                        if close_prices.empty:
                            close_prices = pd.DataFrame(index=stock_data.index)
                        
                        close_prices[clean_name] = series_data
                        success = True
                        break # Data mil gaya, loop se bahar
            except Exception:
                pass
            
            # Agar fail hua toh 0.3 sec rukk kar fir koshish karega
            time.sleep(0.3)
            
        if success:
            print(f"✅ [{idx}/{len(symbols)}] Loaded: {clean_name}")
        else:
            print(f"⚠️ [{idx}/{len(symbols)}] FAILED AFTER 3 ATTEMPTS: {clean_name}")
            missing_stocks.append(clean_name)

    # 🚨 CRITICAL CHECK: Missing stocks ki poori reporting
    if missing_stocks:
        print("\n❌ DATA NOT FOUND FOR THESE STOCKS (Spelling/Symbol issue on Sheet):")
        print(", ".join(missing_stocks))
        print("-" * 60)

    if not close_prices.empty:
        if close_prices.index.tz is None:
            close_prices.index = close_prices.index.tz_localize('UTC')
            
        close_prices.index = close_prices.index.tz_convert('Asia/Kolkata').strftime('%Y-%m-%d %H:%M')
        close_prices.reset_index(inplace=True)
        close_prices.rename(columns={'index': f'Date & Time ({INTERVAL})'}, inplace=True)
        
        # Kisi stock me thoda gap ho toh blank chhodna na ki zero ya error
        close_prices.fillna("", inplace=True)

        # Final Save
        csv_filename = "pair_data.csv"
        close_prices.to_csv(csv_filename, index=False)
        print(f"\n🎯 BOOM! 100% Sateek Matrix ready ho gaya hai: '{csv_filename}'")
    else:
        print("❌ Engine matrix build completely failed.")

if __name__ == "__main__":
    main()
