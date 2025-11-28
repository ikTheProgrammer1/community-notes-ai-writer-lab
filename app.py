import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import time

# --- Step 1: Configuration & Styling (The "Terminal" Vibe) ---
st.set_page_config(layout="wide", page_title="⚔️ War Room")

# Force Dark Mode and Cyberpunk/Terminal Aesthetic
st.markdown("""
    <style>
    /* Main Background */
    .stApp {
        background-color: #050505;
        color: #00ff41; /* Terminal Green */
        font-family: 'Courier New', Courier, monospace;
    }
    
    /* Inputs (Text Input, Text Area) */
    .stTextInput input, .stTextArea textarea {
        background-color: #000000 !important;
        color: #00ff41 !important;
        border: 1px solid #00ff41 !important;
        border-radius: 0px !important;
        font-family: 'Courier New', Courier, monospace !important;
    }
    .stTextInput input:focus, .stTextArea textarea:focus {
        border: 1px solid #ffffff !important;
        box-shadow: 0 0 10px #00ff41 !important;
    }
    
    /* Buttons */
    .stButton button {
        border: 1px solid #00ff41 !important;
        border-radius: 0px !important;
        color: #00ff41 !important;
        background-color: #000000 !important;
        font-family: 'Courier New', Courier, monospace !important;
        text-transform: uppercase !important;
        font-weight: bold !important;
        transition: all 0.2s ease-in-out;
    }
    .stButton button:hover {
        background-color: #00ff41 !important;
        color: #000000 !important;
        box-shadow: 0 0 15px #00ff41;
    }
    
    /* Metrics */
    div[data-testid="stMetricValue"] {
        font-family: 'Courier New', Courier, monospace;
        font-weight: bold;
        color: #00ff41;
        text-shadow: 0 0 5px #00ff41;
    }
    div[data-testid="stMetricLabel"] {
        color: #00aa2c;
    }
    
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #0a0a0a;
        border-right: 1px solid #333;
    }
    
    /* Headers */
    h1, h2, h3 {
        color: #e6edf3 !important;
        font-family: 'Courier New', Courier, monospace !important;
        text-transform: uppercase;
        letter-spacing: 2px;
    }
    
    /* Dataframe */
    div[data-testid="stDataFrame"] {
        border: 1px solid #333;
    }
    
    /* Custom Classes */
    .cyber-box {
        border: 1px solid #00ff41;
        padding: 10px;
        margin-bottom: 10px;
        background-color: #0a0a0a;
    }
    .status-pass { color: #00ff41; font-weight: bold; }
    .status-fail { color: #ff0055; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# Initialize Session State
if 'target_url' not in st.session_state:
    st.session_state.target_url = ""
if 'admission_status' not in st.session_state:
    st.session_state.admission_status = "idle" # idle, checking, results
if 'admission_scores' not in st.session_state:
    st.session_state.admission_scores = {}

# --- Step 2: The "Setup" Sidebar (Configuration) ---
with st.sidebar:
    st.title("Target Parameters")
    my_candidate = st.text_input("My Candidate", value="@SenatorSmith")
    opponent = st.text_input("The Opponent", value="@SenatorJones")
    key_topics = st.multiselect("Key Topics", ["Inflation", "Border", "Taxes", "Healthcare"], default=["Inflation", "Border"])
    
    st.divider()
    st.markdown("**SYSTEM STATUS**")
    st.markdown("🟢 ONLINE")
    st.markdown("**THREAT LEVEL**")
    st.markdown("🔴 CRITICAL")

# --- Step 3: The "Shield" Pane (Top Row - FUD Metrics) ---
st.title("⚔️ War Room // Threat Intelligence")
st.markdown("---")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(label="📉 Reach Suppressed", value="2.4M", delta="-15%", delta_color="inverse")

with col2:
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = 85,
        title = {'text': "Account Suspension Risk"},
        gauge = {
            'axis': {'range': [None, 100], 'tickwidth': 1, 'tickcolor': "white"},
            'bar': {'color': "#ff0055"}, # Cyberpunk Red
            'bgcolor': "black",
            'borderwidth': 2,
            'bordercolor': "#333",
            'steps': [
                {'range': [0, 50], 'color': '#003300'},
                {'range': [50, 80], 'color': '#333300'},
                {'range': [80, 100], 'color': '#330000'}],
            'threshold': {
                'line': {'color': "white", 'width': 4},
                'thickness': 0.75,
                'value': 85}}))
    fig.update_layout(height=200, margin=dict(l=20, r=20, t=50, b=20), paper_bgcolor="rgba(0,0,0,0)", font={'color': "white", 'family': "Courier New"})
    st.plotly_chart(fig, use_container_width=True)

with col3:
    st.metric(label="🛡️ Narrative Control", value="12%", delta="-8%", delta_color="inverse")

st.markdown("---")

# --- Step 4 & 5: Battlefield & Weapon Panes ---
cols = st.columns([2, 1])

# Mock Data for Feed
mock_data = pd.DataFrame({
    "Tweet Text": [
        "Senator Smith voted to increase taxes on working families! #Inflation",
        "The border crisis is out of control thanks to Smith's policies.",
        "Smith's healthcare plan will bankrupt the state. Read the fine print!",
        "Another scandal? Smith needs to resign immediately."
    ],
    "Views": ["1.2M", "850K", "420K", "150K"],
    "Status": ["Unchallenged ❌", "Unchallenged ❌", "Addressed ✅", "Unchallenged ❌"],
    "URL": [
        "https://x.com/SenatorJones/status/1234567890",
        "https://x.com/SenatorJones/status/1234567891",
        "https://x.com/SenatorJones/status/1234567892",
        "https://x.com/SenatorJones/status/1234567893"
    ]
})

with cols[0]:
    st.subheader("🔥 Active Threats")
    
    # Create the Dataframe with a selection event
    event = st.dataframe(
        mock_data,
        on_select="rerun",  # Rerun the app when clicked
        selection_mode="single-row",
        hide_index=True,
        use_container_width=True
    )

    # Handle the Selection
    if len(event.selection.rows) > 0:
        row_idx = event.selection.rows[0]
        selected_url = mock_data.iloc[row_idx]["URL"]
        
        # Only update if changed to avoid loops
        if st.session_state.target_url != selected_url:
            st.session_state.target_url = selected_url
            st.session_state.admission_status = "idle" # Reset status on new target
            st.rerun()

with cols[1]:
    st.subheader("Tactical Response")
    
    # --- Step 5: The "Weapon" Pane ---
    # Input linked to session state
    target_url = st.text_input("Target URL", value=st.session_state.target_url, key="url_input")
    
    # Update session state if user types manually
    if target_url != st.session_state.target_url:
        st.session_state.target_url = target_url
    
    draft_text = st.text_area("Draft Counter-Note", height=150, placeholder="Draft your Community Note here...")
    
    col_a, col_b = st.columns(2)
    
    # Admission Engine Logic
    if st.session_state.admission_status == "idle":
        if col_a.button("CHECK ADMISSION", type="primary", use_container_width=True):
            if not draft_text:
                st.error("Enter draft text first.")
            else:
                st.session_state.admission_status = "checking"
                st.rerun()
                
    elif st.session_state.admission_status == "checking":
        with st.spinner("ANALYZING ADMISSION VECTORS..."):
            time.sleep(1.5) # Simulate API latency
            # Mock Scores
            st.session_state.admission_scores = {
                "UrlValidity": 0.98,
                "HarassmentAbuse": 0.99,
                "ClaimOpinion": 0.45 # Fail
            }
            st.session_state.admission_status = "results"
            st.rerun()
            
    elif st.session_state.admission_status == "results":
        scores = st.session_state.admission_scores
        
        st.markdown("### 🛡️ ADMISSION REPORT")
        
        # Scorecard
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("URL", f"{scores['UrlValidity']*100:.0f}%")
        sc2.metric("TOXICITY", f"{scores['HarassmentAbuse']*100:.0f}%")
        sc3.metric("CLAIM", f"{scores['ClaimOpinion']*100:.0f}%", delta="-FAIL", delta_color="inverse")
        
        st.error("❌ ADMISSION DENIED: Claim Opinion Score too low.")
        
        if st.button("🔄 AUTO-FIX (AI)", use_container_width=True):
            st.info("AI Refactoring initiated...")
            # Here we would call the Fixer
            
        if st.button("RESET", use_container_width=True):
            st.session_state.admission_status = "idle"
            st.rerun()

    # Deploy Button (Always visible but maybe disabled)
    if col_b.button("DEPLOY", use_container_width=True, disabled=(st.session_state.admission_status != "passed")):
        st.success("NOTE DEPLOYED TO NETWORK.")
