import math
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
        total, dealer_pay, non_dealer_pay = calculate_score(3, 30, is_dealer=True, is_tsumo=True)
        assert total == 6000
        assert dealer_pay == 0
        assert non_dealer_pay == 2000

    def test_3han_30fu_non_dealer_tsumo(self):
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
        total, _, _ = calculate_score(6, 30, is_dealer=True, is_tsumo=False)
        assert total == 18000

    def test_baiman_dealer_ron(self):
        total, _, _ = calculate_score(8, 30, is_dealer=True, is_tsumo=False)
        assert total == 24000

    def test_yakuman_dealer_ron(self):
        total, _, _ = calculate_score(13, 30, is_dealer=True, is_tsumo=False)
        assert total == 48000


class TestCalcSpecialPoint:
    """ウマ・オカ計算のテスト"""

    def test_rank1_at_return_point(self):
        assert calc_special_point(30000, 1) == 50.0

    def test_rank4_below_return_point(self):
        assert calc_special_point(20000, 4) == -40.0

    def test_rank2_above_return_point(self):
        assert calc_special_point(35000, 2) == 15.0

    def test_zero_sum_4players(self):
        scores = [40000, 32000, 18000, 10000]
        ranks = [1, 2, 3, 4]
        total = sum(calc_special_point(s, r) for s, r in zip(scores, ranks))
        assert abs(total) < 1e-6


class TestCalcOkaNashiPoint:
    """オカなし計算のテスト"""

    def test_rank1_at_init_score(self):
        assert calc_oka_nashi_point(25000, 1) == 30.0

    def test_rank2_at_init_score(self):
        assert calc_oka_nashi_point(25000, 2) == 10.0

    def test_rank3_above_init_score(self):
        assert calc_oka_nashi_point(30000, 3) == -5.0

    def test_zero_sum_4players(self):
        scores = [40000, 32000, 18000, 10000]
        ranks = [1, 2, 3, 4]
        total = sum(calc_oka_nashi_point(s, r) for s, r in zip(scores, ranks))
        assert abs(total) < 1e-6


if __name__ == "__main__":
    t1 = TestCalculateScore()
    t1.test_1han_30fu_dealer_ron()
    t1.test_1han_30fu_non_dealer_ron()
    t1.test_3han_30fu_dealer_tsumo()
    t1.test_3han_30fu_non_dealer_tsumo()
    t1.test_mangan_dealer_ron()
    t1.test_mangan_non_dealer_ron()
    t1.test_haneman_dealer_ron()
    t1.test_baiman_dealer_ron()
    t1.test_yakuman_dealer_ron()

    t2 = TestCalcSpecialPoint()
    t2.test_rank1_at_return_point()
    t2.test_rank4_below_return_point()
    t2.test_rank2_above_return_point()
    t2.test_zero_sum_4players()

    t3 = TestCalcOkaNashiPoint()
    t3.test_rank1_at_init_score()
    t3.test_rank2_at_init_score()
    t3.test_rank3_above_init_score()
    t3.test_zero_sum_4players()

    print("ALL TESTS PASSED SUCCESSFULLY!")
<<<<<<< Updated upstream

=======
>>>>>>> Stashed changes
