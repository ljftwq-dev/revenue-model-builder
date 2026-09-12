<div align="center">

<img src="assets/logo.png" width="180" alt="revenue-model-builder logo"/>

# revenue-model-builder

**像卖方分析师一样预测收入——一棵引擎能辩护、能分级、能压力测试的 driver tree。**

[![CI](https://github.com/ljftwq-dev/revenue-model-builder/actions/workflows/ci.yml/badge.svg)](https://github.com/ljftwq-dev/revenue-model-builder/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-mkdocs%20Material-536DFE.svg)](https://ljftwq-dev.github.io/revenue-model-builder/)
[![PyPI](https://img.shields.io/pypi/v/revenue-model-builder.svg)](https://pypi.org/project/revenue-model-builder/)
[![Downloads](https://img.shields.io/pypi/dm/revenue-model-builder.svg)](https://pypi.org/project/revenue-model-builder/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![Dependencies: zero](https://img.shields.io/badge/core%20dependencies-0-success.svg)](#安装)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

English documentation: [README.md](README.md)

<img src="assets/demo.gif" width="640" alt="60 秒演示：校验对齐、行业默认预测、蒙特卡洛"/>

*零依赖。纯标准库蒙特卡洛。每个数字都带来源与可信度分级。*

`分部收入 = 市场基数 × 渗透率 × 市占率 × 单价`
`总收入   = Σ(分部) + 差额行`

</div>

---

> ### 预注册、外样本验证
>
> v0.16 的行业适配论点已在 **244 家标普 500 成分股**（防幸存者偏差，锚定
> 2023-12-31 时点）+ 六棵手工 driver 树上按"测试集开启前冻结 spec"的纪律做过检验：
>
> - **Driver 层**：行业默认预测在可测的 4 棵树里 3 棵胜过朴素逐因子趋势
>   （SBUX **0.7%** vs 3.6%、META 4.6% vs 6.7%、NVDA Gaming **3.0%** vs 10.9% sMAPE）
> - **Weak 档重定向有效**：警告命中 **2/2**、误报 **0/4**，蒙特卡洛 P10–P90
>   框住全部三个 weak 档测试年（JPM NII 落在 P46；NVDA 数据中心 P75/P66）
> - **诚实公布零结果**：增长回归法在主场被否证；公司总收入层属于统计基线
>
> 完整记分牌：[docs/profile-validation.md](docs/profile-validation.md)

## 为什么做这个

开源金融工具覆盖了交易回测与 DCF 估值，但卖方分析师每天在 Excel 里搭的
**driver 分解收入预测**（`基数 × 渗透率 × 市占率 × 单价`）没有可运行的引擎。
Prompt skill 只描述方法；本库**就是方法本身**——数学写进代码，不留在表格注释里。

收入模型生死取决于每个数字能否被追问。这里每个 driver 带 **A/B/C 可信度分级**
与来源，**差额行是一等公民**（不是凑数），经典陷阱（反解渗透率、差额占比
过高）在污染预测之前就被检查拦下。

| | revenue-model-builder | 市场规模 prompt skill | DCF 库 |
|---|---|---|---|
| 可运行引擎 | ✅ | ❌ 仅 prompt | ✅ |
| 行业感知默认（10 画像） | ✅ | ❌ | ❌ |
| 对齐报告总收入（结构性差额行） | ✅ | ❌ | 不适用 |
| 每个数字 A/B/C 分级 | ✅ | ❌ | ❌ |
| 不确定性（MC + 龙卷风，纯标准库） | ✅ | ❌ | 部分有 |
| 核心依赖 | **0** | 不适用 | 通常 numpy + API |

## 一张图：driver tree 在哪准、在哪崩

![NVIDIA Gaming vs Data Center —— 真实 vs driver 外推](examples/nvda_demo/nvda_backtest.png)

同一家公司、同一个公式、同一个引擎——**Gaming**（成熟市场）hold-out
**sMAPE 1.0%**，**数据中心**（AI 范式跳变）差 6 倍，且**引擎在打开 hold-out
之前就报警**，重定向到蒙特卡洛情景，Bull 尾把真实 $115B 框住。准确性是行业
增长机制的属性——v0.16 把它编码为 10 个机制画像 × strong/adapt/weak 三档
（[已外样本验证](docs/profile-validation.md)）。

## 60 秒上手

```bash
pip install revenue-model-builder
```

```python
from revenue_model import (
    Driver, Segment, RevenueModel, BASE, PENETRATION, SHARE, PRICE,
    forecast_segment, segment_warnings, simulate_segment,
)

seg = Segment(
    "座舱-国内",
    base=Driver("中国乘用车销量", BASE, {2022: 22.0, 2023: 23.0},
                level="A", unit="百万辆", source="中汽协"),
    penetration=Driver("DMS 前装渗透率", PENETRATION, {2022: 0.04, 2023: 0.06},
                       level="B", unit="比例", source="行业研究院"),
    share=Driver("市占率", SHARE, {2022: 0.10, 2023: 0.12},
                 level="C", unit="比例", source="估计"),
    price=Driver("ASP", PRICE, {2022: 600, 2023: 620},
                 level="C", unit="元", source="对标"),
    industry="consumer_electronics",   # <- 一个标签改变一切
)
model = RevenueModel("DemoCo", [seg], total_revenue={2022: 78.0, 2023: 163.0})

print(model.validate_all())               # Σ 分项 + 差额行 == 报告总收入
fc = forecast_segment(seg, [2024, 2025])  # 行业默认外推
for w in segment_warnings(fc):            # 预测之前就给出适配判定
    print(w)
mc = simulate_segment(fc, 2024, {"市占率": (0.10, 0.18)}, n=20000)
print(mc.median, mc.percentiles["p5"], mc.percentiles["p95"])
```

或看上方 GIF。CLI：`python -m revenue_model {build, simulate, excel, docx, extract, sec, akshare, tushare}`。

## 里面有什么

| 能力 | 价值 |
|---|---|
| **Driver 树核心**（纯标准库，零依赖） | 可审计的 `基数×渗透率×市占率×单价`，带 A/B/C 分级与来源——没有黑箱 |
| **结构性差额行** | 分项对齐报告总收入，未建模的部分看得见、藏不住 |
| **10 个行业画像**（v0.16） | 打一个 `industry=` 标签即获得分析师直觉默认、行业检查、weak 档情景重定向——软默认，手工覆盖永远优先 |
| **蒙特卡洛 + 龙卷风** | 按 driver 自身的不确定性区间摆动（不是统一百分比），找出真正驱动收入的假设——纯标准库 |
| **诚实回测** | Naive/Linear/CAGR/Holt/ARIMA + 画像形状方法的外样本 sMAPE；[验证报告](docs/profile-validation.md)连零结果一起发表 |
| **数据适配器**（可选 extra） | SEC EDGAR / A 股 tushare / 港股 akshare / Q4 IR PDF——真实财报直通 driver 历史 |
| **Excel / Word 输出** | 带公式的模型工作簿；带图表的方法论备忘录 |
| **LLM 分部抽取** | 年报文本 → 分部骨架（LLM 可注入，测试无需 key） |

### 深入专题（每个都有文档 + 可运行示例）

- **行业适配**——适配矩阵与 NVDA/立讯自然实验 →
  [文档](docs/industry-fit-analysis.md) ·
  [examples/industry_demo](examples/industry_demo/)
- **画像验证**——预注册的 244 家公司检验 →
  [文档](docs/profile-validation.md) ·
  [examples/profile_validation](examples/profile_validation/)
- **新闻冲击验证**——8-K 事件能预测收入吗？（剧透：不能，这本身就是发现）→
  [文档](docs/news-impact-validation.md)
- **回测**——自适应方法 vs driver 结构，真实数据 →
  [examples/backtest_demo](examples/backtest_demo/)
- **真实数据 demo**——NVDA（SEC 季度粒度）、立讯/德赛西威（A 股 20 年）、
  智谱 ARR 阶梯 → [examples/](examples/)

## 安装

核心零依赖，按需装 extra：

```bash
pip install revenue-model-builder                 # 核心，零依赖
pip install revenue-model-builder[excel]          # openpyxl
pip install revenue-model-builder[docx]           # python-docx + matplotlib
pip install revenue-model-builder[backtest,data]  # statsmodels + akshare
```

Python 3.9–3.13 · MIT 许可证 ·
[文档站](https://ljftwq-dev.github.io/revenue-model-builder/) ·
[更新日志](CHANGELOG.md)

## 设计原则

五条硬规则，结构化强制：结构性差额行 · A/B/C 数据分级 · 增量式（非增长率）
渗透率外推 · 确定性金字塔 · 历史优先工作流 →
[docs/design-principles.md](docs/design-principles.md)

*研究/教育工具，非投资建议——见 [DISCLAIMER](DISCLAIMER)。*

## 路线图

- **v0.18（数据之锚）**：Damodaran 行业基准接入画像检查——阈值变成引用
- **v0.19（体验）**：基于回测指纹的画像自动推荐；画像目录页

**已发布——v0.17（数学内核）**：订阅基数的流失存活动力学（`基数×(1+毛增) − 基数×churn`
成为 saas/telecom 默认，附带"ARPU 增长救不了萎缩基数"的净流失检查）；
DampedTrend + DeceleratingCAGR 从预注册验证毕业进标准回测电池（7 方法）；
`forecast_segment` 手工覆盖修复；CI 挂 G1 代码门控（ruff 固定规则集 + 内核
mypy）；金融 weak 档补 FIG 教学共识引用。

完整历史：[CHANGELOG.md](CHANGELOG.md) ·
[Releases](https://github.com/ljftwq-dev/revenue-model-builder/releases)

## 适合谁

想让收入模型变成代码的卖方/PE 同学；研究"预测精度是否是行业机制属性"的
量化；学 driver 建模估值的学生；想逃离表格 sprawl 的 FP&A 团队。欢迎贡献——
[docs](docs/) 本身就是设计记录。

<details>
<summary><b>API 速览</b>（点击展开）</summary>

```python
from revenue_model import (
    Driver, Segment, RevenueModel,            # 核心树
    BASE, PENETRATION, SHARE, PRICE,          # driver 种类
    implied_driver,                           # 用已知收入反标一个 driver
                                              # （优先 PRICE/BASE，避免反解渗透率陷阱）
    forecast_segment, segment_warnings,       # 行业默认 + 检查
    check_segment, list_profiles, resolve_industry,
    simulate_model, simulate_segment, scenarios,   # 蒙特卡洛
    tornado,                                  # 按 driver 的敏感度排序
)

# Driver(名称, 种类, {年份: 值}, level="A"|"B"|"C", unit=..., source=...)
# Segment(名称, base=..., penetration=..., share=..., price=...,
#         reported_revenue={...}, industry="saas_subscription" | "40" | "银行")
# Segment.revenue(年份) -> float
# RevenueModel.validate_all() -> [YearResult(分项和, 差额行, 警告)]
# CLI：python -m revenue_model {build, simulate, excel, docx, extract,
#                               sec, akshare, tushare}
```

目录：`revenue_model/`（引擎）· `docs/`（方法论 + 验证报告）· `examples/`
（NVDA、立讯、行业 demo、画像验证、回测、ARR 阶梯）· tests（303 个，
纯标准库 CI）。

</details>
