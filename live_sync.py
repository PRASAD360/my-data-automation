# Step C: Agar purane records zyada hain, toh neeche ke bache hue excess rows ko DELETE kar do
if len(existing_records) > len(records_to_save):
    excess_ids = [row['id'] for row in existing_records[len(records_to_save):]]
    
    if excess_ids:
        try:
            # Grist records delete karne ke liye URL ke sath query parameters mein IDs bhejte hain
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
