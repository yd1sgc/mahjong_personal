import sys
import os

# src へのパスを通す
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))
import game_logic
import calc

print("Testing dynamic game_logic features...")

players = ["A", "B", "C", "D"]

# 1. 動的本場点テスト (honba_pt = 1500)
custom_cfg = {
    "basic": {
        "init_score": 25000,
        "return_score": 30000,
        "game_length": "hanchan",
        "uma": [50, 10, -10, -30]
    },
    "detail": {
        "honba_pt": 1500,
        "riichi_pt": 1000,
        "tobi_end": "under_zero",
        "west_extension": "under_30000",
        "noten_bappu_pt": 3000
    }
}

gs = game_logic.GameState(players, 25000, custom_cfg)
# 東1局: 流局 (全員ノーテン -> 親流れ, 1本場)
gs.apply_ryukyoku(tenpai_players=[])
# 東2局: 流局 (全員ノーテン -> 親流れ, 2本場)
gs.apply_ryukyoku(tenpai_players=[])

# 東3局 2本場: A が B から 8000点ロン和了 (8000 + 1500*2 = 11000点)
gs.apply_win(winner="A", win_type="ron", points_data={"total": 8000}, loser="B")

assert gs.scores["A"] == 25000 + 11000, f"Expected 36000, got {gs.scores['A']}"
assert gs.scores["B"] == 25000 - 11000, f"Expected 14000, got {gs.scores['B']}"
print("[PASS] Dynamic honba_pt (1500/honba) verified")


# 2. 東風戦 (tonpu) 終了判定テスト
tonpu_cfg = {
    "basic": {
        "init_score": 25000,
        "return_score": 30000,
        "game_length": "tonpu",
        "uma": [20, 10, -10, -20]
    },
    "detail": {
        "tobi_end": "under_zero",
        "west_extension": "none",
        "agari_yame": True
    }
}

gs_tonpu = game_logic.GameState(players, 25000, tonpu_cfg)
gs_tonpu.round_idx = 4 # 東4局終了直後 (round_idx = 4)
gs_tonpu.scores = {"A": 35000, "B": 25000, "C": 22000, "D": 18000}
end_msg = gs_tonpu.check_game_end()
assert end_msg == "東4局終了", f"Expected '東4局終了', got '{end_msg}'"
print("[PASS] Tonpu game end (East 4) verified")

# 3. 飛びなし (tobi_end = "none") テスト
no_tobi_cfg = {
    "basic": {
        "init_score": 25000,
        "return_score": 30000,
        "game_length": "hanchan"
    },
    "detail": {
        "tobi_end": "none",
        "west_extension": "none"
    }
}

gs_notobi = game_logic.GameState(players, 25000, no_tobi_cfg)
gs_notobi.round_idx = 2 # 東3局
gs_notobi.scores = {"A": 45000, "B": -5000, "C": 30000, "D": 30000} # Bがマイナス
end_msg_notobi = gs_notobi.check_game_end()
assert end_msg_notobi is None, f"Expected None (game continues despite negative score), got '{end_msg_notobi}'"
print("[PASS] tobi_end = 'none' (box-under continuation) verified")

# 4. build_v2_game_payload 検証
payload = game_logic.build_v2_game_payload(
    game_state=gs,
    players=players,
    scores=gs.scores,
    group_id="test_group_id",
    rule_id="custom_rule",
    rule_config=custom_cfg
)

assert payload["game_mode"] == "detail", f"Expected detail, got {payload['game_mode']}"
assert len(payload["participants"]) == 4, "Participants count != 4"
assert len(payload["rounds"]) == 3, f"Rounds count != 3 (got {len(payload['rounds'])})"

round_3 = payload["rounds"][2]
assert len(round_3["seats"]) == 4, "Seats count != 4"

seat_A = next(s for s in round_3["seats"] if s["seat"] == 1)
seat_B = next(s for s in round_3["seats"] if s["seat"] == 2)
assert seat_A["is_winner"] == 1, "Seat A should be winner"
assert seat_A["base_point"] == 8000, f"Expected 8000, got {seat_A['base_point']}"
assert seat_A["honba_point"] == 3000, f"Expected 3000, got {seat_A['honba_point']}"
assert seat_A["score_delta"] == 11000, f"Expected 11000, got {seat_A['score_delta']}"
assert seat_B["is_loser"] == 1, "Seat B should be loser"
assert seat_B["score_delta"] == -11000, f"Expected -11000, got {seat_B['score_delta']}"

print("[PASS] build_v2_game_payload verified")

print("\nALL DYNAMIC GAME LOGIC TESTS PASSED SUCCESSFULLY!")
