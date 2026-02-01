import streamlit as st
import pandas as pd
import plotly.express as px
import firebase_admin
from firebase_admin import credentials, firestore
import uuid
import json
import ast 

# --- CONFIGURATION & SETUP ---
st.set_page_config(page_title="My Library", page_icon="📚", layout="wide")

# --- FIREBASE CONNECTION HANDLER (SMART PARSE) ---
@st.cache_resource
def init_firebase():
    """
    Initializes Firebase. 
    Strictly checks for 'firebase_key.json' (Local) or Streamlit Secrets (Cloud).
    Uses 'Smart Parse' to handle formatting issues in Secrets.
    """
    # Check if app is already initialized
    if not firebase_admin._apps:
        try:
            # 1. Try loading from Streamlit Cloud Secrets
            if "firebase" in st.secrets:
                key_content = st.secrets["firebase"]["textkey"]
                
                # --- SMART PARSING BLOCK ---
                try:
                    # Attempt A: Standard JSON parse
                    key_dict = json.loads(key_content)
                except ValueError:
                    try:
                        # Attempt B: Loose Mode (fixes newlines)
                        key_dict = json.loads(key_content, strict=False)
                    except ValueError:
                        # Attempt C: Python Dict Fallback
                        try:
                            key_dict = ast.literal_eval(key_content)
                        except:
                            raise ValueError("Could not parse the Secrets key.")
                # ---------------------------

                cred = credentials.Certificate(key_dict)
                firebase_admin.initialize_app(cred)
            
            # 2. Local fallback (for local development)
            else:
                cred = credentials.Certificate("firebase_key.json")
                firebase_admin.initialize_app(cred)
                
        except Exception as e:
            st.error(f"❌ Database connection failed: {e}")
            return None
    
    return firestore.client()

db = init_firebase()

# --- DATA FUNCTIONS ---

def get_data():
    """Fetches real data from Firebase."""
    if not db:
        return pd.DataFrame()
        
    try:
        docs = db.collection('books').stream()
        items = [{"id": doc.id, **doc.to_dict()} for doc in docs]
        
        if items:
            return pd.DataFrame(items)
        else:
            # Return empty structure if DB is empty
            return pd.DataFrame(columns=["Title", "Author", "Genre", "Status", "Rating", "Year"])
            
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return pd.DataFrame()

def add_book_to_db(data):
    """Adds a new book to the Firestore database."""
    if not db:
        st.error("Not connected to database.")
        return False
        
    try:
        db.collection('books').add(data)
        return True
    except Exception as e:
        st.error(f"Error saving to database: {e}")
        return False

def update_book_status(book_id, new_status, new_rating):
    """Updates specific fields in Firestore."""
    if db:
        doc_ref = db.collection('books').document(book_id)
        doc_ref.update({
            'Status': new_status,
            'Rating': new_rating
        })

# --- UI LAYOUT ---

# Sidebar Navigation
with st.sidebar:
    st.header("Library OS")
    page = st.radio("Navigation", ["📊 Dashboard", "📚 Inventory", "➕ Add Book", "📈 Analytics"])
    st.divider()
    if db:
        st.success("🟢 Online")
    else:
        st.error("🔴 Offline")

# Load Data
df = get_data()

# --- PAGE 1: DASHBOARD ---
if page == "📊 Dashboard":
    st.title("Library Dashboard")
    
    if df.empty:
        st.info("Your library is empty! Go to 'Add Book' to get started.")
    else:
        # Top Metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Books", len(df))
        with col2:
            read_count = len(df[df['Status'] == 'Read'])
            st.metric("Books Read", read_count)
        with col3:
            toread_count = len(df[df['Status'] == 'To Read'])
            st.metric("To Read Queue", toread_count)
        with col4:
            # Handle case where rating might be NaN or string
            valid_ratings = df[pd.to_numeric(df['Rating'], errors='coerce') > 0]
            if not valid_ratings.empty:
                avg_rating = valid_ratings['Rating'].mean()
                st.metric("Avg Rating", f"{avg_rating:.1f} ⭐")
            else:
                st.metric("Avg Rating", "-")

        st.divider()
        
        # Spotlight Section
        c1, c2 = st.columns([2, 1])
        with c1:
            st.subheader("📖 Currently Reading")
            current = df[df['Status'] == 'Reading']
            if not current.empty:
                for _, row in current.iterrows():
                    st.info(f"**{row['Title']}** by {row['Author']} ({row['Genre']})")
            else:
                st.write("You are not reading anything right now.")
                
        with c2:
            st.subheader("🔥 Top Rated")
            if 'Rating' in df.columns:
                # Ensure Rating is numeric for sorting
                df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce').fillna(0)
                top_rated = df.sort_values(by='Rating', ascending=False).head(5)
                st.dataframe(
                    top_rated[['Title', 'Rating']], 
                    hide_index=True,
                    column_config={"Rating": st.column_config.NumberColumn(format="%d ⭐")}
                )

