MEMBERS = [
    "リョウト", "ユウダイ", "マサキ", "クノ", "オッチャン",
    "フルタ", "カツトシ", "ルイ", "シュン", "キド",
]
INIT_SCORE = 25000

KO_RON = [
    ("1000", 1000), ("1300", 1300), ("1600", 1600),
    ("2000", 2000), ("2600", 2600), ("3200", 3200),
    ("3900", 3900), ("5200", 5200), ("6400", 6400),
    ("7700", 7700), ("8000 (満貫)", 8000), ("12000 (跳満)", 12000),
]
OYA_RON = [
    ("1500", 1500), ("2000", 2000), ("2400", 2400),
    ("2900", 2900), ("3900", 3900), ("4800", 4800),
    ("5800", 5800), ("7700", 7700), ("9600", 9600),
    ("11600", 11600), ("12000 (満貫)", 12000), ("18000 (跳満)", 18000),
]
KO_TSUMO = [
    ("300/500", 300, 500),
    ("500/1000", 500, 1000),
    ("700/1300", 700, 1300),
    ("1000/2000", 1000, 2000),
    ("1300/2600", 1300, 2600),
    ("1600/3200", 1600, 3200),
    ("2000/4000 (満貫)", 2000, 4000),
    ("3000/6000 (跳満)", 3000, 6000),
]
OYA_TSUMO = [
    ("500オール", 500), ("1000オール", 1000),
    ("1300オール", 1300), ("2000オール", 2000),
    ("2600オール", 2600), ("2900オール", 2900),
    ("4000オール (満貫)", 4000), ("6000オール (跳満)", 6000),
]

HOUSE_RULES = {
    "精算": [
        "25,000点持ち / 30,000点返し / 飛びあり",
        "10-30：1位+50 / 2位+10 / 3位-10 / 4位-30（×0.2）",
        "ノーテン罰符：3,000点均等分配",
    ],
    "試合の流れ": [
        "半荘戦 ",
        "座席：つかみ取り",
        "起家：サイコロ2振り / 開門：1振り",
        "南場ノーテン親落ち",
        "聴牌連荘 / アガリ止めなし / テンパイ止めなし",
        "西入：トップ30,000点未満で継続（誰かが30,000点以上かつトップになった時点でサドンデス終局。※親が上がっても連荘せず即終局） / 北入なし",
    ],
    "基本ルール": [
        "喰いタン・後付けあり / 常時1翻縛り / 赤牌3枚",
        "一発・カンドラ・裏ドラ（カン裏含む）あり",
        "四風子連打・九種九牌・四人リーチ流局なし",
        "人和なし / 流し満貫あり",
    ],
    "特殊ルール": [
        "ダブロン・トリロンなし / 上家取り（同着も）/ 供託はトップ取り",
        "喰い変えなし / ツモ番なしリーチ不可",
        "フリテンリーチ・見逃しあり",
        "カン4回まで",
        "（同一人物4回は継続、それ以外流局）",
        "槍槓：カン不成立 / 加カンは嶺上ツモ後にカンドラ",
        "パオ：ツモは全額払い / ロンはロンされた人と折半",
    ],
    "役満": [
        "複合・数え役満あり",
        "国士無双：暗カンアガリあり / 13面まちはダブル役満",
        "四暗刻単騎・大四喜：ダブル役満",
    ],
    "チョンボ": [
        "ひどい場合：満貫払い / それ以外：アガリ放棄",
    ],
    "その他": [
        "農作業などを優先し、麻雀に熱中しすぎない",
        "恋人より麻雀を優先した場合、1局ごとに-100pt",
    ],
}


DEFAULT_RULE_CONFIG = {
    "basic": {
        "player_count": 4,
        "init_score": 25000,
        "return_score": 30000,
        "uma": [50, 10, -10, -30],
        "oka_type": "top_takes_all",
        "rate_note": "1000点＝1.0pt",
        "rounding_type": "goshagokyu",
    },
    "detail": {
        "kuitan": True,
        "atozuke": True,
        "aka_dora": "3枚",
        "dora_setting": "all",
        "kuikae": "forbidden",
        "kyushu": "renchan",
        "sufon": "none",
        "sujin_riichi": "none",
        "sukan": "allowed_single",
        "nagashi_mangan": "mangan_renchan",
        "dubron": "atama_hane",
        "furiten_tsumo": True,
        "tsumoban_none_riichi": False,
        "ippatsu": True,
        "renho": "none",
        "tobi_end": "under_zero",
        "tobi_penalty_pt": 0,
        "west_extension": "under_30000",
        "agari_yame": True,
        "tenpai_yame": True,
        "renchan_rule": "tenpai",
        "yakuman_multiple": True,
        "kokushi_ankan_win": True,
        "pao": True,
        "chombo_rule": "mangan_pay",
        "chombo_pt": 20,
        "house_notes": "",
    }
}


