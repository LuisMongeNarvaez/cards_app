#!/usr/bin/env python3
import os
import time
import google.oauth2.service_account
import gspread
from google import genai

# --- 1. INITIALIZE GEMINI CLIENT ---
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("❌ Error: GEMINI_API_KEY environment variable not found!")
    print("Run: export GEMINI_API_KEY='your_key_here'")
    exit(1)

ai_client = genai.Client(api_key=api_key)

# --- 2. GOOGLE SHEETS AUTHENTICATION ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

try:
    creds = google.oauth2.service_account.Credentials.from_service_account_file(
        "credentials.json", scopes=SCOPES
    )
    client = gspread.authorize(creds)
    worksheet = client.open_by_key("121WYq0sNSxhR2r_Tb_OPNHdrRwyR9KRC6e1pokCwsLQ").worksheet("Inventory_Log")
    data = worksheet.get_all_values()
    print(f"✅ Sheet connected. Total rows: {len(data)}")
except Exception as e:
    print(f"❌ Connection error: {e}")
    exit(1)

# --- 3. LOCATE COLUMNS ---
header_row_idx = None
headers = []

for idx, row in enumerate(data):
    clean_row = [str(cell).strip() for cell in row]
    if "Card Number" in clean_row and "Set Name" in clean_row:
        header_row_idx = idx
        headers = clean_row
        break

if header_row_idx is None:
    print("❌ Headers not found!")
    exit(1)

card_num_idx = headers.index("Card Number") + 1
player_col_idx = headers.index("Player") + 1
team_col_idx = headers.index("Team") + 1
set_col_idx = headers.index("Set Name") + 1
sport_col_idx = headers.index("Sport") + 1 if "Sport" in headers else None


def query_gemini_team(player: str, set_name: str, sport: str) -> str:
    """Queries Gemini model to determine official team affiliation."""
    prompt = (
        f"What official team did the sports figure '{player}' belong to for the set '{set_name}' ({sport})? "
        f"Return ONLY the exact team name. If unknown, reply 'Unknown'."
    )
    try:
        response = ai_client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
        )
        team_name = response.text.strip()
        if team_name.lower() in ["unknown", "n/a", "none"]:
            return ""
        return team_name
    except Exception as e:
        print(f"    ⚠️ Gemini API Error: {e}")
        return ""

# --- 4. DATA PROCESSING LOOP ---
print("\n🤖 Autofilling missing teams using Gemini AI...\n")

updates = []
count_updated = 0

for row_idx, row in enumerate(data[header_row_idx + 1 :], start=header_row_idx + 2):
    player = row[player_col_idx - 1] if len(row) >= player_col_idx else ""
    team = row[team_col_idx - 1] if len(row) >= team_col_idx else ""
    set_name = row[set_col_idx - 1] if len(row) >= set_col_idx else ""
    sport_val = row[sport_col_idx - 1] if (sport_col_idx and len(row) >= sport_col_idx) else ""

    if player.strip() and not team.strip():
        print(f"Row {row_idx}: Querying Gemini for '{player}' in [{set_name}]...")
        
        found_team = query_gemini_team(player, set_name, sport_val)

        if found_team:
            print(f"  --> ✅ Found Team: {found_team}")
            updates.append({
                "range": gspread.utils.rowcol_to_a1(row_idx, team_col_idx),
                "values": [[found_team]]
            })
            count_updated += 1
        else:
            print("  --> ❌ Team not found")

        # Stay within free tier rate limit (~15 requests per minute)
        time.sleep(4.0)

        # Batch write to Google Sheet every 10 updates
        if len(updates) >= 10:
            worksheet.batch_update(updates)
            print(f"\n💾 Saved batch of {len(updates)} entries to Google Sheet...\n")
            updates = []

if updates:
    worksheet.batch_update(updates)
    print(f"\n💾 Saved final batch of {len(updates)} entries to Google Sheet.")

print(f"\n✨ Process complete! Total updated: {count_updated}")
