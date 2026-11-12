#!/usr/bin/env -S streamlit run
import io
import os
import google.oauth2.service_account
import gspread
import polars as pl
import requests
import streamlit as st

st.set_page_config(
    page_title="Sports Card Dashboard", page_icon="🏎️", layout="wide"
)
st.title("🏎️ Sports Card Collection Board")

sheet_id = "121WYq0sNSxhR2r_Tb_OPNHdrRwyR9KRC6e1pokCwsLQ"
csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=Inventory_Log"
parquet_cache = "inventory_cache.parquet"


# --- 1. GOOGLE SHEETS AUTHENTICATION & SAFE APPEND ---
@st.cache_resource
def get_gspread_client():
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_path = "credentials.json"
    if not os.path.exists(creds_path):
        st.error(f"Missing '{creds_path}'! Please place your Google Cloud credentials JSON file in the project folder.")
        st.stop()
        
    creds = google.oauth2.service_account.Credentials.from_service_account_file(
        creds_path, scopes=SCOPES
    )
    return gspread.authorize(creds)


def safe_add_card(
    card_number: str,
    set_name: str,
    qty: int,
    player: str,
    team: str,
    sport: str,
    est_value: float,
    notes: str = "",
):
    """Safely appends a new card entry to the bottom of Inventory_Log."""
    client = get_gspread_client()
    worksheet = client.open_by_key(sheet_id).worksheet("Inventory_Log")

    est_val_formatted = f"${est_value:.2f}"
    new_row = [
        str(card_number),
        str(set_name),
        int(qty),
        str(player),
        str(team),
        str(sport),
        est_val_formatted,
        "",  # Let spreadsheet formula calculate Total Value
        str(notes),
    ]

    worksheet.append_row(new_row, value_input_option="USER_ENTERED")
    st.cache_data.clear()


# --- 2. FAST READ & CACHE VIA POLARS (PURE SPREADSHEET READ) ---
@st.cache_data(ttl=60)
def load_and_cache_data():
    response = requests.get(csv_url)
    text_lines = response.text.splitlines()

    header_idx = 0
    found_header = False
    for idx, line in enumerate(text_lines):
        if "Card Number" in line and "Set Name" in line:
            header_idx = idx
            found_header = True
            break

    if not found_header:
        st.error("Could not find header row containing 'Card Number' and 'Set Name'.")
        st.stop()

    csv_data = "\n".join(text_lines[header_idx:])

    raw_df = pl.read_csv(
        io.StringIO(csv_data),
        infer_schema_length=0,
        ignore_errors=True,
    )

    clean_cols = [str(c).replace('"', "").strip() for c in raw_df.columns]
    raw_df.columns = clean_cols

    df = raw_df.filter(
        pl.col("Set Name").is_not_null()
        & (pl.col("Set Name") != "Set Name")
        & (pl.col("Card Number") != "Card Number")
    )

    for col_name in ["Player", "Set Name", "Sport", "Team", "Notes"]:
        if col_name in df.columns:
            df = df.with_columns(
                pl.col(col_name).cast(pl.Utf8).fill_null("").str.strip_chars()
            )
        else:
            df = df.with_columns(pl.lit("").alias(col_name))

    if "Qty" in df.columns:
        df = df.with_columns(
            pl.col("Qty")
            .cast(pl.Utf8)
            .str.replace_all(",", "")
            .cast(pl.Float64, strict=False)
            .fill_null(0.0)
        )
    else:
        df = df.with_columns(pl.lit(0.0).alias("Qty"))

    # --- READ ESTIMATE VALUE DIRECTLY FROM SHEET ---
    if "Estimate Value" in df.columns:
        df = df.with_columns(
            pl.col("Estimate Value")
            .cast(pl.Utf8)
            .str.replace_all(r"[\$,]", "")
            .cast(pl.Float64, strict=False)
            .fill_null(0.0)
            .alias("Estimate_Value_Num")
        )
    else:
        df = df.with_columns(pl.lit(0.0).alias("Estimate_Value_Num"))

    # --- READ TOTAL VALUE DIRECTLY FROM SHEET ---
    if "Total Value" in df.columns:
        df = df.with_columns(
            pl.col("Total Value")
            .cast(pl.Utf8)
            .str.replace_all(r"[\$,]", "")
            .cast(pl.Float64, strict=False)
            .fill_null(0.0)
            .alias("Total Value_Num")
        )
    else:
        df = df.with_columns(pl.lit(0.0).alias("Total Value_Num"))

    df.write_parquet(parquet_cache)
    return df


df = load_and_cache_data()

# Status indicator
if os.path.exists(parquet_cache):
    file_size_kb = os.path.getsize(parquet_cache) / 1024
    st.sidebar.success(
        f"⚡ Connected via Polars\n📦 Parquet Cache: {file_size_kb:.1f} KB"
    )

