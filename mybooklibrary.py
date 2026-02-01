import streamlit as st
import pandas as pd
import plotly.express as px
import firebase_admin
from firebase_admin import credentials, firestore
import uuid
import json
import ast
import requests
import datetime

# --- CONFIGURATION & SETUP ---
st.set_page_config(page_title="Library OS Pro", page_icon="📚", layout="wide")

# --- FIREBASE CONNECTION (Smart Parse) ---
@st.cache_resource
def init_firebase():
    """Initializes Firebase with error handling for Secrets formatting."""
    if not firebase_admin._apps:
        try:
            if "firebase" in st.secrets:
                key_content = st.secrets["firebase"]["textkey"]
                try:
                    key_dict = json.loads(key_content)
                except ValueError:
                    try:
                        key_dict = json.loads(key_content, strict=False)
                    except ValueError:
                        try:
                            key_dict = ast.literal_eval(key_content)
                        except:
                            raise ValueError("Could not parse Secrets key.")
                
                cred = credentials.Certificate(key_dict)
                firebase_admin.initialize_app(cred)
            else:
                # Local fallback
                cred = credentials.Certificate("firebase_key.json")
                firebase_admin.initialize_app(cred)
        except Exception as e:
            st.error(f"❌ Connection Error: {e}")
            return None
    return firestore.client()

db = init_firebase()

# --- HELPER: GOOGLE BOOKS API ---
@st.cache_data(ttl=3600)
def fetch_book_metadata(query):
    """
    Searches Google Books API for a title/ISBN.
    Returns: dict with title, authors, year, categories, thumbnail
    """
    if not query:
        return None
    
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q={query}"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if "items" in data:
                item = data['items'][0]['volumeInfo']
                
                # Extract data safely
                return {
                    "Title": item.get('title', query),
                    "Author": ", ".join(item.get('authors', ["Unknown"])),
                    "Year": int(item.get('publishedDate', '2000')[:4]),
                    "Genre": item.get('categories', ["General"])[0],
                    "Cover": item.get('imageLinks', {}).get('thumbnail', None),
                    "Description": item.get('description', "No description available.")
                }
    except Exception as e:
        print(f"API Error: {e}")
    return None

# --- DATA FUNCTIONS ---
def get_data():
    """Fetches all books from Firestore."""
    if not db: return pd.DataFrame()
    try:
        docs = db.collection('books').stream()
        items = [{"id": doc.id, **doc.to_dict()} for doc in docs]
        return pd.DataFrame(items) if items else pd.DataFrame(columns=["Title", "Author", "Status", "Rating", "Year"])
    except:
        return pd.DataFrame()

def save_changes_to_db(df_original, df_edited):
    """
    Compares original vs edited dataframe and pushes updates to Firestore.
    This enables Two-Way Sync.
    """
    if not db: return
    
    # Identify changes
    changes_count = 0
    progress_bar = st.progress(0)
    
    # Iterate through rows to find diffs (Simplified for robustness)
    # in a production app with thousands of rows, we'd use index comparison
    for index, row in df_edited.iterrows():
        book_id = row['id']
        
        # Check if this ID exists in original (it should)
        original_row = df_original[df_original['id'] == book_id]
        
        if not original_row.empty:
            # Check for specific field changes
            orig_status = original_row.iloc[0]['Status']
            orig_rating = original_row.iloc[0]['Rating']
            
            if row['Status'] != orig_status or row['Rating'] != orig_rating:
                # Update Firestore
                db.collection('books').document(book_id).update({
                    "Status": row['Status'],
                    "Rating": row['Rating']
                })
                changes_count += 1
                
    progress_bar.empty()
    if changes_count > 0:
        st.success(f"✅ Synced {changes_count} changes to cloud!")
        st.cache_data.clear() # Clear cache to force refresh
        st.rerun()

# --- UI LAYOUT ---
with st.sidebar:
    st.header("Library OS Pro")
    page = st.radio("Navigation", ["📊 Dashboard", "📚 Inventory (Sync)", "➕ Add (Auto-Fill)", "📈 Analytics"])
    st.divider()
    
    # Feature 3: Reading Challenge Settings
    st.subheader("🎯 2026 Challenge")
    goal = st.number_input("Target Books", value=20, min_value=1)
    
    if db: st.success("🟢 Online")
    else: st.error("🔴 Offline")

df = get_data()

# --- PAGE 1: DASHBOARD ---
if page == "📊 Dashboard":
    st.title("Executive Dashboard")
    
    if not df.empty:
        # 1. Reading Challenge Tracker
        read_count = len(df[df['Status'] == 'Read'])
        progress = min(read_count / goal, 1.0)
        
        st.write(f"**Yearly Goal:** {read_count} of {goal} books completed")
        st.progress(progress)
        if progress >= 1.0:
            st.balloons()
        
        st.divider()

        # 2. Key Metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Assets", len(df))
        c2.metric("Reading", len(df[df['Status'] == 'Reading']))
        c3.metric("To Read", len(df[df['Status'] == 'To Read']))
        
        # Calculate Avg Rating safely
        if 'Rating' in df.columns:
            avg = pd.to_numeric(df['Rating'], errors='coerce').fillna(0).mean()
            c4.metric("Quality Score", f"{avg:.1f} / 5.0")
            
        st.divider()
        
        # 3. Visual Spotlight (Auto-Fetch Covers)
        st.subheader("📖 Active Reads")
        current_books = df[df['Status'] == 'Reading']
        
        if not current_books.empty:
            cols = st.columns(5) # Grid layout
            for idx, row in current_books.iterrows():
                with cols[idx % 5]:
                    # Use cover from DB or fetch fallback
                    cover_url = row.get('Cover')
                    if not cover_url or pd.isna(cover_url):
                        # Attempt live fetch if missing (optional, can be slow)
                        meta = fetch_book_metadata(f"{row['Title']} {row['Author']}")
                        cover_url = meta['Cover'] if meta else "https://via.placeholder.com/150x220?text=No+Cover"
                    
                    st.image(cover_url, width=120)
                    st.caption(f"**{row['Title']}**")
        else:
            st.info("No active books. Go to Inventory to start one!")

