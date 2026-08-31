# 大模型行业板块①：五家公司 ARR 阶梯与预测检验

> **行业划分路线的第一块**：大模型（基础模型层）。五家代表性公司，同一套"ARR 锚点预测 → 实际对答案"流程。
> 时点：2026-08-31 ｜ 数据：各公司披露 + 权威媒体（Bloomberg/CNBC/Reuters/The Information 等）

## 1. 为什么从大模型行业开始

- **ARR/run-rate 是全行业通用的领先指标**：管理层主动披露（智谱 3 月/7 月、Anthropic 每月、OpenAI CFO 内部会），信息频率远高于财报
- **口径梯度完整**：两家无财报（OpenAI/DeepSeek）、一家无审计财报（Anthropic）、一家季报制（Google）、一家半年报制（智谱）——正好检验预测方法在不同披露环境下的适配

## 2. 五家公司 2026 年中收入阶梯（详见 `data/llm_runrates.json`）

| 公司 | 商业模式 | 最新年化量级 | 口径 |
|---|---|---|---|
| Anthropic | 闭源高价 | **$650亿**（7月 run-rate） | 媒体报道 |
| OpenAI | 闭源规模平价 | **$400亿+**（8月 run-rate） | Bloomberg |
| Google Cloud | 闭源+云捆绑 | **$248亿**（Q2 季度收入，+82% YoY） | GAAP 审计 |
| 智谱 02513.HK | 闭源平价（中国） | **$10亿 ARR**（7月，官方） | 港股半年报+官方 |
| DeepSeek | 开源极低价 | **≈$5亿**（年化，媒体估算） | 估算 |

## 3. 预测检验（同一流程重复五次）

| 检验 | 预测方法（仅用事前信息） | 预测 | 实际 | 误差 |
|---|---|---|---|---|
| 智谱 2026H1 收入 | ARR 单锚点指数（M2） | 9.16 亿元 | 9.54 亿元 | **-4.0%** ✅ |
| OpenAI 2026Q2 GAAP 收入 | 2025末+3月锚点外推 | $7.3B | $6.7B | **+9%** ✅ |
| Anthropic 7月 run-rate | 2月+4月锚点外推 | $94B | $65B | **+45%** ❌ |
| Google Cloud Q1/Q2 收入 | 卖方 consensus | $18.4B / $22.5B | $20.0B / $24.8B | **-8.8% / -10.3%**（低配） |
| DeepSeek 年化收入 | 2025-03 理论日收入年化 | $205M→外推 | ≈$500M（媒体） | 无对答案（对照组） |

## 4. 行业级发现

1. **锚点法在加速期准、在减速期高估**：智谱（-4%）和 OpenAI（+9%）处于加速段；Anthropic 后段（4→7月）实际月环比从 1.46x 降到 ~1.30x，恒定指数外推高估 45%——与智谱"前快后慢"同构。**改进方向：衰减项 g(t) 随规模递减**
2. **卖方 consensus 在爆发期系统性低配 ~10%**：Google Cloud 连续两季 beat（+8.8%/+10.3%），分析师锚定历史增速，低估加速度
3. **三条商业模式分化**：闭源高价（Anthropic，$65B）、闭源平价规模（OpenAI $40B、智谱 $1B）、开源极低价（DeepSeek ≈$0.5B，但理论成本利润率 545%，盈利性最好）
4. **Google 的第二领先指标——backlog**：$460B(Q1)→$514B(Q2)，环比+12%，比收入更早反映 AI 需求订单

## 5. 复现

```bash
python llm_ladder.py   # 纯标准库
```

## 6. 文件结构

```
llm_arr_ladder/
├── README.md              # 本文档
├── llm_ladder.py          # 阶梯表 + 五次预测检验脚本
└── data/
    └── llm_runrates.json  # 五家锚点/实际值/来源
```

## 数据来源

- 智谱：中期业绩公告（2026-08-31）；ARR 报道（中金在线、《智能涌现》）
- OpenAI：The Information（2025末$21.4B）、dealroom（3月月收入$2B）、CNBC（CFO 内部会，Q2 GAAP $6.7B）、Bloomberg（8月$40B+）
- Anthropic：Bloomberg/CNBC/Reuters（2026-08-17，$65B）；Series H 披露（5月$47B）
- Google：Alphabet Q1/Q2 2026 财报（SEC 10-Q/8-K，GAAP）；consensus（Visible Alpha/LSEG 转引）
- DeepSeek：Reuters（2025-03，理论日收入$562K、成本利润率545%）；PYMNTS（2026年化≈$500M）

---

*仅作预测方法论研究用途，不构成投资建议。*