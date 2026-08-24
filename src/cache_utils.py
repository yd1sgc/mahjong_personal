import streamlit as st
import database2 as db

@st.cache_data(ttl=300)
def get_games_data(year_filter=None):
    return db.get_games_data(year_filter)

@st.cache_data(ttl=300)
def get_rounds_data():
    return db.get_rounds_data()

@st.cache_data(ttl=300)
def load_rounds_by_game(game_id):
    return db.load_rounds_by_game(game_id)

@st.cache_data(ttl=300)
def get_rule_templates(include_archived=False):
    return db.get_rule_templates(include_archived)

@st.cache_data(ttl=300)
def get_groups():
    return db.get_groups()

@st.cache_data(ttl=300)
def get_all_members():
    return db.get_all_members()