# --- SIDEBAR: SAFE APPEND NEW CARD FORM ---
st.sidebar.header("📥 Add New Card")
with st.sidebar.expander("Safe Append Form"):
    with st.form("add_card_form", clear_on_submit=True):
        new_card_num = st.text_input("Card Number #:", value="")
        new_set_name = st.text_input("Set Name:", value="")
        new_qty = st.number_input("Quantity:", min_value=1, value=1, step=1)
        new_player = st.text_input("Player Name:", value="")
        new_team = st.text_input("Team:", value="")

        existing_sports = (
            sorted(
                [
                    s
                    for s in df["Sport"].unique().to_list()
                    if s is not None and str(s).strip() != ""
                ]
            )
            if "Sport" in df.columns
            else ["MLB", "NFL", "NBA", "NHL"]
        )
        new_sport = st.selectbox("Sport:", options=existing_sports)
        new_est_val = st.number_input(
            "Estimated Value ($):", min_value=0.0, value=0.15, step=0.05
        )
        new_notes = st.text_input("Notes / Tags (e.g. RC, HOF, VAR):", value="")

        submit_btn = st.form_submit_button("Append to Google Sheets")

        if submit_btn:
            if not new_card_num or not new_set_name or not new_player:
                st.error("Please fill in Card Number, Set Name, and Player Name.")
            else:
                try:
                    safe_add_card(
                        card_number=new_card_num,
                        set_name=new_set_name,
                        qty=new_qty,
                        player=new_player,
                        team=new_team,
                        sport=new_sport,
                        est_value=new_est_val,
                        notes=new_notes,
                    )
                    st.success(
                        f"Successfully appended {new_player} (#{new_card_num})!"
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Error appending card: {e}")

st.sidebar.markdown("---")

# --- SIDEBAR: FILTERS ---
st.sidebar.header("Filter Collection")

show_hof_rc_only = st.sidebar.checkbox(
    "⭐ Show HOF & RC Cards Only", 
    value=False,
    help="Instantly filter view to show only in-stock Hall of Fame and Rookie cards."
)

sports_list = []
if "Sport" in df.columns:
    sports_list = sorted(
        [
            s
            for s in df["Sport"].unique().to_list()
            if s is not None and str(s).strip() != ""
        ]
    )

selected_sports = st.sidebar.multiselect(
    "Select Sport:", options=sports_list, default=sports_list
)

st.sidebar.subheader("🏷️ Tag / Attribute Filter")
available_tags = ["RC", "VAR", "HOF", "UER", "SSS", "CPC"]
selected_tags = st.sidebar.multiselect(
    "Filter by Tags (Notes):",
    options=available_tags,
    default=[],
    help="Select tags to filter records containing specific attributes like Rookie (RC) or Hall of Fame (HOF)."
)

search_query = st.sidebar.text_input("Search Player, Set, or Notes:").strip()

# --- FILTERING LOGIC ---
filtered_df = df

# Permanently enforce showing only in-stock cards (Qty > 0)
if "Qty" in filtered_df.columns:
    filtered_df = filtered_df.filter(pl.col("Qty") > 0)

if show_hof_rc_only:
    filtered_df = filtered_df.filter(
        pl.col("Notes").str.contains(r"\b(RC|HOF)\b", literal=False)
    )

if "Sport" in df.columns and selected_sports:
    filtered_df = filtered_df.filter(pl.col("Sport").is_in(selected_sports))
elif "Sport" in df.columns and not selected_sports:
    filtered_df = filtered_df.head(0)

if selected_tags:
    tag_conditions = [
        pl.col("Notes").str.contains(rf"\b{tag}\b", literal=False)
        for tag in selected_tags
    ]
    combined_tag_filter = tag_conditions[0]
    for cond in tag_conditions[1:]:
        combined_tag_filter = combined_tag_filter | cond
        
    filtered_df = filtered_df.filter(combined_tag_filter)

if search_query:
    q_lower = search_query.lower()
    filtered_df = filtered_df.filter(
        pl.col("Player").str.to_lowercase().str.contains(q_lower, literal=True)
        | pl.col("Set Name").str.to_lowercase().str.contains(q_lower, literal=True)
        | pl.col("Notes").str.to_lowercase().str.contains(q_lower, literal=True)
    )

# --- MAIN INVENTORY VIEW & METRICS ---
total_entries = int(filtered_df["Qty"].sum()) if "Qty" in filtered_df.columns else len(filtered_df)
total_val = (
    filtered_df["Total Value_Num"].sum()
    if "Total Value_Num" in filtered_df.columns
    else 0.0
)

col1, col2 = st.columns(2)
col1.metric("In-Stock Cards", f"{total_entries:,}")
col2.metric("Estimated Sale Value", f"${total_val:,.2f}")

st.markdown("---")

# --- VALUE BREAKDOWN GRAPHIC & SUMMARY (HIDDEN INSIDE EXPANDER) ---
if len(filtered_df) > 0:
    chart_df = filtered_df.with_columns(
        pl.when(pl.col("Notes").str.contains(r"\bRC\b", literal=False))
        .then(pl.lit("Rookie Cards (RC)"))
        .when(pl.col("Notes").str.contains(r"\bHOF\b", literal=False))
        .then(pl.lit("Hall of Famers (HOF)"))
        .when(pl.col("Set Name").str.contains("1966|1968", literal=False))
        .then(pl.lit("Vintage Sets (1966/1968)"))
        .otherwise(pl.lit("Standard Inventory"))
        .alias("Card Tier")
    )
    
    tier_summary = (
        chart_df.group_by("Card Tier")
        .agg([
            pl.col("Total Value_Num").sum().alias("Total Value ($)"),
            pl.len().alias("Card Quantity")
        ])
        .sort("Total Value ($)", descending=True)
        .to_pandas()
    )

    with st.expander("📊 Collection Breakdown by Tier (Quantities & Values)", expanded=False):
        st.bar_chart(
            data=tier_summary,
            x="Card Tier",
            y=["Total Value ($)", "Card Quantity"],
            use_container_width=True
        )
        st.dataframe(tier_summary, use_container_width=True, hide_index=True)

st.markdown("---")

display_cols = [
    c
    for c in [
        "Card Number",
        "Set Name",
        "Qty",
        "Player",
        "Team",
        "Sport",
        "Estimate Value",
        "Total Value",
        "Notes",
    ]
    if c in filtered_df.columns
]

st.dataframe(
    filtered_df.select(display_cols).to_pandas(),
    use_container_width=True,
    height=550,
)
