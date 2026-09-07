import sqlite3
import pandas as pd

conn = sqlite3.connect('local_mahjong_v2.db')
tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

for t in tables:
    df = pd.read_sql(f"SELECT * FROM {t}", conn)
    null_cols = [c for c in df.columns if df[c].isnull().any()]
    if null_cols:
        print(f"Table {t} has NULLs in: {null_cols}")
