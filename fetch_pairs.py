import os
import pandas as pd
import yfinance as yf
import time

# =========================================================================
# 🎛️ CONFIGURATION (Aapki Exact Sheet, Tab Aur Range)
# =========================================================================
SPREADSHEET_ID = "13JWuBGKiLVe8dgvIcXLM3JZbo2rO83rN6aujpP0IKCY"
SOURCE_SHEET_NAME = "ALL_STOCKS_NAME"
STOCK_RANGE = "B2:B201"  
INTERVAL = "1h"
RANGE = "1y" # Agad 1y rakhna hai, toh batches me fetch karna hi bulletproof hai

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
                sym = sym.split(":")[1].strip()
            if not sym.endswith(".NS"):
                sym = sym + ".NS"
            clean_symbols.append(sym)
        return clean_symbols
    except Exception as e:
        print(f"❌ Google Sheet ki range {STOCK_RANGE} se data read karne me dikkat aayi: {e}")
        return []

def main():
    symbols = get_stocks_from_exact_range()
    if not symbols:
        print("❌ Di gayi range me koi valid stock symbol nahi mila. Process stopped.")
        return

    print(f"📊 Sheet ke '{STOCK_RANGE}' range se total {len(symbols)} stocks load ho gaye hain.")
    print(f"🚀 Fetching hourly data from Yahoo Finance in Safe Batches...")

    # ⚡ CHUNK-BASED DOWNLOAD SYSTEM (Bina data loss ke 1y data fetch karne ka tarika)
    chunk_size = 20  # Ek baar me sirf 20 stocks fetch honge taaki Yahoo block na kare
    all_chunks_data = []

    for i in range(0, len(symbols), chunk_size):
        batch = symbols[i:i + chunk_size]
        print(f"📦 Fetching Batch {(i//chunk_size)+1}: {batch[0]} se {batch[-1]}...")
        
        # Safe Multi-threaded download for the batch
        batch_data = yf.download(batch, period=RANGE, interval=INTERVAL, group_by='ticker', threads=True, progress=False)
        all_chunks_data.append(batch_data)
        
        # ⏱️ 1 second ka gap taaki Yahoo ka server load handle kar sake
        time.sleep(1)

    print("✅ All batches received. Merging into a Unified Matrix...")

    # Saare chunks ko ek bade dataframe me axis=1 (side-by-side) jodna
    combined_data = pd.concat(all_chunks_data, axis=1)

    # Absolute Matrix Alignment
    close_prices = pd.DataFrame(index=combined_data.index)
    for ticker in symbols:
        # Check if ticker exists in multi-index columns
        if ticker in combined_data.columns.levels[0]:
            clean_name = ticker.replace(".NS", "")
            close_prices[clean_name] = combined_data[ticker]['Close']

    # Date aur Time format ko IST (Indian Standard Time) me convert karna
    if not close_prices.empty:
        # Pata lagayein agar index already timezone aware hai ya nahi
        if close_prices.index.tz is None:
            close_prices.index = close_prices.index.tz_localize('UTC')
            
        close_prices.index = close_prices.index.tz_convert('Asia/Kolkata').strftime('%Y-%m-%d %H:%M')
        close_prices.reset_index(inplace=True)
        close_prices.rename(columns={'index': f'Date & Time ({INTERVAL})'}, inplace=True)
        close_prices.fillna("", inplace=True)

        # 📝 SAVE AS CSV
        csv_filename = "pair_data.csv"
        close_prices.to_csv(csv_filename, index=False)
        print(f"🎯 BOOM! 100% Complete Range-Aligned Matrix CSV ban chuka hai: '{csv_filename}'")
    else:
        print("❌ Yahoo Finance se data fetch nahi ho paya, CSV empty hai.")

if __name__ == "__main__":
    main()
