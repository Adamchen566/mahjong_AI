from collections import Counter

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

def get_fan_score(hand, melds, is_tianhu=False, is_dihu=False):
    """
    返回：最终得分（2^番数，番数最多5），以及所有番型名字
    """
    fans = []
    base_score = 1
    fan_count = 0
    if is_tianhu:
        return 32, ["天胡"]
    if is_dihu:
        return 32, ["地胡"]
    if is_peng_peng_hu(hand, melds):
        fan_count += 1
        fans.append("碰碰胡")
    if is_men_qing(melds):
        fan_count += 1
        fans.append("门清")
    if is_qing_yi_se(hand, melds):
        fan_count += 2
        fans.append("清一色")
    if not fans:
        fans = ["鸡胡"]
    # 番数上限5番
    fan_count = min(fan_count, 5)
    score = base_score * (2 ** fan_count)
    return score, fans