# --- PAGE 2: INVENTORY ---
elif page == "📚 Inventory":
    st.title("Library Inventory")
    
    if df.empty:
        st.warning("No books found.")
    else:
        # Search / Filter
        search_term = st.text_input("🔍 Search by Title or Author", "")
        
        # Filter Logic
        if search_term:
            filtered_df = df[df['Title'].str.contains(search_term, case=False) | df['Author'].str.contains(search_term, case=False)]
        else:
            filtered_df = df

        # Editable Dataframe
        edited_df = st.data_editor(
            filtered_df,
            column_config={
                "Rating": st.column_config.NumberColumn(
                    "Rating",
                    help="Stars 1-5",
                    min_value=0,
                    max_value=5,
                    step=1,
                    format="%d ⭐",
                ),
                "Status": st.column_config.SelectboxColumn(
                    "Status",
                    options=["Read", "Reading", "To Read", "DNF"],
                    required=True,
                ),
                # Hide internal ID
                "id": None 
            },
            hide_index=True,
            use_container_width=True,
            key="inventory_editor"
        )
        
        # NOTE: Streamlit data_editor does not automatically sync back to Firebase.
        # You would need a "Save Changes" button or session state comparison logic to update 
        # the DB based on 'edited_df'. That is advanced logic. 
        # For now, this view allows you to VIEW and SORT locally.

# --- PAGE 3: ADD BOOK ---
elif page == "➕ Add Book":
    st.title("Add New Entry")
    
    with st.form("add_book_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        title = c1.text_input("Book Title")
        author = c2.text_input("Author")
        
        c3, c4, c5 = st.columns(3)
        genre = c3.selectbox("Genre", ["Fiction", "Non-Fiction", "Sci-Fi", "Tech", "Finance", "Biography", "Self-Help"])
        year = c4.number_input("Year Published", min_value=1900, max_value=2030, step=1, value=2024)
        status = c5.selectbox("Status", ["To Read", "Reading", "Read"])
        
        rating = st.slider("Rating", 0, 5, 0)
        
        submitted = st.form_submit_button("Add to Library")
        
        if submitted:
            if title and author:
                new_book = {
                    "Title": title,
                    "Author": author,
                    "Genre": genre,
                    "Year": int(year),
                    "Status": status,
                    "Rating": int(rating),
                    "Created_At": firestore.SERVER_TIMESTAMP
                }
                
                success = add_book_to_db(new_book)
                
                if success:
                    st.success(f"Added '{title}' to your library!")
                    st.rerun() 
            else:
                st.warning("Please enter at least a Title and Author.")

# --- PAGE 4: ANALYTICS ---
elif page == "📈 Analytics":
    st.title("Reading Insights")
    
    if not df.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Genre Distribution")
            fig_pie = px.pie(df, names='Genre', title='Books by Genre', hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)
            
        with col2:
            st.subheader("Reading Status")
            status_counts = df['Status'].value_counts().reset_index()
            status_counts.columns = ['Status', 'Count']
            fig_bar = px.bar(status_counts, x='Status', y='Count', color='Status', title="Current Library Status")
            st.plotly_chart(fig_bar, use_container_width=True)
            
        st.subheader("Publication Timeline")
        fig_hist = px.histogram(df, x="Year", nbins=20, title="Books by Publication Year")
        st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.info("No data available for analytics.")