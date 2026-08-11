import os
import json
import urllib.request
import re
import pandas as pd
import yfinance as yf

# Load Grist environment configurations securely
api_key = os.environ['GRIST_API_KEY']
doc_id = os.environ['GRIST_DOC_ID']
table_id = os.environ['GRIST_TABLE_ID']

# List of Indian stocks to track (append .NS for NSE symbols)
tickers = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "SBIN.NS"]

print(f"Fetching live market data for: {tickers}")

records = []
standard_headers = ["Symbol", "Open", "High", "Low", "Close", "Volume", "Last_Updated"]

for idx, ticker in enumerate(tickers, start=1):
    try:
        df = yf.download(ticker, period="1d", interval="1m", progress=False)
        if not df.empty:
            latest_row = df.iloc[-1]
            
            # Helper to extract values safely regardless of multi-index format
            def get_val(col_name, is_int=False):
                try:
                    val = latest_row[col_name]
                    if hasattr(val, 'iloc'):
                        val = val.iloc[0]
                    return int(val) if is_int else float(val)
                except Exception:
                    return 0 if is_int else 0.0

            # Map to standard generic column names so all rows match
            open_p = get_val('Open')
            high_p = get_val('High')
            low_p = get_val('Low')
            close_p = get_val('Close')
            vol = get_val('Volume', is_int=True)
            timestamp = str(df.index[-1])
            
            print(f"{ticker} -> O:{open_p} H:{high_p} L:{low_p} C:{close_p} V:{vol}")

            records.append({
                "id": idx,
                "fields": {
                    "Symbol": ticker,
                    "Open": open_p,
                    "High": high_p,
                    "Low": low_p,
                    "Close": close_p,
                    "Volume": vol,
                    "Last_Updated": timestamp
                }
            })
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")

if not records:
    print("Error: No valid records parsed from yfinance.")
    exit(1)

# 1. Fetch existing columns from Grist to compare
cols_url = f"https://docs.getgrist.com/api/docs/{doc_id}/tables/{table_id}/columns"
req_cols = urllib.request.Request(cols_url, headers={"Authorization": f"Bearer {api_key}"}, method="GET")

existing_cols = []
try:
    with urllib.request.urlopen(req_cols) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        for col in data.get('columns', []):
            cid = col.get('id')
            if cid and cid != 'id':
                existing_cols.append(cid)
except Exception as e:
    print(f"Warning: Could not fetch existing columns: {e}")

# 2. Clean / Delete unnecessary or fake columns not in the standard set
for cid in existing_cols:
    if cid not in standard_headers:
        del_url = f"{cols_url}/{cid}"
        del_req = urllib.request.Request(del_url, headers={"Authorization": f"Bearer {api_key}"}, method="DELETE")
        try:
            with urllib.request.urlopen(del_req):
                print(f"Cleaned/Deleted unnecessary column: {cid}")
        except Exception as e:
            print(f"Could not delete column {cid}: {e}")

# 3. Automatically Create missing standard columns if they don't exist
missing_cols = [cid for cid in standard_headers if cid not in existing_cols]
if missing_cols:
    new_cols_payload = []
    for cid in missing_cols:
        new_cols_payload.append({
            'id': cid,
            'fields': {
                'label': cid.replace('_', ' '),
                'type': 'Numeric' if cid not in ['Symbol', 'Last_Updated'] else 'Text'
            }
        })
    
    add_col_data = json.dumps({'columns': new_cols_payload}).encode('utf-8')
    req_add_cols = urllib.request.Request(
        cols_url,
        data=add_col_data,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        },
        method='POST'
    )
    try:
        with urllib.request.urlopen(req_add_cols):
            print(f"Successfully created missing columns: {missing_cols}")
    except urllib.error.HTTPError as e:
        print(f"Error creating columns: {e.code} - {e.read().decode('utf-8')}")
        exit(1)

# 4. Push records update to Grist
records_url = f"https://docs.getgrist.com/api/docs/{doc_id}/tables/{table_id}/records"
payload_data = json.dumps({"records": records}).encode('utf-8')

req = urllib.request.Request(
    records_url,
    data=payload_data,
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    },
    method="PATCH"
)

try:
    with urllib.request.urlopen(req) as response:
        print("Successfully updated Grist table records:", response.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print(f"Grist API Error: {e.code} - {e.read().decode('utf-8')}")
    exit(1)
