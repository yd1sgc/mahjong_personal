import sqlite3
import pandas as pd
conn = sqlite3.connect(r'C:\Users\segu1\OneDrive\mahjong_personal\mahjong_local.db')
print("Tables:")
print(pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", conn))
print("\nGames columns:")
print(pd.read_sql("PRAGMA table_info(games)", conn))
try:
    print("\ngame_participants:")
    print(pd.read_sql("SELECT * FROM game_participants LIMIT 1", conn))
except Exception as e:
    print(e)
