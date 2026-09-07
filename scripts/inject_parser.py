with open('migrate_v2.py', 'r', encoding='utf-8') as f:
    text = f.read()

def_find_knum = """
import re
def get_k_num(kyoku_name):
    match = re.search(r'([1-4１-４])', kyoku_name)
    if match:
        num = match.group(1).translate(str.maketrans('１２３４', '1234'))
        return int(num)
    return 1
"""

text = def_find_knum + text
text = text.replace("k_num = int(kyoku[1]) if len(kyoku)>=3 and kyoku[1].isdigit() else 1", "k_num = get_k_num(kyoku)")
text = text.replace("k_num = int(ro['kyoku_name'][1]) if len(ro['kyoku_name'])>=3 and ro['kyoku_name'][1].isdigit() else 1", "k_num = get_k_num(ro['kyoku_name'])")

with open('migrate_v2.py', 'w', encoding='utf-8') as f:
    f.write(text)
