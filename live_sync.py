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

# --- Tickers aur Industry kahaan se lene hain uski Table ID aur Column Names ---
SOURCE_TABLE_ID = "SYMBOLS"    
SOURCE_COLUMN_NAME = "SYMBOLS"  
INDUSTRY_COLUMN_NAME = "INDUSTRY"

# Grist se tickers aur unke industry names dynamically fetch karne ka code
stock_data_map = {}
try:
    src_url = f"https://docs.getgrist.com/api/docs/{doc_id}/tables/{SOURCE_TABLE_ID}/records"
    req_src = urllib.request.Request(src_url, headers={"Authorization": f"Bearer {api_key}"}, method="GET")
    with urllib.request.urlopen(req_src) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        for row in data.get('records', []):
            fields = row.get('fields', {})
            val = fields.get(SOURCE_COLUMN_NAME)
            ind_val = fields.get(INDUSTRY_COLUMN_NAME, "")
            if val:
                t = str(val).strip()
                if not t.endswith('.NS'):
                    t += '.NS'
                stock_data_map[t] = str(ind_val).strip() if ind_val else ""
except Exception as e:
    print(f"Error fetching tickers from Grist: {e}")

# Duplicates hatayein (tickers ki list)
tickers = list(dict.fromkeys(stock_data_map.keys()))

if not tickers:
    print("Error: No tickers found from source table.")
    exit(1)

print(f"Fetching chunked batch live market data with industry names for {len(tickers)} stocks...")

records_to_save = []
standard_headers = ["Symbol", "Industry", "Open", "High", "Low", "Close", "Volume", "Last_Updated"]

# 50-50 tickers ke chunks mein download karna
chunk_size = 50
for i in range(0, len(tickers), chunk_size):
    chunk_tickers = tickers[i:i + chunk_size]
    try:
        df_all = yf.download(chunk_tickers, period="1d", interval="1m", group_by='ticker', progress=False)
        if df_all.empty:
            continue

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

                        records_to_save.append({
                            "fields": {
                                "Symbol": ticker,
                                "Industry": stock_data_map.get(ticker, ""),
                                "Open": get_val('Open'),
                                "High": get_val('High'),
                                "Low": get_val('Low'),
                                "Close": get_val('Close'),
                                "Volume": get_val('Volume', is_int=True),
                                "Last_Updated": str(df.index[-1])
                            }
                        })
            except Exception as e:
                pass
    except Exception as e:
        print(f"Chunk download error for batch {i}: {e}")

if not records_to_save:
    print("Error: No valid records parsed from yfinance.")
    exit(1)

print(f"Successfully parsed {len(records_to_save)} stocks. Preparing Grist columns...")

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
                'type': 'Numeric' if cid not in ['Symbol', 'Industry', 'Last_Updated'] else 'Text'
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

records_url = f"https://docs.getgrist.com/api/docs/{doc_id}/tables/{table_id}/records"

# 4. Target table ke pehle se mojood saare records fetch karo (unki IDs ke sath)
existing_records = []
try:
    req_get_target = urllib.request.Request(records_url, headers={"Authorization": f"Bearer {api_key}"}, method="GET")
    with urllib.request.urlopen(req_get_target) as resp:
        target_data = json.loads(resp.read().decode('utf-8'))
        existing_records = target_data.get('records', [])
except Exception as e:
    print(f"Warning fetching target records: {e}")

update_records = []
create_records = []

# 5. Sequential Overwrite Logic:
for idx, rec in enumerate(records_to_save):
    if idx < len(existing_records):
        ex_id = existing_records[idx]['id']
        update_records.append({
            "id": ex_id,
            "fields": rec["fields"]
        })
    else:
        create_records.append(rec)

# Step A: Existing rows ko unhi IDs par PATCH (overwrite) karo
if update_records:
    try:
        patch_payload = json.dumps({"records": update_records}).encode('utf-8')
        req_patch = urllib.request.Request(
            records_url,
            data=patch_payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="PATCH"
        )
        with urllib.request.urlopen(req_patch) as resp:
            print("Successfully overwritten top rows sequentially with Industry names.")
    except urllib.error.HTTPError as e:
        print(f"Error updating rows: {e.code} - {e.read().decode('utf-8')}")

# Step B: Agar naye records zyada hain, toh niche naye create karo
if create_records:
    try:
        post_payload = json.dumps({"records": create_records}).encode('utf-8')
        req_post = urllib.request.Request(
            records_url,
            data=post_payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req_post) as resp:
            print("Successfully created extra new rows.")
    except urllib.error.HTTPError as e:
        print(f"Error creating extra rows: {e.code} - {e.read().decode('utf-8')}")

# Step C: Agar purane records zyada the aur naye kam hain, toh neeche ke bache hue excess rows ko DELETE kar do
if len(existing_records) > len(records_to_save):
    excess_ids = [row['id'] for row in existing_records[len(records_to_save):]]
    
    if excess_ids:
        try:
            delete_url = f"{records_url}?" + "&".join([f"id={rid}" for rid in excess_ids])
            req_delete = urllib.request.Request(
                delete_url,
                headers={"Authorization": f"Bearer {api_key}"},
                method="DELETE"
            )
            with urllib.request.urlopen(req_delete) as resp:
                print(f"Successfully deleted {len(excess_ids)} excess rows from the bottom.")
        except urllib.error.HTTPError as e:
            print(f"Error deleting excess rows: {e.code} - {e.read().decode('utf-8')}")
