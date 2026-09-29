#!/usr/bin/env python3
import sys
import re
import gspread

# ---------------------------------------------------------
# 1. Credentials & Google Sheets Setup
# ---------------------------------------------------------
gc = gspread.service_account(filename="/home/luis/credentials.json")
sh = gc.open_by_key("121WYq0sNSxhR2r_Tb_OPNHdrRwyR9KRC6e1pokCwsLQ")
worksheet = sh.worksheet("Inventory_Log")

print("📥 Fetching current sheet data...")
all_data = worksheet.get_all_values()
headers = all_data[0]

# Locate column index positions
card_num_col = headers.index("Card Number")
set_name_col = headers.index("Set Name")
notes_col = headers.index("Notes")

# Build lookup table: (card_number, set_name) -> {row_idx, existing_notes}
record_lookup = {}
for row_idx, row in enumerate(all_data[1:], start=2):
    if len(row) > max(card_num_col, set_name_col):
        c_num = str(row[card_num_col]).strip()
        s_name = str(row[set_name_col]).strip()
        e_notes = str(row[notes_col]).strip() if len(row) > notes_col else ""
        
        lookup_key = (c_num.lower(), s_name.lower())
        record_lookup[lookup_key] = {
            "row_idx": row_idx,
            "existing_notes": e_notes
        }

# ---------------------------------------------------------
# 2. Category & Tag Prompt
# ---------------------------------------------------------
print("\n🏷️ Select Tag Category to Apply:")
print("  1. Hall of Famers (Adds 'HOF')")
print("  2. Rookies (Adds 'RC')")
print("  3. Custom Tag")

choice = input("Enter choice (1-3) or type tag directly [Default: 1]: ").strip()

default_tag = "HOF"
if choice == "2" or choice.lower() == "rc" or choice.lower() == "rookie":
    default_tag = "RC"
elif choice == "3":
    default_tag = input("Enter custom tag (e.g. SubSet, Autograph): ").strip().upper()
elif choice and choice != "1":
    default_tag = choice.upper()

# ---------------------------------------------------------
# 3. Dynamic User Input
# ---------------------------------------------------------
print(f"\n📋 Paste your raw checklist text for [{default_tag}] below.")
print("👉 When finished pasting, press Enter, then press Ctrl+D (Linux/macOS) or Ctrl+Z (Windows) to execute:\n")

raw_text = sys.stdin.read()

if not raw_text.strip():
    print("❌ No text entered. Exiting script.")
    sys.exit()

lines = [l.strip() for l in raw_text.strip().split('\n') if l.strip()]

# Ask for Set Name dynamically (or use the first line as set name fallback)
default_set = lines[0] if lines else "1991 Fleer Baseball"
set_name = input(f"Enter Set Name [Default: '{default_set}']: ").strip() or default_set

# Skip header line if user accepted default header line as set name
start_index = 1 if set_name == default_set else 0

# ---------------------------------------------------------
# 4. Match & Prepare Batch Updates
# ---------------------------------------------------------
pattern = re.compile(r"^(\d+[a-z]?)\s+(.*?)(?:\s+([A-Z,\s]+))?$")
known_tags = {"VAR", "UER", "SSS", "CPC", "HOF", "ROO", "RC"}

cell_updates = []
updated_count = 0
not_found_count = 0

for line in lines[start_index:]:
    match = pattern.match(line)
    if match:
        card_num, player_str, tags_str = match.groups()
        
        new_tags = [default_tag]  # Apply selected category tag (HOF, RC, etc.)
        
        if tags_str:
            new_tags.extend([t.strip() for t in tags_str.split(',') if t.strip()])
        
        words = player_str.split()
        for w in words:
            clean_word = w.strip(',')
            if clean_word in known_tags:
                new_tags.append(clean_word)

        lookup_key = (card_num.lower(), set_name.lower())
        
        if lookup_key in record_lookup:
            rec = record_lookup[lookup_key]
            existing_notes = rec["existing_notes"]
            
            # Combine existing and new tags without duplicates
            combined = [t.strip() for t in existing_notes.split(',') if t.strip()]
            for nt in new_tags:
                if nt not in combined:
                    combined.append(nt)
            
            updated_notes_field = ", ".join(dict.fromkeys(combined))
            
            # Append batch update cell if notes changed
            if updated_notes_field != existing_notes:
                row_idx = rec["row_idx"]
                col_letter = gspread.utils.rowcol_to_a1(row_idx, notes_col + 1)
                cell_updates.append({
                    'range': col_letter,
                    'values': [[updated_notes_field]]
                })
                updated_count += 1
        else:
            not_found_count += 1
            print(f"⚠️ Not found in sheet: Card #{card_num} - {set_name}")

# ---------------------------------------------------------
# 5. Push Updates to Google Sheets
# ---------------------------------------------------------
if cell_updates:
    worksheet.batch_update(cell_updates)
    print(f"\n✅ Successfully updated 'Notes' with [{default_tag}] for {updated_count} matching records!")
else:
    print(f"\nℹ️ No new notes were added; all matching records already contained [{default_tag}].")

if not_found_count > 0:
    print(f"ℹ️ {not_found_count} records were not found in the spreadsheet.")
