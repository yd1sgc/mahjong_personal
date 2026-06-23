import pytest
from calc import calculate_score, calc_special_point, calc_oka_nashi_point


class TestCalculateScore:
    """翻数・符数から点数を計算する関数のテスト"""

    def test_1han_30fu_dealer_ron(self):
        total, dealer_pay, non_dealer_pay = calculate_score(1, 30, is_dealer=True, is_tsumo=False)
        assert total == 1500
        assert dealer_pay == 0
        assert non_dealer_pay == 0

    def test_1han_30fu_non_dealer_ron(self):
        total, dealer_pay, non_dealer_pay = calculate_score(1, 30, is_dealer=False, is_tsumo=False)
        assert total == 1000
        assert dealer_pay == 0
        assert non_dealer_pay == 0

    def test_3han_30fu_dealer_tsumo(self):
        # base=960, round_up(1920)=2000, total=6000
        total, dealer_pay, non_dealer_pay = calculate_score(3, 30, is_dealer=True, is_tsumo=True)
        assert total == 6000
        assert dealer_pay == 0
        assert non_dealer_pay == 2000

    def test_3han_30fu_non_dealer_tsumo(self):
        # dealer=2000, non_dealer=1000, total=4000
        total, dealer_pay, non_dealer_pay = calculate_score(3, 30, is_dealer=False, is_tsumo=True)
        assert total == 4000
        assert dealer_pay == 2000
        assert non_dealer_pay == 1000

    def test_mangan_dealer_ron(self):
        total, _, _ = calculate_score(5, 30, is_dealer=True, is_tsumo=False)
        assert total == 12000

    def test_mangan_non_dealer_ron(self):
        total, _, _ = calculate_score(5, 30, is_dealer=False, is_tsumo=False)
        assert total == 8000

    def test_haneman_dealer_ron(self):
        # 6-7翻: base=3000
        total, _, _ = calculate_score(6, 30, is_dealer=True, is_tsumo=False)
        assert total == 18000

    def test_baiman_dealer_ron(self):
        # 8-10翻: base=4000
        total, _, _ = calculate_score(8, 30, is_dealer=True, is_tsumo=False)
        assert total == 24000

    def test_yakuman_dealer_ron(self):
        # 13翻以上: base=8000
        total, _, _ = calculate_score(13, 30, is_dealer=True, is_tsumo=False)
        assert total == 48000


class TestCalcSpecialPoint:
    """ウマ・オカ計算のテスト（RETURN_POINT=30000, UMA={1:30, 2:5, 3:-5, 4:-10}）"""

    def test_rank1_at_return_point(self):
        # (30000-30000)/1000 + 30 = 30.0
        assert calc_special_point(30000, 1) == 30.0

    def test_rank4_below_return_point(self):
        # (20000-30000)/1000 + (-10) = -20.0
        assert calc_special_point(20000, 4) == -20.0

    def test_rank2_above_return_point(self):
        # (35000-30000)/1000 + 5 = 10.0
        assert calc_special_point(35000, 2) == 10.0

    def test_zero_sum_4players(self):
        # 4人の点数合計=100000 のとき、ポイント合計は必ず0になる
        scores = [40000, 32000, 18000, 10000]
        ranks = [1, 2, 3, 4]
        total = sum(calc_special_point(s, r) for s, r in zip(scores, ranks))
        assert total == pytest.approx(0.0)


class TestCalcOkaNashiPoint:
    """オカなし計算のテスト（INIT_SCORE=25000, RETURN_POINT=30000）"""

    def test_rank1_at_init_score(self):
        # oka=20, base_pt=0, uma_pt=30-20=10 → 10.0
        assert calc_oka_nashi_point(25000, 1) == 10.0

    def test_rank2_at_init_score(self):
        # base_pt=0, uma_pt=5 → 5.0
        assert calc_oka_nashi_point(25000, 2) == 5.0

    def test_rank3_above_init_score(self):
        # (30000-25000)/1000 + (-5) = 5 - 5 = 0.0
        assert calc_oka_nashi_point(30000, 3) == 0.0

    def test_zero_sum_4players(self):
        # 4人の点数合計=100000 のとき、オカなしでもポイント合計は0になる
        scores = [40000, 32000, 18000, 10000]
        ranks = [1, 2, 3, 4]
        total = sum(calc_oka_nashi_point(s, r) for s, r in zip(scores, ranks))
        assert total == pytest.approx(0.0)
