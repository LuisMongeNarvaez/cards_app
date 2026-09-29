import io
import pandas as pd

# 1. Google Sheet details
SPREADSHEET_ID = "121WYq0sNSxhR2r_Tb_OPNHdrRwyR9KRC6e1pokCwsLQ"
SHEET_NAME = "Inventory_Log"

url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"

# 2. Load the raw CSV
df = pd.read_csv(url, header=None)

# 3. Keep only the first 6 columns and assign your clean headers
clean_df = df.iloc[:, :6].copy()
clean_df.columns = ["Card Number", "Set Name", "Qty", "Player", "Team", "Sport"]

# 4. Clean up trailing/leading whitespace and fix decimal quantities (e.g. 0.0 -> 0 or 1.0 -> 1)
for col in clean_df.columns:
    clean_df[col] = clean_df[col].astype(str).str.strip()

clean_df["Qty"] = (
    pd.to_numeric(clean_df["Qty"], errors="coerce").fillna(0).astype(int)
)

# 5. Export clean, formatted CSV for the buyer
clean_df.to_csv(
    "Pop_Collection_Clean_Buyer_List.csv", index=False, quoting=1
)

print("Successfully cleaned up the spreadsheet!")
print(clean_df.head(10))
