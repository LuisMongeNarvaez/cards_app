#!/usr/bin/env python3
import sys
import csv
import re

# 1. Gather input parameters
set_name = input("Enter Set Name (e.g. 1991 Pro Set): ").strip()
sport = input("Enter Sport (MLB, NFL, NBA, NHL): ").strip()
qty_input = input("Enter Quantity [default 1]: ").strip()
qty = qty_input if qty_input else "1"
est_val = "$0.15"

output_filename = "cards_output.tsv"

print("\n" + "=" * 60)
print("Paste your card list below.")
print("When finished pasting, press Enter then Ctrl+D:")
print("=" * 60 + "\n", flush=True)

seen_numbers = set()
rows = []

# 2. Process stdin line-by-line
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    
    parts = line.split(maxsplit=1)
    card_num = parts[0]
    player_name = parts[1] if len(parts) > 1 else ""

    # Extract base number to prevent duplicate variants (e.g. 5a / 5b)
    if re.match(r'^\d+[a-zA-Z]*$', card_num):
        base_num = re.sub(r'[a-zA-Z]+$', '', card_num)
    else:
        base_num = f"{card_num}_{player_name}"

    if base_num in seen_numbers:
        continue
    
    seen_numbers.add(base_num)

    # 9-column layout
    rows.append([
        card_num,   # Card Number
        set_name,   # Set Name
        qty,        # Qty
        player_name,# Player
        "",         # Team (empty)
        sport,      # Sport
        est_val,    # Estimate Value
        "",         # Total Value (empty)
        ""          # Notes (empty)
    ])

# 3. Write strictly formatted TSV with quoted strings
headers = ["Card Number", "Set Name", "Qty", "Player", "Team", "Sport", "Estimate Value", "Total Value", "Notes"]

with open(output_filename, mode="w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    writer.writerows(rows)

print(f"\n[DONE] Saved {len(rows)} unique cards directly to '{output_filename}'")
