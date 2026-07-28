# revenue-model-builder

[![CI](https://github.com/ljftwq-dev/revenue-model-builder/actions/workflows/ci.yml/badge.svg)](https://github.com/ljftwq-dev/revenue-model-builder/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)

**English: [README.md](README.md)**

一个**自下而上的收入预测框架**——把 driver tree
（`市场基数 × 渗透率 × 市占率 × 单价`）变成**可审计**的收入模型，通过一条
结构性的差额行（residual）对齐到年报总收入。

> 市面上的开源金融工具几乎都是**交易/回测**（zipline、backtrader、QuantLib、vnpy）。
> 而卖方分析师、PE 投资经理真正在做的 **driver-based 收入拆解预测**，几乎没有开源实现。
> 本库用最小、可跑的代码，把这个工作流固化下来。

设计上编码了五条踩过坑才总结出的建模铁律（详见
[设计原则白皮书](docs/design-principles.md)）：**结构性差额行**（吸收未建模业务）、
**ABC 数据等级**（可追溯）、**增量法**（渗透率预测不用增速法）、**确定性金字塔**
（预测输入按可知性排序）、**先历史后预测**。

---

## 为什么需要它

一份卖方收入模型，成败在于你能不能**为每一个数字辩护**——"这个渗透率哪来的？为什么
不能再高点？" 手工 Excel 用晦涩的批注回答这个问题。`revenue-model-builder` 把它做成
结构化的：每个 driver 自带可信度等级和来源，差额行是一等公民，对齐校验会在"反推渗透率"
污染预测期之前就把它拦住。

## 核心公式

```
分项收入 = 市场基数 × 渗透率 × 市占率 × 单价
总收入   = Σ(分项) + 差额行          # 差额行吸收未建模业务
```

单位推导：基数（百万辆）× 单价（元）= **百万元**（渗透率、市占率是 [0,1] 的小数）。
所以 `Segment.revenue()` 按定义返回百万元。

## 安装

```bash
pip install -e .                  # 仅核心引擎（纯标准库，零依赖）
pip install -e ".[excel]"         # + openpyxl，用于输出 .xlsx
pip install -e ".[dev]"           # + pytest，用于跑测试
```

## 快速上手

**建模型并校验是否对齐年报总收入：**

```python
from revenue_model import Driver, Segment, RevenueModel, BASE, PENETRATION, SHARE, PRICE

seg = Segment(
    name="舱内-国内",
    base=Driver("中国乘用车销量", BASE, {2022: 22.0, 2023: 23.0},
                level="A", unit="百万辆", source="CAAM"),
    penetration=Driver("DMS 前装渗透率", PENETRATION, {2022: 0.04, 2023: 0.06},
                       level="B", unit="小数", source="高工产业研究院"),
    share=Driver("市占率", SHARE, {2022: 0.10, 2023: 0.12},
                 level="C", unit="小数", source="估算"),
    price=Driver("单价", PRICE, {2022: 600, 2023: 620},
                 level="C", unit="元", source="对标"),
)
model = RevenueModel("DemoCo", [seg], total_revenue={2022: 110.0, 2023: 215.0})

for r in model.validate_all():
    print(r.year, f"分项合计={r.segment_sum:.1f}", f"差额={r.residual:.1f}",
          f"({r.residual_ratio:.0%})", r.warnings)
```

**跑虚构公司 demo**（NovaTech，车载 AI 公司，所有数据均为虚构）：

```bash
python -m revenue_model.demo
```

```
--- 2024 ---
  舱内-国内      :    218.4 百万元
  舱内-海外      :    120.0 百万元
  Σ 分项        :    338.4
  差额行        :     71.6  (17.5%)
  总收入        :    410.0
  [ok] 对齐通过（Σ分项 + 差额 = 总收入）
```

**渲染成带格式的 .xlsx**（需 `[excel]` extra）：

```bash
python -m revenue_model.excel_builder 输出.xlsx
```

Excel 输出实现了 ABC 颜色编码（黑/蓝/红）、IF 保护的收入公式、差额行、以及橙色高亮的
预测区（在历史模型对齐之前留空）。

## 五条设计原则

| # | 原则 | 防止什么 |
|---|---|---|
| 1 | **差额行是结构性设计，绝不反推** | 为了"对齐"而抬高渗透率，污染预测期 |
| 2 | **ABC 数据等级** | 黑箱表格——让每个数字可追溯 |
| 3 | **渗透率用增量法，不用增速法** | 有界变量指数爆炸 |
| 4 | **预测确定性金字塔** | 把所有输入当成同样可知 |
| 5 | **先历史后预测** | 模型还没复现历史就开始预测未来 |

完整推导 + 数值例子：**[docs/design-principles.md](docs/design-principles.md)**。

## API

```python
Driver(name, kind, values, level="C", unit="", source="")
#   kind ∈ {BASE, PENETRATION, SHARE, PRICE};  level ∈ {"A","B","C"}

Segment(name, base, penetration, share, price)
#   .revenue(year) -> float  (百万元)

RevenueModel(company, segments, total_revenue)
#   .validate(year)  -> YearResult   (分项收入、差额、告警)
#   .validate_all()  -> list[YearResult]
```

## 目录结构

```
revenue-model-builder/
├── revenue_model/
│   ├── driver.py        # Driver — 单个因子（基数/渗透/市占/单价）+ ABC 等级
│   ├── segment.py       # Segment — 收入 = 基数 × 渗透 × 市占 × 单价
│   ├── model.py         # RevenueModel — 差额行 + 对齐校验
│   ├── excel_builder.py # 渲染成 .xlsx（ABC 颜色、IF 公式、差额行）
│   └── demo.py          # NovaTech 虚构示例
├── tests/               # 10 个测试 — 公式、校验、差额不变式
├── docs/
│   └── design-principles.md
└── pyproject.toml
```

## 路线图

- [ ] 多市场数据源适配器（A股 tushare / 美股 yfinance / 港股）
- [ ] 从年报文本自动抽取 driver
- [ ] Word 底稿生成器（历史 + 预测叙述，对齐原 skill 的产出）
- [ ] 强制增量法的预测辅助函数（原则 3）
- [ ] PyPI 发布

## 适用人群

卖方研究、PE/VC 投资团队、股票分析师，以及正在学基本面分析的同学——想要一个
**可复用、可审计**的收入建模脚手架，而不是每次都手工重建同样的 Excel 结构。

## 许可证

MIT — 见 [LICENSE](LICENSE)。
