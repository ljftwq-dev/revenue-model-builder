# 赴美前优化设计：随机过程收入建模（v0.2 → v0.3）

> 状态：**Brainstorming 定稿，待实现**
> 日期：2026-07-28
> 决策来源：5 轮 brainstorming（开源目标 / 投入节奏 / 杀手锏 / 三阶段编排 / 有界性方案）
> 关联：[design-principles.md](../design-principles.md)、[proposal-segment-extraction.md](../proposal-segment-extraction.md)

---

## 0. 决策摘要

经 5 轮 brainstorming，赴美前交付包定为**单线推进的三阶段**。核心判断：项目的「方法论质量比 agent-memory-engine 更稀缺」（driver-based 收入拆解在 GitHub 几乎空白，全是闭源 FP&A SaaS），下一步用**随机过程**把「方法论引擎」升级为「方法论 + 金融随机建模」，建立差异化学术护城河。

| # | 决策点 | 结论 |
|---|---|---|
| 1 | 开源首要目标 | ① 建立「金融+AI」专业品牌 + ② 全流程开源工程 + ④ 做成机构可用工具（三者协同：工程是地基、可用是深度、品牌是传播面） |
| 2 | 投入节奏 | 赴美前集中冲刺，赴美后转轻量维护/迭代 |
| 3 | 杀手锏 | **B2 随机过程升级**先行（低风险、纯代码、结合专业课），**B1 真实 A 股 demo** 其次 |
| 4 | 三阶段编排 | 深度优先：地基 → B2 做透 → A1 精简 + B1 最小可用 |
| 5 | 有界性方案 | 渗透率/市占率用 **logit-OU**（logistic 扩散），price 用 **GBM** |

**联网搜证（方案合理性背书）**：
- Euler-Maruyama + GBM 蒙特卡洛 = SDE 数值模拟的教科书标准方法（Columbia 讲义、Berkeley DRP 报告、量化博客用它定价 Asian/Lookback 期权）
- Ornstein-Uhlenbeck = 连续时间均值回归建模的基石（Vasicek 利率模型、配对交易都用它）→ 市占率均值回归类比利率建模，有据可依
- 纯 stdlib 做 SDE 可行（Box-Muller 从 uniform 造正态是标准做法，无需 numpy）
- 差异化成立：driver-based forecasting 搜出来全是闭源 FP&A 商业 SaaS（Anaplan/Jedox/CFI），LinkedIn 原话「very few can build driver-based models that actually connect」→ 开源引擎 + 随机过程 = 蓝海

---

## 1. 三阶段路线图

每个子项独立 commit + 测试，延续现有 7-commit 的节奏。

### 阶段一 · 工程地基（约 3-4 天 → `v0.2.0a0`）

| 项 | 内容 | 要点 |
|---|---|---|
| C1 | PyPI 发布 | `pip install revenue-model-builder`；复用 agent-memory-engine 的 build + twine 流程 |
| C2 | 统一 CLI | `python -m revenue_model {build, simulate, excel, extract}` 子命令 |
| C4 | mkdocs + GitHub Pages | 把 design-principles 白皮书上线成文档站（material 主题） |
| C5 | CONTRIBUTING + 模板 | CONTRIBUTING.md + Issue/PR 模板 + Code of Conduct |

### 阶段二 · B2 随机过程模块（约 5-6 天 → `v0.2.0`，核心杀手锏）

详见 §2。

### 阶段三 · A1 精简 pipeline + B1 最小真实 demo（约 4-5 天 → `v0.3.0`）

| 项 | 内容 |
|---|---|
| A1 | `parsed_to_segments()` + driver 模板库 + `RevenueModel.from_report()` 端到端打通 |
| B1 | 1 家真实 A 股公司，**仅历史对齐**（不预测），合规与工作量双控 |

---

## 2. B2 随机过程模块设计（核心）

### 2.1 模块定位与依赖策略

- 新文件 `revenue_model/stochastic.py`，标记 `experimental`
- **不动** `monte_carlo.py`——现有 uniform 蒙特卡洛保留为「零依赖基线」，stochastic 是上层增强
- **坚持纯 stdlib**（Box-Muller + Euler-Maruyama + 手写 Cholesky），保住 README `dependencies: 0` badge
- 两条并行路径：① 确定性 driver + uniform 蒙特卡洛（现有）；② 随机过程 driver（新增）

### 2.2 核心抽象

