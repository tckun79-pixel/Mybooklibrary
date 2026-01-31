import streamlit as st
import pandas as pd
import plotly.express as px
import firebase_admin
from firebase_admin import credentials, firestore

# --- Page Configuration ---
st.set_page_config(page_title="Cloud Library", page_icon="☁️", layout="wide")

# ==========================================
# 🔐 AUTHENTICATION BLOCK (Added)
# ==========================================
def check_password():
    """Returns `True` if the user had the correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == st.secrets["auth"]["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store the password
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    st.text_input(
        "🔐 Please enter the password to access the library:", 
        type="password", 
        on_change=password_entered, 
        key="password"
    )
    
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("😕 Password incorrect")
        
    return False

# Stop execution if password is not correct
if not check_password():
    st.stop()

# ==========================================
# 🔥 FIREBASE CONNECTION
# ==========================================
# Check if firebase app is already initialized to avoid errors on refresh
if not firebase_admin._apps:
    # Load credentials from Streamlit Secrets
    # Make sure your secrets.toml on Streamlit Cloud has a [firebase] section!
    key_dict = st.secrets["firebase"]
    cred = credentials.Certificate(key_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- Helper Functions ---

def load_data():
    """Fetches data from Firestore and returns a DataFrame"""
    # Note: Stream uses a generator, list comprehension converts it
    docs = db.collection('books').stream()
    data = [doc.to_dict() for doc in docs]
    
    if data:
        return pd.DataFrame(data)
    else:
        return pd.DataFrame(columns=["Title", "Author", "Genre", "Year", "Status", "Rating"])

def add_book_to_db(title, author, genre, year, status, rating):
    """Adds a new book to Firestore"""
    doc_ref = db.collection('books').document()
    doc_ref.set({
        "Title": title,
        "Author": author,
        "Genre": genre,
        "Year": int(year),
        "Status": status,
        "Rating": int(rating),
        "Created_At": firestore.SERVER_TIMESTAMP
    })

# --- Sidebar Navigation ---
st.sidebar.title("☁️ Cloud Library")
page = st.sidebar.radio("Navigate", ["Dashboard", "Inventory", "Add New Book", "Analytics"])

# --- PAGE 1: DASHBOARD ---
if page == "Dashboard":
    st.title("📊 Dashboard Overview")
    # Add a refresh button to manually fetch new data
    if st.button("Refresh Data"):
        st.cache_data.clear()
        
    df = load_data()

    if not df.empty:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Books", len(df))
        col2.metric("Books Read", len(df[df['Status'] == 'Completed']))
        col3.metric("Currently Reading", len(df[df['Status'] == 'Reading']))
        col4.metric("To Read", len(df[df['Status'] == 'To Read']))

        st.markdown("---")
        
        col_left, col_right = st.columns([2, 1])
        with col_left:
            st.subheader("📖 Currently Reading")
            reading = df[df['Status'] == 'Reading']
            if not reading.empty:
                st.dataframe(reading[['Title', 'Author', 'Genre']], use_container_width=True, hide_index=True)
            else:
                st.info("No active books.")
        
        with col_right:
            st.subheader("🏆 Top Rated")
            top = df[df['Rating'] == 5]
            if not top.empty:
                st.dataframe(top[['Title']], use_container_width=True, hide_index=True)
    else:
        st.warning("Library is empty. Go to 'Add New Book' to start!")

# --- PAGE 2: INVENTORY ---
elif page == "Inventory":
    st.title("📚 Book Inventory")
    df = load_data()
    
    if not df.empty:
        col1, col2 = st.columns(2)
        search_term = col1.text_input("🔍 Search")
        filter_genre = col2.multiselect("Filter Genre", options=df['Genre'].unique())

        if search_term:
            df = df[df['Title'].str.contains(search_term, case=False) | df['Author'].str.contains(search_term, case=False)]
        if filter_genre:
            df = df[df['Genre'].isin(filter_genre)]

        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No books found.")

# --- PAGE 3: ADD NEW BOOK ---
elif page == "Add New Book":
    st.title("➕ Add to Cloud Database")
    
    with st.form("add_book_form"):
        col1, col2 = st.columns(2)
        title = col1.text_input("Book Title")
        author = col2.text_input("Author")
        
        col3, col4, col5 = st.columns(3)
        genre = col3.selectbox("Genre", ["Fiction", "Non-Fiction", "Sci-Fi", "Mystery", "Self-Help", "Tech"])
        year = col4.number_input("Year", 2000, 2030, 2025)
        status = col5.selectbox("Status", ["To Read", "Reading", "Completed"])
        rating = st.slider("Rating", 0, 5, 0)
        
        submitted = st.form_submit_button("Save to Firebase")
        
        if submitted:
            if title and author:
                add_book_to_db(title, author, genre, year, status, rating)
                st.success(f"Saved '{title}' to the cloud!")
            else:
                st.error("Title and Author are required.")

# --- PAGE 4: ANALYTICS ---
elif page == "Analytics":
    st.title("📈 Analytics")
    df = load_data()
    
    if not df.empty:
        col1, col2 = st.columns(2)
        with col1:
            fig = px.pie(df, names='Genre', title='Genre Distribution')
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig2 = px.bar(df, x='Status', color='Status', title='Reading Status')
            st.plotly_chart(fig2, use_container_width=True)