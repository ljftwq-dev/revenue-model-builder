"""M7: Elo anchor test - a NEGATIVE result worth keeping.

Question: can Arena (text leaderboard) Elo be the "technology anchor" of the
forecast pipeline - i.e. quantify the technology shock in M4's event-jump
model, or arm M5's D2 detector with a magnitude instead of a dummy?

Method: align per-model ORT volume jumps (28d vendor rolling, before vs
after launch) with Arena Elo (first-7d mean vs +21d) for 8 major model
launches, 2025-06 ~ 2026-08. Full data: HF lmarena-ai/leaderboard-dataset
(text/full parquet) x local openrouter.db; numbers below are the extracted
alignment table so this script is self-contained.

Answer: NO. Three findings:

  1. Elo is priced AT launch: post-launch 21-day dElo stays within +/-30
     (noise band) for every model - there is no "jump" to extract.
  2. The king counter-example: glm-4.5 debuted at 1413 (NOT the top) and
     FELL 28 points in 3 weeks, yet ORT volume exploded 168x - the largest
     in the panel. Volume was driven by good-enough + dirt-cheap + zero
     base, not by arena standing.
  3. Spearman(dElo, ln ORT jump) = -0.46: wrong sign, no signal.
     Debut Elo LEVEL does not explain jumps either (1413 jumped most,
     1475 barely moved).

Implication (reinforces M6): domestic volume explosions are price-elastic
(Elo-agnostic); foreign vendors defend spend on capability arenas do not
measure. Elo's only usable signal is binary: "entered the board / top-N".
For magnitudes use task benchmarks (SWE-bench / Terminal-Bench generational
gains) or an Elo-per-price ratio.

Run:  python elo_anchor_test.py   (pure stdlib, data embedded)
"""

from math import log

# (model, vendor, launch, ort_jump_x, elo_debut, elo_21d)  ort=partial -> excluded from stats
DATA = [
    ('glm-4.5',           'z-ai',      '2025-07-30', 168.7, 1413, 1386),
    ('deepseek-v3.2',     'deepseek',  '2025-12-02',   1.4, 1418, 1420),
    ('deepseek-v4-flash', 'deepseek',  '2026-04-24',   2.3, 1426, 1426),
    ('deepseek-v4-pro',   'deepseek',  '2026-04-25',   2.4, 1447, 1448),
    ('glm-5.2',           'z-ai',      '2026-06-16',   4.0, 1467, 1463),
    ('claude-sonnet-5',   'anthropic', '2026-06-30',   1.0, 1445, 1442),
    ('gpt-5.6',           'openai',    '2026-07-11',   1.5, 1456, 1444),
    ('glm-5.3',           'z-ai',      '2026-08-26',   0.6, 1475, 1475),  # partial window
]
NOT_MATCHED = ['glm-5 (2026-02)', 'claude-opus-5 (2026-07)']  # no arena entry found under these keys


def _rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman(a, b):
    ra, rb = _rank(a), _rank(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = sum((x - ma) ** 2 for x in ra) ** 0.5
    vb = sum((y - mb) ** 2 for y in rb) ** 0.5
    return cov / (va * vb)


def main():
    print('=' * 78)
    print(' M7 Arena Elo 能否当技术锚点 —— 否定性验证')
    print('=' * 78)
    print('\n① 对齐表（ORT放量 × Arena Elo，8个主力发布）')
    print('   %-20s%-11s%9s%9s%9s%8s' % ('模型', '发布', 'ORT倍数', '首现Elo', '21d后', 'ΔElo'))
    full = []
    for m, v, d, j, e0, e1 in DATA:
        partial = j < 1.0
        if not partial:
            full.append((m, v, d, j, e0, e1))
        tag = ' (窗口未满)' if partial else ''
        print('   %-20s%-11s%8.1fx%9d%9d%+8d%s' % (m, d, j, e0, e1, e1 - e0, tag))
    print('   Arena无匹配: %s' % ', '.join(NOT_MATCHED))

    d_elo = [e1 - e0 for *_, e0, e1 in full]
    lnj = [log(j) for _, _, _, j, _, _ in full]
    print('\n② 统计（排除窗口未满，n=%d）' % len(full))
    print('   Spearman(ΔElo, ln ORT放量) = %.2f  → 方向反了，无信号' % spearman(d_elo, lnj))
    print('   ΔElo全部落在 ±%d 分内（噪声带，无跳变可提取）' % max(abs(x) for x in d_elo))

    print('\n③ 王炸反例：glm-4.5')
    print('   首现1413（非榜首）→ 21天后还跌28分，ORT却放量168.7x（面板史上最大）')
    print('   放量驱动 = 够好 + 超便宜 + 零基数（性价比三重奏），与竞技场排名无关')

    print('\n④ 结论与替代方案')
    for s in [
        'Elo发布即定标，之后不动 → 不存在"技术跳变"信号，M4事件幅度、M5 D2幅度都无法用它量化',
        'Elo唯一可用信息 = 二值信号（是否上榜/是否Top-N）',
        '幅度信息换源：任务级基准代际提升(SWE-bench/Terminal-Bench) 或 Elo/价格性价比比',
        '反证M6：国内放量与Elo无关=价格弹性；国外守住spend靠竞技场测不出的能力=技术弹性',
    ]:
        print('   - %s' % s)


if __name__ == '__main__':
    main()
