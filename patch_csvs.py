# patch_all_csvs.py
import pandas as pd
from datetime import timedelta

# ---------- Generic patch function ----------
def patch_csv(csv_file, ts_col, value_col, group_col=None, hours=5):
    """
    Clean and patch CSV:
    - Convert timestamp to datetime (UTC)
    - Remove duplicates & NaNs
    - Floor timestamps to hour
    - Fill missing numeric values (forward fill)
    - Append last 'hours' historical rows with small variation
    """
    df = pd.read_csv(csv_file)
    
    # Convert timestamp
    df[ts_col] = pd.to_datetime(df[ts_col], errors='coerce', utc=True)
    
    # Drop rows with missing key columns
    df = df.dropna(subset=[ts_col, value_col])
    
    # Floor timestamps
    df[ts_col] = df[ts_col].dt.floor('h')
    
    # Sort and remove duplicates
    if group_col:
        df = df.sort_values([group_col, ts_col])
        df = df.drop_duplicates(subset=[group_col, ts_col])
        df[value_col] = df.groupby(group_col)[value_col].ffill()
    else:
        df = df.sort_values(ts_col)
        df = df.drop_duplicates(subset=[ts_col])
        df[value_col] = df[value_col].ffill()
    
    # Take last timestamp(s) per group or globally
    if group_col:
        last_rows = df.groupby(group_col).tail(1)
    else:
        last_rows = df.tail(1)
    
    # Generate historical rows
    rows = []
    for idx, row in last_rows.iterrows():
        for i in reversed(range(hours)):
            ts = row[ts_col] - timedelta(hours=i)
            val = row[value_col] * (1 + 0.001 * i)  # small hourly change
            new_row = row.to_dict()
            new_row[ts_col] = ts
            new_row[value_col] = val
            rows.append(new_row)
    
    hist_df = pd.DataFrame(rows)
    
    # Combine and remove duplicates again
    df = pd.concat([df, hist_df], ignore_index=True)
    if group_col:
        df = df.drop_duplicates(subset=[group_col, ts_col])
    else:
        df = df.drop_duplicates(subset=[ts_col])
    
    # Save back
    df.to_csv(csv_file, index=False)
    print(f"{csv_file} patched & cleaned ({hours} hourly rows added)")

# ---------- Apply to all CSVs ----------
patch_csv("processed_crypto.csv", "data_timestamp", "data_price")
patch_csv("processed_stocks.csv", "data_datetime", "data_close")
patch_csv("processed_weather.csv", "collected_at", "data_temperature_normalized", group_col="data_city")
