from core.rules import *

def get_fan_score(hand, melds, is_tianhu=False, is_dihu=False):
    fans = []
    base_score = 1
    fan_count = 0

    if is_dragon_seven_pairs(hand, melds):
        fan_count += 3
        fans.append("龙七对")
        if is_qing_yi_se(hand, melds):
            fan_count += 2
            fans.append("清一色")
        if is_duan_yao_jiu(hand, melds):
            fan_count += 1
            fans.append("断幺九")
        fan_count = min(fan_count, 5)
        score = base_score * (2 ** fan_count)
        return score, fans
    elif is_seven_pairs(hand, melds):
        fan_count += 2
        fans.append("七对")
        if is_qing_yi_se(hand, melds):
            fan_count += 2
            fans.append("清一色")
        if is_duan_yao_jiu(hand, melds):
            fan_count += 1
            fans.append("断幺九")
        fan_count = min(fan_count, 5)
        score = base_score * (2 ** fan_count)
        return score, fans

    # 普通标准胡牌
    if is_tianhu:
        fan_count += 5
        fans.append("天胡")
    elif is_dihu:
        fan_count += 5
        fans.append("地胡")
    if is_peng_peng_hu(hand, melds):
        fan_count += 1
        fans.append("碰碰胡")
    if is_men_qing(melds):
        fan_count += 1
        fans.append("门清")
    if is_qing_yi_se(hand, melds):
        fan_count += 2
        fans.append("清一色")
    yi_gen_cnt = count_yi_gen(hand, melds)
    if yi_gen_cnt > 0:
        fan_count += yi_gen_cnt
        fans.append(f"{yi_gen_cnt}根")
    if is_duan_yao_jiu(hand, melds):
        fan_count += 1
        fans.append("断幺九")
    if not fans:
        fans = ["鸡胡"]
    fan_count = min(fan_count, 5)
    score = base_score * (2 ** fan_count)
    return score, fans


def is_peng_peng_hu(hand, melds):
    """
    手牌hand为list，melds为副露区list of list，每组副露为list[Tile]。
    """
    from collections import Counter
    all_tiles = list(hand)
    koutsu_count = 0
    # 1. 统计副露中的刻子/杠
    for meld in melds:
        if len(meld) in (3, 4) and all(t == meld[0] for t in meld):
            koutsu_count += 1
        else:
            return False  # 副露中有顺子或吃，直接不是碰碰胡
    # 2. 剩余手牌中每次尽量拆刻子
    c = Counter(all_tiles)
    while True:
        found = False
        for t, n in c.items():
            if n >= 3:
                c[t] -= 3
                koutsu_count += 1
                found = True
                break
        if not found:
            break
    # 3. 剩下必须只剩1种牌且数量为2（对子），且刻子总数==4
    rest = [t for t, n in c.items() for _ in range(n) if n > 0]
    if koutsu_count == 4 and len(rest) == 2 and rest[0] == rest[1]:
        return True
    else:
        return False

def is_men_qing(melds):
    """门清：副露区为空"""
    return len(melds) == 0

def is_qing_yi_se(hand, melds):
    """清一色：所有手牌、副露同一花色"""
    # 只认man/pin/sou（不算风牌/三元牌）
    suits = set()
    for t in hand:
        if t.suit.value not in ('man', 'pin', 'sou'):
            continue
        suits.add(t.suit.value)
    for meld in melds:
        for t in meld:
            if t.suit.value not in ('man', 'pin', 'sou'):
                continue
            suits.add(t.suit.value)
    return len(suits) == 1 and len(suits) != 0

def count_yi_gen(hand, melds):
    """
    返回“根”的数量。
    hand: 手牌列表
    melds: 副露区（明刻、杠等）
    """
    from collections import Counter
    all_tiles = list(hand)
    for meld in melds:
        all_tiles += meld
    c = Counter(all_tiles)
    return sum(1 for v in c.values() if v >= 4)

def is_duan_yao_jiu(hand, melds):
    """
    断幺九：手牌和副露都不含1m/9m/1p/9p/1s/9s
    """
    yao_jiu = set([
        ("man", 1), ("man", 9),
        ("pin", 1), ("pin", 9),
        ("sou", 1), ("sou", 9)
    ])
    def is_yaojiu(tile):
        return (tile.suit.value, tile.value) in yao_jiu
    # 检查手牌
    for t in hand:
        if is_yaojiu(t):
            return False
    # 检查副露
    for meld in melds:
        for t in meld:
            if is_yaojiu(t):
                return False
    return True