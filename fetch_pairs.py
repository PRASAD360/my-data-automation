import os
import pandas as pd
import yfinance as yf

# =========================================================================
# 🎛️ CONFIGURATION (Aapki Exact Sheet, Tab Aur Range)
# =========================================================================
SPREADSHEET_ID = "13JWuBGKiLVe8dgvIcXLM3JZbo2rO83rN6aujpP0IKCY"
SOURCE_SHEET_NAME = "ALL_STOCKS_NAME"
STOCK_RANGE = "B2:B201"  # 🎯 Sirf isi range se stocks uthaye jayenge
INTERVAL = "1h"
RANGE = "90"

def get_stocks_from_exact_range():
    """
    Public sheet ke exact range (B2:B201) ka direct CSV grid export 
    format use karke symbols load karne ka sabse sateek tareeka.
    """
    try:
        # Google Sheet ka direct range-specific export URL
        url = (
            f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?"
            f"format=csv&sheet={SOURCE_SHEET_NAME}&range={STOCK_RANGE}"
        )
        
        # Header=None rakh rahe hain taaki B2 cell ka stock bhi miss na ho
        df = pd.read_csv(url, header=None)
        
        # Pehle column (Index 0) me hi hamari range ka data aayega
        raw_symbols = df[0].dropna().astype(str).tolist()
        
        clean_symbols = []
        for s in raw_symbols:
            sym = s.strip()
            # Khali cells aur galti se aaye nan strings ko hatayein
            if sym == "" or sym.lower() == "nan" or sym.lower() == "null":
                continue
            
            # Agar symbol me ':' hai (jaise NSE:SBIN), toh sirf stock code nikalna
            if ":" in sym:
                sym = sym.split(":")[1].strip()
                
            # Indian stocks ke liye .NS lagana compulsory hai Yahoo me
            if not sym.endswith(".NS"):
                sym = sym + ".NS"
                
            clean_symbols.append(sym)
            
        return clean_symbols
    except Exception as e:
        print(f"❌ Google Sheet ki range {STOCK_RANGE} se data read karne me dikkat aayi: {e}")
        return []

def main():
    # 1. Exact range se stocks ki list load karein
    symbols = get_stocks_from_exact_range()
    
    if not symbols:
        print("❌ Di gayi range me koi valid stock symbol nahi mila. Process stopped.")
        return
        
    print(f"📊 Sheet ke '{STOCK_RANGE}' range se total {len(symbols)} stocks load ho gaye hain.")
    print(f"🚀 Fetching hourly data from Yahoo Finance...")
    
    # 2. ⚡ PARALLEL DOWNLOAD ENGINE (Multi-threaded processing)
    data = yf.download(symbols, period=RANGE, interval=INTERVAL, group_by='ticker', threads=True)
    
    # 3. ABSOLUTE MATRIX ALIGNMENT (Pandas Join Network)
    close_prices = pd.DataFrame(index=data.index)
    for ticker in symbols:
        if ticker in data.columns.levels[0]:
            clean_name = ticker.replace(".NS", "")
            close_prices[clean_name] = data[ticker]['Close']
    
    # Date aur Time format ko IST (Indian Standard Time) me convert karna
    if not close_prices.empty:
        close_prices.index = close_prices.index.tz_convert('Asia/Kolkata').strftime('%Y-%m-%d %H:%M')
        close_prices.reset_index(inplace=True)
        close_prices.rename(columns={'index': f'Date & Time ({INTERVAL})'}, inplace=True)
        close_prices.fillna("", inplace=True)
        
        # 📝 SAVE AS CSV
        csv_filename = "pair_data.csv"
        close_prices.to_csv(csv_filename, index=False)
        print(f"🎯 BOOM! 100% Sateek Range-Aligned Matrix CSV ban chuka hai: '{csv_filename}'")
    else:
        print("❌ Yahoo Finance se data fetch nahi ho paya, CSV empty hai.")

if __name__ == "__main__":
    main()
