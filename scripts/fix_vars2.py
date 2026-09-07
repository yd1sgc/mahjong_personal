with open('migrate_v2.py', 'r', encoding='utf-8') as f:
    text = f.read()
text = text.replace("p['point']", "0.0")
with open('migrate_v2.py', 'w', encoding='utf-8') as f:
    f.write(text)
