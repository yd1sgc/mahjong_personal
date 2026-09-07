import json
d = json.load(open('game_257_data.json', encoding='utf-8'))
rounds = {r['round_id']: r for r in d['rounds']}
seats = d['round_seats']
by_round = {}
for s in seats:
    by_round.setdefault(s['round_id'], []).append(s)

sorted_rounds = sorted(d['rounds'], key=lambda x: (x['round_index'], x['kyoku_name']))
print('--- Round Summary ---')
current_scores = {1:25000, 2:25000, 3:25000, 4:25000}
for i, r in enumerate(sorted_rounds):
    rs = sorted(by_round[r['round_id']], key=lambda x: x['seat'])
    print(f"[{i}] {r['round_id'][:8]} idx={r['round_index']} {r['kyoku_name']} {r['honba']}honba {r['riichi_sticks']}riichi {r['result_type']}")
    for s in rs:
        current_scores[s['seat']] += s['score_delta']
        tags = []
        if s['is_winner']: tags.append('WIN')
        if s['is_loser']: tags.append('LOSE')
        if s['is_riichi']: tags.append('RIICHI')
        tag_str = ','.join(tags)
        print(f"  S{s['seat']} {s['member_name']}: delta={s['score_delta']} (base={s['base_point']}, honba={s['honba_point']}, kyotaku={s['kyotaku_point']}, penalty={s['penalty_point']}) {tag_str}")
    print(f"  Scores: {current_scores}\n")