现有 `Driver` 是「确定性时间序列」（`values: Dict[year→value]`）。新增对偶 `StochasticDriver`——描述 driver 如何随时间**随机演化**：

```python
class StochasticDriver(Protocol):
    def simulate(self, years: list[int], n: int = 10000, seed: int = 0) -> list[Path]
    # Path = list[float]，n 条路径，每条是各年样本
```

三个具体实现，按 driver 性质配 SDE（伊藤形式）：

| 实现 | 配哪个 driver | SDE | 选择理由 |
|---|---|---|---|
| `GBMDriver(S0, μ, σ)` | price 单价 | $dS = \mu S\,dt + \sigma S\,dW$ | 价格 ≥0、对数正态，经典资产价格模型 |
| `LogitOUDriver(p0, θ, μ_bar, σ)` | penetration / share | $\mathrm{logit}(p)\sim\text{OU},\ p=\frac{1}{1+e^{-y}}$ | 天然 (0,1) 有界、均值回归、契合 S 曲线 |
| `correlated(drivers, ρ)` | 相关性层 | Cholesky 分解共享相关布朗运动 | 捕捉 driver 间相关性（如 base 与 penetration 负相关） |

### 2.3 数值方法（纯 stdlib）

**① Box-Muller 变换** —— `random.random()` 的 uniform 转标准正态：
$$Z_1 = \sqrt{-2\ln U_1}\cos(2\pi U_2),\quad Z_2 = \sqrt{-2\ln U_1}\sin(2\pi U_2)$$

**② Euler-Maruyama 离散化** —— 统一离散所有 SDE（$Z\sim\mathcal N(0,1)$）：
$$\Delta X = a(X,t)\Delta t + b(X,t)\sqrt{\Delta t}\cdot Z$$
GBM 落地：$S_{t+\Delta t} = S_t(1 + \mu\Delta t + \sigma\sqrt{\Delta t}\,Z)$。统一用 EM（简单、可推广），不逐过程求精确解。

**③ 手写 Cholesky** —— 相关矩阵 $\Sigma=LL^\top$，独立正态向量 $Z$ 经 $LZ$ 变相关。driver 维度小（2-4），纯 stdlib 三重循环，性能无压力。

### 2.4 有界性决策：logit-OU

**问题**：OU 过程 $dx=\theta(\mu-x)dt+\sigma dW$ 生成正态分布，市占率/渗透率用它可能跑出 $[0,1]$——而渗透率物理上不可能 >100%。

**方案**：**logit-OU（logistic 扩散）**——对 $\mathrm{logit}(p)$ 跑 OU，再用 sigmoid 映射回 $(0,1)$：
$$y = \mathrm{logit}(p)\sim\text{OU},\qquad p = \frac{1}{1+e^{-y}} \in (0,1)$$

**对比备选（决策记录）**：
- **Jacobi / Wright-Fisher 扩散** $dx=\theta(\mu-x)dt+\sigma\sqrt{x(1-x)}\,dW$：理论最纯（Wright-Fisher 来自群体遗传、Jacobi 用于利率价差），但需独立实现、参数估计更难
- **OU + 软截断**：5 行最省事，但破坏统计性质、理论不纯

**选 logit-OU 的理由**：天然有界 + 复用 OUDriver（加变换层）+ 直觉契合 S 曲线（logistic）。市占率 share 同样在 $(0,1) 且均值回归，统一用 logit-OU，代码机制一致。

### 2.5 API 草案

```python
# revenue_model/stochastic.py  (experimental, pure stdlib)
from revenue_model.stochastic import (
    GBMDriver,         # price:      dS = μS dt + σS dW
    LogitOUDriver,     # pen/share:  logit(p)~OU → sigmoid，天然 (0,1)
    correlated,        # Cholesky → 共享相关布朗运动
    simulate_revenue,  # 随机路径 → 收入分布
)

price = GBMDriver(S0=650, mu=0.03, sigma=0.08)
pen   = LogitOUDriver(p0=0.09, theta=1.5, mu_bar=logit(0.20), sigma=0.25)  # 长期趋近 20%
share = LogitOUDriver(p0=0.14, theta=2.0, mu_bar=logit(0.18), sigma=0.20)
bundle = correlated([price, pen, share],
                    rho=[[1, -.2, -.3], [-.2, 1, .1], [-.3, .1, 1]])
mc = simulate_revenue(segment, 2027, bundle, n=20000)   # → MCResult
```

### 2.6 数据流