def generate_rule_description(config):
    """ルール設定辞書から説明文章マップ(HOUSE_RULES互換形式)を動的生成"""
    if not isinstance(config, dict):
        return HOUSE_RULES

    # 構造のノーマライズ（旧データ互換）
    basic = config.get("basic", {})
    detail = config.get("detail", {})

    init_s = basic.get("init_score", config.get("init_score", 25000))
    ret_s = basic.get("return_score", config.get("return_score", 30000))
    uma = basic.get("uma", config.get("uma", [50, 10, -10, -30]))
    uma_str = f"{uma[0]:+}, {uma[1]:+}, {uma[2]:+}, {uma[3]:+}"

    tobi_type = detail.get("tobi_end", "under_zero")
    tobi_str = "飛びあり (0点未満)" if tobi_type == "under_zero" else ("飛びあり (0点以下)" if tobi_type == "zero_or_less" else "トビなし")

    # 精算
    seisan = [
        f"{init_s:,}点持ち / {ret_s:,}点返し / {tobi_str}",
        f"順位点 (ウマ)：[{uma_str}]",
        f"端数処理：{basic.get('rounding_type', '五捨六入')}",
    ]
    rate = basic.get("rate_note", "")
    if rate:
        seisan.append(f"レート・換算メモ：{rate}")

    # 基本・アリアリ
    kuitan_str = "あり" if detail.get("kuitan", True) else "なし"
    atozuke_str = "あり" if detail.get("atozuke", True) else "なし"
    aka_str = detail.get("aka_dora", "3枚")
    kuikae_str = "不可" if detail.get("kuikae", "forbidden") == "forbidden" else "可"
    
    kihon = [
        f"喰いタン：{kuitan_str} / 後付け：{atozuke_str} / 赤牌：{aka_str}",
        f"喰い替え：{kuikae_str} / 一発・カンドラ・裏ドラあり",
        f"フリテンリーチ・見逃しツモ：{'あり' if detail.get('furiten_tsumo', True) else 'なし'}",
        f"ツモ番なしリーチ：{'可能' if detail.get('tsumoban_none_riichi', False) else '不可'}",
    ]

    # 進行・流局
    renchan_map = {"tenpai": "聴牌連荘", "agari": "和了連荘", "noten": "ノーテン連荘"}
    renchan_str = renchan_map.get(detail.get("renchan_rule", "tenpai"), "聴牌連荘")

    west_map = {
        "under_30000": "トップ30,000点未満で西入 (サドンデス)",
        "none": "なし (オーラスで必ず終了)",
        "fixed_nan4": "南4局固定終了",
    }
    west_str = west_map.get(detail.get("west_extension", "under_30000"), "西入あり")

    shinko = [
        f"親連荘条件：{renchan_str}",
        f"西入延長：{west_str}",
        f"アガリ止め・テンパイ止め：{'あり' if detail.get('agari_yame', True) else 'なし'}",
    ]
    
    mid_ryu_map = {"renchan": "あり (連荘)", "ryukyoku": "あり (親流れ/流局)", "none": "なし (流局とせず続行)"}
    kyushu_str = mid_ryu_map.get(detail.get("kyushu", "renchan"), "あり (連荘)")
    shinko.append(f"途中流局 (九種・四風など)：{kyushu_str}")

    # 役満・特殊・チョンボ
    dubron_map = {"atama_hane": "なし (頭ハネ/上家取り)", "atama_hane_kyotaku": "あり (供託は頭ハネ)", "split": "あり (全分配)"}
    dubron_str = dubron_map.get(detail.get("dubron", "atama_hane"), "頭ハネ")

    chombo_map = {"mangan_pay": "満貫払い", "pt_penalty": f"対局後 -{detail.get('chombo_pt', 20)}pt 直減算", "agari_hoki": "アガリ放棄のみ"}
    chombo_str = chombo_map.get(detail.get("chombo_rule", "mangan_pay"), "満貫払い")

    tokushu = [
        f"ダブロン・トリロン：{dubron_str}",
        f"パオ (責任払い)：{'あり (ツモ全額/ロン折半)' if detail.get('pao', True) else 'なし'}",
        f"役満複合・数え役満：{'あり' if detail.get('yakuman_multiple', True) else 'なし'}",
        f"国士無双暗カンアガリ：{'あり' if detail.get('kokushi_ankan_win', True) else 'なし'}",
        f"チョンボ扱い：{chombo_str}",
    ]

    res = {
        "精算": seisan,
        "基本・アリアリルール": kihon,
        "試合の進行": shinko,
        "特殊ルール・チョンボ": tokushu,
    }

    house_notes = detail.get("house_notes", "")
    if house_notes and house_notes.strip():
        res["ハウスルールメモ"] = [line.strip() for line in house_notes.strip().split("\n") if line.strip()]

    return res

