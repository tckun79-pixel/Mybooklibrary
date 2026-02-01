import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import uuid

# --- CONFIGURATION & SETUP ---
st.set_page_config(page_title="My Library", page_icon="📚", layout="wide")

# TOGGLE THIS TO FALSE TO CONNECT TO REAL FIREBASE
# Keep as TRUE to test the UI without needing keys immediately
DEMO_MODE = True 

import json
import ast # Import ast for safer Python literal evaluation

def init_firebase():
    """
    Initializes Firebase with 'Smart Parsing' to auto-correct 
    common JSON formatting issues in Streamlit Secrets.
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
                        # Attempt B: Loose Mode (fixes "Invalid control character" / newlines)
                        # strict=False allows control characters inside strings
                        key_dict = json.loads(key_content, strict=False)
                    except ValueError:
                        # Attempt C: Python Dict Fallback
                        # Useful if you accidentally copied a Python dict (with single quotes) 
                        # instead of strict JSON (double quotes).
                        try:
                            key_dict = ast.literal_eval(key_content)
                        except:
                            # If all fail, raise the original error to show the user
                            raise ValueError("Could not parse the Secrets key. Please check the format.")
                # ---------------------------

                cred = credentials.Certificate(key_dict)
                firebase_admin.initialize_app(cred)
            
            # 2. Local fallback (for when you run 'streamlit run' on your PC)
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
    """Fetches data from Firebase or generates Mock Data."""
    if DEMO_MODE:
        # Generate robust mock data if in demo mode
        if 'mock_data' not in st.session_state:
            st.session_state.mock_data = pd.DataFrame([
                {"id": "1", "Title": "The Laws of Trading", "Author": "Agustin Lebron", "Genre": "Finance", "Status": "Read", "Rating": 5, "Year": 2019},
                {"id": "2", "Title": "Dune", "Author": "Frank Herbert", "Genre": "Sci-Fi", "Status": "Read", "Rating": 5, "Year": 1965},
                {"id": "3", "Title": "Atomic Habits", "Author": "James Clear", "Genre": "Self-Help", "Status": "Reading", "Rating": 4, "Year": 2018},
                {"id": "4", "Title": "Project Hail Mary", "Author": "Andy Weir", "Genre": "Sci-Fi", "Status": "To Read", "Rating": 0, "Year": 2021},
                {"id": "5", "Title": "Clean Code", "Author": "Robert C. Martin", "Genre": "Tech", "Status": "Read", "Rating": 4, "Year": 2008},
                {"id": "6", "Title": "Thinking, Fast and Slow", "Author": "Daniel Kahneman", "Genre": "Psychology", "Status": "Reading", "Rating": 0, "Year": 2011},
                {"id": "7", "Title": "Zero to One", "Author": "Peter Thiel", "Genre": "Business", "Status": "Read", "Rating": 3, "Year": 2014},
            ])
        return st.session_state.mock_data
    else:
        # Real Firebase Fetch
        if db:
            docs = db.collection('books').stream()
            items = [{"id": doc.id, **doc.to_dict()} for doc in docs]
            if items:
                return pd.DataFrame(items)
            else:
                return pd.DataFrame(columns=["Title", "Author", "Genre", "Status", "Rating", "Year"])
        return pd.DataFrame()

def add_book_to_db(data):
    """Adds a new book to the database."""
    if DEMO_MODE:
        new_row = pd.DataFrame([data])
        st.session_state.mock_data = pd.concat([st.session_state.mock_data, new_row], ignore_index=True)
        return True
    else:
        if db:
            db.collection('books').add(data)
            return True
        return False

# --- UI LAYOUT ---

# Sidebar Navigation
with st.sidebar:
    st.header("Library OS 2.0")
    page = st.radio("Navigation", ["📊 Dashboard", "📚 Inventory", "➕ Add Book", "📈 Analytics"])
    st.divider()
    if DEMO_MODE:
        st.warning("⚠️ Demo Mode Active. Data is not saved to cloud.")
    else:
        st.success("🟢 Connected to Firebase")

# Load Data
df = get_data()

# --- PAGE 1: DASHBOARD ---
if page == "📊 Dashboard":
    st.title("Welcome back! 👋")
    
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
        avg_rating = df[df['Rating'] > 0]['Rating'].mean()
        st.metric("Avg Rating", f"{avg_rating:.1f} ⭐")

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
            st.write("You are not reading anything right now. Pick a book!")
            
    with c2:
        st.subheader("🔥 Top Rated")
        top_rated = df.sort_values(by='Rating', ascending=False).head(3)
        st.dataframe(top_rated[['Title', 'Rating']], hide_index=True)

# --- PAGE 2: INVENTORY ---
elif page == "📚 Inventory":
    st.title("Library Inventory")
    
    # Search / Filter
    search_term = st.text_input("🔍 Search by Title or Author", "")
    
    # Filter Logic
    if search_term:
        filtered_df = df[df['Title'].str.contains(search_term, case=False) | df['Author'].str.contains(search_term, case=False)]
    else:
        filtered_df = df

    # Editable Dataframe
    # Note: Full 2-way sync with Firebase via st.data_editor requires extra logic (listening to callbacks).
    # For this version, we display the grid.
    st.data_editor(
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
            )
        },
        hide_index=True,
        use_container_width=True
    )

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
                    "Year": year,
                    "Status": status,
                    "Rating": rating,
                    "id": str(uuid.uuid4()) # Unique ID for Firebase
                }
                
                success = add_book_to_db(new_book)
                
                if success:
                    st.success(f"Added '{title}' to your library!")
                    # Rerun to update the dataframe immediately
                    st.rerun() 
                else:
                    st.error("Failed to connect to Database.")
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
        st.info("Add some books to see analytics!")