# --- PAGE 2: INVENTORY (Two-Way Sync) ---
elif page == "📚 Inventory (Sync)":
    st.title("Master Inventory")
    
    if df.empty:
        st.warning("Library is empty.")
    else:
        st.caption("⚡ Edit 'Status' or 'Rating' directly in the grid, then click 'Save Changes'.")
        
        # Search
        search = st.text_input("🔍 Filter", "")
        if search:
            view_df = df[df['Title'].str.contains(search, case=False) | df['Author'].str.contains(search, case=False)]
        else:
            view_df = df

        # Editable Grid
        edited_df = st.data_editor(
            view_df,
            column_config={
                "Cover": st.column_config.ImageColumn("Cover", width="small"),
                "Rating": st.column_config.NumberColumn("Rating", min_value=0, max_value=5, format="%d ⭐"),
                "Status": st.column_config.SelectboxColumn("Status", options=["To Read", "Reading", "Read", "DNF"]),
                "id": None # Hide ID
            },
            use_container_width=True,
            hide_index=True,
            key="data_editor",
            num_rows="fixed" 
        )
        
        # Save Button triggers the Sync Logic
        if st.button("💾 Save Changes to Cloud"):
            save_changes_to_db(df, edited_df)

# --- PAGE 3: ADD BOOK (Auto-Fill) ---
elif page == "➕ Add (Auto-Fill)":
    st.title("Acquire New Book")
    
    # Initialize session state for form values if not exists
    if 'form_title' not in st.session_state: st.session_state.form_title = ""
    if 'form_author' not in st.session_state: st.session_state.form_author = ""
    if 'form_year' not in st.session_state: st.session_state.form_year = 2024
    if 'form_cover' not in st.session_state: st.session_state.form_cover = ""
    
    # 1. Search Bar for Auto-Fill
    with st.container(border=True):
        st.subheader("🤖 AI Auto-Fill")
        col_search, col_btn = st.columns([3, 1])
        search_query = col_search.text_input("Enter ISBN or Book Title to search metadata", placeholder="e.g. The Laws of Trading")
        
        if col_btn.button("🔍 Search & Fill"):
            with st.spinner("Querying Google Books..."):
                meta = fetch_book_metadata(search_query)
                if meta:
                    st.session_state.form_title = meta['Title']
                    st.session_state.form_author = meta['Author']
                    st.session_state.form_year = meta['Year']
                    st.session_state.form_cover = meta.get('Cover', "")
                    st.success("Metadata found! Form updated below.")
                else:
                    st.error("Book not found. Please enter manually.")

    # 2. The Form
    with st.form("add_book_form"):
        st.subheader("Book Details")
        c1, c2 = st.columns([1, 2])
        
        # Show cover preview if available
        if st.session_state.form_cover:
            c1.image(st.session_state.form_cover, width=100)
        
        with c2:
            title = st.text_input("Title", value=st.session_state.form_title)
            author = st.text_input("Author", value=st.session_state.form_author)
        
        c3, c4, c5 = st.columns(3)
        genre = c3.selectbox("Genre", ["Finance", "Sci-Fi", "Tech", "Fiction", "Biography", "Self-Help"])
        year = c4.number_input("Year", value=st.session_state.form_year)
        status = c5.selectbox("Status", ["To Read", "Reading", "Read"])
        
        # Hidden inputs to pass state
        cover_input = st.text_input("Cover URL (Hidden)", value=st.session_state.form_cover, type="password") 
        
        if st.form_submit_button("Add to Library"):
            new_book = {
                "Title": title,
                "Author": author,
                "Genre": genre,
                "Year": year,
                "Status": status,
                "Rating": 0,
                "Cover": st.session_state.form_cover, # Use the session state cover
                "Created_At": firestore.SERVER_TIMESTAMP,
                "id": str(uuid.uuid4())
            }
            if db:
                db.collection('books').add(new_book)
                st.success("Book Added!")
                # Clear state
                for key in ['form_title', 'form_author', 'form_cover']:
                    st.session_state[key] = ""
                st.rerun()

# --- PAGE 4: ANALYTICS ---
elif page == "📈 Analytics":
    st.title("Knowledge Analytics")
    
    if not df.empty:
        # Advanced Chart: ROI / Distribution
        fig = px.sunburst(df, path=['Genre', 'Status'], title="Library Distribution")
        st.plotly_chart(fig, use_container_width=True)
        
        # Scatter: Year vs Rating
        if 'Rating' in df.columns:
            df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce')
            fig2 = px.scatter(df, x="Year", y="Rating", color="Genre", size="Rating", hover_data=['Title'], title="Rating by Era & Genre")
            st.plotly_chart(fig2, use_container_width=True)