import os
import json
import urllib.request
import re
import pandas as pd
import yfinance as yf

# Load Grist environment configurations securely from the workflow environment
api_key = os.environ['GRIST_API_KEY']
doc_id = os.environ['GRIST_DOC_ID_LIVE']
table_id = os.environ['GRIST_TABLE_ID']

# List of Indian stocks to track (append .NS for NSE symbols)
tickers = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "SBIN.NS"]

print(f"Fetching dynamic live market data for: {tickers}")

records = []
all_source_headers = []

# 1. Fetch data and dynamically discover all source columns
for idx, ticker in enumerate(tickers, start=1):
    try:
        df = yf.download(ticker, period="1d", interval="1m", progress=False)
        if not df.empty:
            latest_row = df.iloc[-1]
            fields = {"Symbol": ticker}
            
            # Extract all available metrics dynamically from the source
            for raw_col in df.columns:
                safe_id = re.sub(r'[^a-zA-Z0-9]', '_', str(raw_col))
                if safe_id and safe_id[0].isdigit():
                    safe_id = 'col_' + safe_id
                
                val = latest_row[raw_col]
                if hasattr(val, 'iloc'):
                    val = val.iloc[0]
                
                # Format as integer for volume or float for prices
                if pd.api.types.is_integer_dtype(df[raw_col]) or 'Volume' in str(raw_col):
                    fields[safe_id] = int(val) if not pd.isna(val) else 0
                else:
                    fields[safe_id] = float(val) if not pd.isna(val) else 0.0
                
                if safe_id not in all_source_headers and safe_id != 'id':
                    all_source_headers.append(safe_id)

            # Append timestamp tracking
            if "Last_Updated" not in all_source_headers:
                all_source_headers.append("Last_Updated")
            fields["Last_Updated"] = str(df.index[-1])

            records.append({
                "id": idx,
                "fields": fields
            })
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")

# Ensure 'Symbol' leads the sequence
if "Symbol" in all_source_headers:
    all_source_headers.remove("Symbol")
required_col_ids = ["Symbol"] + all_source_headers

print(f"Discovered source columns sequence: {required_col_ids}")

if not records:
    print("Error: No valid records parsed from yfinance.")
    exit(1)

# 2. Fetch existing columns from Grist to compare
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

# 3. Automatically Clean / Delete unnecessary or fake columns not in the source
for cid in existing_cols:
    if cid not in required_col_ids:
        del_url = f"{cols_url}/{cid}"
        del_req = urllib.request.Request(del_url, headers={"Authorization": f"Bearer {api_key}"}, method="DELETE")
        try:
            with urllib.request.urlopen(del_req):
                print(f"Cleaned/Deleted unnecessary column: {cid}")
        except Exception as e:
            print(f"Could not delete column {cid}: {e}")

# 4. Automatically Create missing columns based on source sequence
missing_cols = [cid for cid in required_col_ids if cid not in existing_cols]
if missing_cols:
    new_cols_payload = []
    for cid in missing_cols:
        new_cols_payload.append({
            'id': cid,
            'fields': {
                'label': cid.replace('_', ' ').title(),
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

# 5. Push records update to Grist
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