```
StochasticDriver.simulate(years, n)
        ↓  n 条路径（每条 = 各年样本）
   代入 segment.revenue(year)
        ↓  每条路径一个收入
   收入分布 → MCResult（复用 percentiles / scenarios）
```

**不替代** `monte_carlo.py`，是并行路径。`MCResult` / `scenarios()` 完全复用，零浪费。

### 2.7 测试策略（解析解验证 —— 证明数值对，不是「能跑就行」）

| 过程 | 解析解基准 | 断言 |
|---|---|---|
| GBM | $E[S_T]=S_0 e^{\mu T}$，$\mathrm{Var}[\ln S_T]=\sigma^2 T$ | 模拟均值/方差相对误差 < 3% |
| LogitOU | $p\in(0,1)$ 恒成立；长期均值 $\approx\sigma(\mu_{bar})$ | 路径全程有界 + 长期均值逼近 |
| correlated | 输入 $\rho$ | 样本相关系数 $\approx\rho$ |

固定 `seed` + 容差断言，CI 无需任何外部依赖。

### 2.8 文档更新

- `design-principles.md` 新增「随机过程层」章节（**全部 LaTeX SDE**，沿用本项目新立的公式规范）
- README 加 stochastic 示例，标 `experimental`
- `__init__` 延迟导出 stochastic（避免实验模块影响核心导入）

---

## 3. 阶段一范围（工程地基）

- **C1 PyPI**：`pyproject.toml` 已就绪（零依赖核心 + `[excel]`/`[dev]` extras），补 `[project.urls]` 指向 GitHub/docs，`python -m build` + `twine upload`
- **C2 CLI**：新增 `revenue_model/__main__.py`，argparse 子命令分发到 demo/excel_builder/extractor
- **C4 mkdocs**：`mkdocs.yml` + `docs/` 复用现有 markdown，GitHub Actions 自动部署 Pages
- **C5**：CONTRIBUTING.md（开发流程 + 测试 + commit 规范）、.github/ISSUE_TEMPLATE/、CODE_OF_CONDUCT.md

---

## 4. 阶段三范围（A1 + B1）

### A1 · 端到端 pipeline（精简版）
- `parsed_to_segments(parsed) -> list[Segment]`：把 extractor 抽出的 dict（driver_type + hints）套进 base×pen×share×price
- driver 模板库 `templates.py`：proposal §5 的 6 类（hardware/software/service/advertising/financial/retail）落成配置
- `RevenueModel.from_report(text, api_key)`：一行串起 extract → to_segments → validate

### B1 · 最小真实 demo（合规与工作量双控）
- 选 1 家业务清晰、主营披露颗粒度好的 A 股（消费电子/软件/半导体类）
- **仅历史对齐**（不做预测）——把非法荐股风险降到最低
- 守 [DISCLAIMER.md](https://github.com/ljftwq-dev/revenue-model-builder/blob/main/DISCLAIMER.md) 三道防线：免费开源、不出买卖建议/目标价/评级、引用标来源+页码
- 真实数据**不进主仓**（建议子仓或 release 附件），主仓保持虚构 NovaTech

---

## 5. 版本规划

```
v0.2.0a0  ← 阶段一（地基：PyPI/CLI/mkdocs/CONTRIBUTING）
v0.2.0    ← 阶段二（B2 随机过程模块）
v0.3.0    ← 阶段三（A1 pipeline + B1 最小真实 demo）
```

---

## 6. 后续（赴美后，轻量维护）

- B1 扩展：多家公司、加入预测期
- C3 Streamlit 交互 app（网页调 driver 滑块看收入分布，传播力）
- 多市场数据源适配器（A股 tushare / 美股 yfinance / 港股）
- OU 参数的历史拟合（θ/μ/σ 的最大似然估计）
- 相关性矩阵的历史估计（替代当前主观设定）
- PyPI 正式稳定版（stochastic 去 experimental 标记）

---

## 附 · Brainstorming 决策记录

5 轮问答的关键转折：

1. **开源目标**（多选）→ 品牌 + 工程 + 可用工具，三者协同
2. **投入节奏** → 赴美前集中冲刺（8 月赴美 UIUC 是硬约束）
3. **杀手锏** → 两个都要，先 B2（低风险）后 B1
4. **编排** → 深度优先（单线推进质量最稳，B2 能讲深、B1 控风险）
5. **有界性** → logit-OU（工程优雅、复用、契合 S 曲线；放弃理论更纯的 Jacobi）

*本设计由 GLM 老师与用户经 brainstorming 共同定稿，2026-07-28。*
