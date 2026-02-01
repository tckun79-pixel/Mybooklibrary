import json # Add this import at the top if missing

def init_firebase():
    """Initializes Firebase connection using Streamlit Secrets."""
    if DEMO_MODE:
        return None

    # Check if app is already initialized
    if not firebase_admin._apps:
        try:
            # Try loading from Streamlit Cloud Secrets first
            if "firebase" in st.secrets:
                key_dict = json.loads(st.secrets["firebase"]["textkey"])
                cred = credentials.Certificate(key_dict)
                firebase_admin.initialize_app(cred)

            # Fallback to local file for testing on your machine
            else:
                cred = credentials.Certificate("firebase_key.json")
                firebase_admin.initialize_app(cred)

        except Exception as e:
            st.error(f"❌ Database connection failed: {e}")
            return None

    return firestore.client()