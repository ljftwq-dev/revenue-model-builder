"""M6: signal weighting - how to use OpenRouter signals, per vendor type.

Question this module answers: the OpenRouter (ORT) panel is price-sensitive
developer traffic. Does an ORT share move mean the same thing for a
domestic price-elastic vendor (zhipu / deepseek / ...) as for a foreign
tech-elastic one (anthropic / openai / ...)?

Calibration (2025-01 ~ 2026-08, openrouter.db vs company disclosures):

  domestic price-elastic  ->  ORT is a SYNCHRONIZED DRIVER
    evidence: zhipu ORT 28d-rolling jumps track ARR milestones exactly
      GLM-4.5 on ORT (25/08):   0.00 -> 0.23T
      GLM-5 around launch (26/02): 0.81 -> 2.83T (+250%)   [ARR Mar 17亿CNY]
      GLM-5.3 latest (26/08):   3.02 -> 14.88T (+393%)     [ARR Jul $1B]
    company ARR grew 15x (Jan-Jul 26) vs ORT ~18x over the same span:
    ORT explains nearly all of it. Use ORT volume as a revenue driver.

  foreign tech-elastic  ->  ORT is a BIASED AMPLIFIER, not a revenue proxy
      2025 full year : run-rate 6.4x  vs ORT 3.1x   (understates growth -
                       enterprise/subscription revenue never touches ORT)
      2026 Jan-Jul   : run-rate 7.2x  vs ORT 7.7x   (sync while rising)
      2026 Jul-Aug   : ORT -27% from peak while run-rate still rising to
                       $65B  (amplifies drops - price-sensitive layer exits
                       first; enterprise sticks)
    cumulative: RR 46x vs ORT 24x since 2025-01 - ORT explains only ~half.
    Use ORT only as an early-warning trigger (M5 D2); confirm decay with
    official run-rate anchors before revising g(t) down.

Run:  python signal_weight.py   (pure stdlib, calibration data embedded)
"""

DOMESTIC = {'z-ai', 'deepseek', 'minimax', 'moonshotai', 'xiaomi', 'tencent',
            'qwen', 'stepfun', 'baidu', 'alibaba', '01-ai', 'bytedance'}

CALIB = {
    'zhipu': {
        'type': 'domestic price-elastic',
        'events': [
            ('2025-08', 'GLM-4.5 on ORT', 0.00, 0.23),
            ('2026-02', 'GLM-5 launch', 0.81, 2.83),
            ('2026-08', 'GLM-5.3 + intro discount', 3.02, 14.88),
        ],
        'company_growth': 'ARR 15x (2026 Jan-Jul)',
        'ort_growth': '~18x same span',
        'verdict': 'SYNC — ORT explains nearly all growth',
    },
    'anthropic': {
        'type': 'foreign tech-elastic',
        'phases': [
            ('2025 FY', 6.4, 3.1, 'ORT underestimates (enterprise/subscription off-ORT)'),
            ('2026 Jan-Jul', 7.2, 7.7, 'sync while rising'),
            ('2026 Jul-Aug', None, -0.27, 'ORT -27% from peak while run-rate still rising'),
        ],
        'company_growth': 'run-rate 46x (2025-01 -> 2026-07)',
        'ort_growth': '24x same span',
        'verdict': 'BIASED AMPLIFIER — ORT explains ~half; drops are amplified',
    },
}


def classify(vendor):
    return ('domestic price-elastic' if vendor in DOMESTIC
            else 'foreign tech-elastic')


def advise(vendor):
    kind = classify(vendor)
    if kind == 'domestic price-elastic':
        return ('ORT volume = revenue DRIVER: feed directly into the forecast '
                'pipeline (zhipu case: -4% error). Weight HIGH. A rival-model '
                'launch with intro pricing moves revenue within weeks.')
    return ('ORT = EARLY-WARNING ONLY: use M5 D2 (rival share momentum) to '
            'arm a g-decay prior, but DO NOT map ORT share to revenue. '
            'Confirm with run-rate anchors (RR 46x vs ORT 24x - only ~half '
            'of growth is visible on ORT). Weight LOW, directional.')


def main():
    print('=' * 76)
    print(' M6 信号定权：OpenRouter 信号怎么用（按厂商类型）')
    print('=' * 76)

    z, a = CALIB['zhipu'], CALIB['anthropic']
    print('\n① 校准样本A — 智谱（%s）' % z['type'])
    for ev, desc, t0, t1 in z['events']:
        print('   %-8s %-26s %.2fT -> %.2fT' % (ev, desc, t0, t1))
    print('   公司 %s vs ORT %s → %s' % (z['company_growth'], z['ort_growth'], z['verdict']))

    print('\n② 校准样本B — Anthropic（%s）' % a['type'])
    for ph, rr, ort, note in a['phases']:
        rrs = '%.1fx' % rr if rr else '  -'
        orts = ('%.1fx' % ort) if ort and ort > 0 else '%.0f%%' % (ort * 100)
        print('   %-14s RR %-6s ORT %-7s %s' % (ph, rrs, orts, note))
    print('   公司 %s vs ORT %s → %s' % (a['company_growth'], a['ort_growth'], a['verdict']))

    print('\n③ 使用建议（classify(vendor) -> advise）')
    for v in ('z-ai', 'deepseek', 'anthropic', 'openai', 'google'):
        print('   %-12s[%s]' % (v, classify(v)))
        print('     %s' % advise(v))

    print('\n④ 预测管道接线')
    for s in [
        '国内厂商: ORT周度量 -> driver层(量) -> 收入 = 付费token x 单价(提价事件修正)',
        '国外厂商: ORT只接 M5 的 D2 检测器 -> g衰减先验 -> 等 run-rate 锚点确认再兑现',
        '边界条件: 若国内厂商企业直连占比升高(智谱企业级智能体), 其信号权重应逐步下调',
    ]:
        print('   - %s' % s)


if __name__ == '__main__':
    main()
