import json
d = json.load(open('game_257_data.json', encoding='utf-8'))
rounds = {r['round_id']: r for r in d['rounds']}
by_round = {}
for s in d['round_seats']:
    by_round.setdefault(s['round_id'], []).append(s)

sorted_rounds = sorted(d['rounds'], key=lambda x: (x['round_index'], x['kyoku_name']))
print('--- Oya Analysis ---')
for r in sorted_rounds:
    rs = by_round[r['round_id']]
    result = r['result_type']
    oya = 'Unknown'
    if result == 'tsumo':
        winner = next(s for s in rs if s['is_winner'])
        losers = [s for s in rs if s['base_point'] < 0]
        if losers:
            min_pay = min(s['base_point'] for s in losers) # more negative means pays more
            oyas = [s['seat'] for s in losers if s['base_point'] == min_pay]
            if len(oyas) == 1:
                oya = oyas[0]
            elif all(s['base_point'] == losers[0]['base_point'] for s in losers):
                oya = winner['seat']
        print(f"{r['kyoku_name']}: Oya={oya} (Tsumo, Winner S{winner['seat']})")
    elif result == 'ron':
        winner = next(s for s in rs if s['is_winner'])
        base = winner['base_point']
        is_oya = base in [1500,2400,2900,3900,4800,5800,7700,9600,11600,12000,18000,24000]
        is_child = base in [1000,1300,1600,2000,2600,3200,3900,5200,6400,8000,12000,16000]
        guess = f"Oya (S{winner['seat']})" if is_oya and not is_child else ("Child" if is_child and not is_oya else "Ambiguous")
        if base == 3900: guess = "Ambiguous (Oya 3900 or Child 3900)"
        if base == 12000: guess = "Ambiguous (Oya 12000 or Child 12000)"
        print(f"{r['kyoku_name']}: Winner S{winner['seat']} got {base} -> Score type: {guess}")
    elif result == 'ryukyoku':
        print(f"{r['kyoku_name']}: Ryukyoku")
