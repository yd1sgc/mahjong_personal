with open('migrate_v2.py', 'r', encoding='utf-8') as f:
    text = f.read()
text = text.replace("rule_cfg = g['rule_config'] if g['rule_config'] else '{}'", "rule_cfg = g['applied_rule_json'] if g['applied_rule_json'] else '{}'")
text = text.replace("g['rule_name']", "g['rule_name_snapshot']")
with open('migrate_v2.py', 'w', encoding='utf-8') as f:
    f.write(text)
