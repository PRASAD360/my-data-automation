import os
import json
import urllib.request
import yfinance as yf

# Load Grist environment configurations securely
api_key = os.environ['GRIST_API_KEY']
doc_id = os.environ['GRIST_DOC_ID']
table_id = os.environ['GRIST_TABLE_ID']

# List of Indian stocks to track (append .NS for NSE symbols)
tickers = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "SBIN.NS"]

print(f"Fetching live market data for: {tickers}")

records_to_update = []

def extract_val(series_or_scalar, is_int=False):
    """Safely extracts a scalar value from a pandas series/dataframe cell."""
    val = series_or_scalar.iloc[-1]
    if hasattr(val, 'iloc'):
        val = val.iloc[0]
    return int(val) if is_int else float(val)

for idx, ticker in enumerate(tickers, start=1):
    try:
        # Fetch the latest 1-minute interval data for the current day
        df = yf.download(ticker, period="1d", interval="1m", progress=False)
        if not df.empty:
            open_price = extract_val(df['Open'])
            high_price = extract_val(df['High'])
            low_price = extract_val(df['Low'])
            close_price = extract_val(df['Close'])
            volume = extract_val(df['Volume'], is_int=True)
            timestamp = str(df.index[-1])
            
            print(f"{ticker} -> O:{open_price} H:{high_price} L:{low_price} C:{close_price} V:{volume} at {timestamp}")
            
            # Map all fields to match your Grist table column IDs
            records_to_update.append({
                "id": idx,
                "fields": {
                    "Symbol": ticker,
                    "Open": open_price,
                    "High": high_price,
                    "Low": low_price,
                    "Close": close_price,
                    "Volume": volume,
                    "Last_Updated": timestamp
                }
            })
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")

if records_to_update:
    records_url = f"https://docs.getgrist.com/api/docs/{doc_id}/tables/{table_id}/records"
    payload_data = json.dumps({"records": records_to_update}).encode('utf-8')
    
    req = urllib.request.Request(
        records_url,
        data=payload_data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        method="PATCH"  # PATCH updates existing row IDs
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            print("Successfully updated Grist table:", response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print(f"Grist API Error: {e.code} - {e.read().decode('utf-8')}")
        exit(1)
else:
    print("No valid records found to update.")
