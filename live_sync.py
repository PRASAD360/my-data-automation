import os
import json
import urllib.request
import re
import pandas as pd
import yfinance as yf
import concurrent.futures
import time

# Poori script ka start time
total_start = time.time()

# Load Grist environment configurations securely
api_key = os.environ['GRIST_API_KEY']
doc_id = os.environ['GRIST_DOC_ID']
table_id = os.environ['GRIST_TABLE_ID']

SOURCE_TABLE_ID = "SYMBOLS"    
SOURCE_COLUMN_NAME = "SYMBOLS"  

# 1. Grist se tickers fetch karna
t0 = time.time()
tickers = []
try:
    src_url = f"https://docs.getgrist.com/api/docs/{doc_id}/tables/{SOURCE_TABLE_ID}/records"
    req_src = urllib.request.Request(src_url, headers={"Authorization": f"Bearer {api_key}"}, method="GET")
    with urllib.request.urlopen(req_src) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        for row in data.get('records', []):
            val = row.get('fields', {}).get(SOURCE_COLUMN_NAME)
            if val:
                t = str(val).strip()
                if not t.endswith('.NS'):
                    t += '.NS'
                tickers.append(t)
except Exception as e:
    print(f"Error fetching tickers from Grist: {e}")

tickers = list(dict.fromkeys(tickers))
print(f"-> Tickers fetched in: {time.time() - t0:.2f} seconds")

if not tickers:
    print("Error: No tickers found from source table.")
    exit(1)

print(f"Fetching parallel chunked live market data for {len(tickers)} stocks...")

records = []
standard_headers = ["Symbol", "Open", "High", "Low", "Close", "Volume", "Last_Updated"]

chunk_size = 50
chunks = [tickers[i:i + chunk_size] for i in range(0, len(tickers), chunk_size)]

def download_chunk(chunk_tickers):
    chunk_records = []
    try:
        df_all = yf.download(chunk_tickers, period="1d", interval="1m", group_by='ticker', progress=False)
        if df_all.empty:
            return chunk_records

        for ticker in chunk_tickers:
            try:
                df = pd.DataFrame()
                if len(chunk_tickers) == 1:
                    df = df_all
                else:
                    if ticker in df_all.columns.levels[0]:
                        df = df_all[ticker]

                if not df.empty:
                    df = df.dropna(subset=['Close'])
                    if not df.empty:
                        latest_row = df.iloc[-1]

                        def get_val(col_name, is_int=False):
                            try:
                                val = latest_row[col_name]
                                if hasattr(val, 'iloc'):
                                    val = val.iloc[0]
                                return int(val) if is_int else float(val)
                            except Exception:
                                return 0 if is_int else 0.0

                        chunk_records.append({
                            "require": {
                                "Symbol": ticker
                            },
                            "fields": {
                                "Open": get_val('Open'),
                                "High": get_val('High'),
                                "Low": get_val('Low'),
                                "Close": get_val('Close'),
                                "Volume": get_val('Volume', is_int=True),
                                "Last_Updated": str(df.index[-1])
                            }
                        })
            except Exception:
                pass
    except Exception as e:
        print(f"Chunk download error: {e}")
    return chunk_records

# 2. Yfinance Download Time Measure karna
t1 = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    results = executor.map(download_chunk, chunks)
    for chunk_result in results:
        records.extend(chunk_result)

print(f"-> Yfinance Download finished in: {time.time() - t1:.2f} seconds")

if not records:
    print("Error: No valid records parsed from yfinance.")
    exit(1)

print(f"Successfully parsed {len(records)} stocks. Checking Grist columns...")

# 3. Grist Columns Check / Create
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

for cid in existing_cols:
    if cid not in standard_headers:
        del_url = f"{cols_url}/{cid}"
        del_req = urllib.request.Request(del_url, headers={"Authorization": f"Bearer {api_key}"}, method="DELETE")
        try:
            with urllib.request.urlopen(del_req):
                pass
        except Exception:
            pass

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
            pass
    except urllib.error.HTTPError as e:
        print(f"Error creating columns: {e.code} - {e.read().decode('utf-8')}")
        exit(1)

# 4. Grist Records Push (Upsert) Time Measure karna
t2 = time.time()
print("Pushing records to Grist...")
records_url = f"https://docs.getgrist.com/api/docs/{doc_id}/tables/{table_id}/records"
payload_data = json.dumps({"records": records}).encode('utf-8')

req = urllib.request.Request(
    records_url,
    data=payload_data,
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    },
    method="PUT"
)

try:
    with urllib.request.urlopen(req) as response:
        print(f"-> Grist Upload finished in: {time.time() - t2:.2f} seconds")
        print("Successfully upserted Grist table records.")
except urllib.error.HTTPError as e:
    print(f"Grist API Error: {e.code} - {e.read().decode('utf-8')}")
    exit(1)

print(f"=== Total Script Execution Time: {time.time() - total_start:.2f} seconds ===")
