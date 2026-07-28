# Proposal: 主营业务抽取 → 多业务预测 → 汇总

> 状态：**设计提案（Draft）**，待 review 定稿后再实现。
> 关联：把单 segment 模型升级为「从年报自动长出多个 segment」的端到端工作流。

## 0. TL;DR

把 sell-side 的 **segment revenue build-up**（分业务线搭建收入）工程化：从年报抓
3-5 个主营业务 → 每个 segment 独立 driver-based 预测 → 汇总成公司整体预测。

- **引擎层已就绪**：`RevenueModel(segments=[...], total_revenue)` + residual + 蒙特卡洛
  + tornado 本就是多 segment 设计。NovaTech demo 已是 2 segment。
- **瓶颈在「年报 → 主营识别」**：这是本提案的核心，也是相对 market-sizing prompt 生态
  （全是 prompt、无引擎）的差异化护城河。
- **务实路线 = 半自动脚手架**：LLM 抽 segment 骨架 + driver 候选，C 级数值人工定。
  不追求取代分析师，而是让方法论显式、可审计、可复用。

---

## 1. 为什么做

- **单 segment 颗粒度太粗**：把整家公司塞进一个 driver tree，解释力差、假设不可辩护。
- **不同业务 driver 结构不同**：硬件看「销量×ASP」、软件看「订阅数×ARPU×续费率」、
  服务看「产能×利用率×单价」——混在一个 segment 会失真。
- **80/20 原则**：抓 3-5 个覆盖 **70-80% 收入**的核心业务，其余进 residual。
  追求 100% 建模要么 C 级堆叠、要么反推失真（违反 [design-principles](design-principles.md)
  Principle 1）。抓大放小是专业做法。

---

## 2. 数据源：A 股年报的「主营业务分析」

A 股年报（披露框架：《公开发行证券的公司信息披露内容与格式准则第2号》）相关章节：

| 位置 | 内容 | 价值 |
|---|---|---|
| 第四节「经营情况讨论与分析」→ 主营业务分析 | 分行业/分产品/分地区的**营业收入、营业成本、毛利率、同比** | ★ 主数据源 |
| 主营业务分行业/分产品情况表 | 结构化表格：业务名、收入、占比、YoY、毛利率 | ★ 直采 |
| 附注·收入分类 | 更细的产品/区域拆分 | 细化用（解析难） |

**关键字段**：业务名、收入（元）、收入占比、YoY、毛利率。

**多市场差异（后续）**：
- 港股年报「分部资料」（IFRS 8 segment information）——口径偏地理/业务板块
- 美股 10-K segment reporting（ASC 280）——结构最规整但口径不同
- → 先聚焦 A 股，模板跑通后再扩多市场。

---

## 3. 端到端工作流（Pipeline）

```
年报 PDF
   │  [1] 文本+表格解析（PyMuPDF 文字层 + pdfplumber/camelot 抠表）
   ▼
「主营业务分析」章节文本 + 分业务表格（markdown）
   │  [2] LLM 结构化抽取（见 §4 prompt / schema）
   ▼
segment 骨架 JSON：[{name, revenue_history, share, yoy, gross_margin, driver_type, hints}]
   │  [3] driver 模板匹配（见 §5 模板库）
   ▼
每个 segment 的 driver tree 候选（base/penetration/share/price 的占位 + 来源线索）
   │  [4] 人工确认/补充（C 级数值、预测假设）← ABC 分级在此落地
   ▼
完整的 Driver / Segment 对象
   │  [5] 接入 RevenueModel + 蒙特卡洛 + tornado
   ▼
多业务预测 + 汇总（residual 自动吸收未建模业务）
```

---

## 4. LLM 抽取：schema 与 prompt

**输入**：主营业务分析章节文本 + 分业务表格（转 markdown）。
**输出**：严格 JSON（用 structured output / function calling 约束）。

```json
{
  "company": "示例科技",
  "fiscal_year": 2024,
  "currency": "CNY",
  "segments": [
    {
      "name": "智能汽车软件",
      "revenue": 410000000,
      "share": 0.62,
      "yoy": 0.35,
      "gross_margin": 0.72,
      "driver_type": "software_subscription",
      "driver_hints": {
        "market_base_source": "年报披露客户数/装机量",
        "penetration_source": "行业第三方（高工/IDC）",
        "price_source": "年报均价或对标竞品"
      },
      "evidence": "「报告期内智能汽车软件收入 4.10 亿元，同比+35%」(年报 p.28)",
      "confidence": "A"
    }
  ],
  "unmodeled": "其他业务（零散项，合计占比<8%）→ 进 residual"
}
```

**prompt 要点**：
- **few-shot**：给 1-2 个标注样例（含一个多业务、一个单业务的）。
- **受控词表**：`driver_type` 必须从 §5 模板库枚举里选，禁止自由发挥。
- **占比求和校验**：要求 `Σ share + unmodeled_share ≈ 1`，否则自查。
- **with evidence**：每个数字必须带 `evidence`（引用原文片段+页码），抑制幻觉。
- **confidence 自评**：A/B/C 自标，与引擎的 data grading 对齐。

**模型与密钥**：用智谱 GLM / OpenAI 兼容 endpoint；API key 走 `secrets_loader`
（项目内绝不硬编码；demo 用占位符 `<your-llm-key>`）。

---

## 5. driver 模板库（按业务类型）

每个 segment 自动套用最接近的模板，展开成 4 个 driver 占位：

| `driver_type` | driver tree | 适用 |
|---|---|---|
| `hardware_product` | 市场基数(销量池) × 渗透率 × 市占率 × ASP | 消费电子、汽车零部件、半导体 |
| `software_subscription` | 客户池 × 渗透率 × 市占率 × ARPU ×（续费率→并入 share） | SaaS、授权软件 |
| `service_project` | 产能/人天 × 利用率 × 单价 | IT 服务、外包、工程 |
| `advertising` | 流量(DAU×时长) × ad_load × 市占率 × eCPM | 互联网平台 |
| `financial_interest` | 生息资产规模 × 收益率（映射为 base×price） | 银行、租赁、消金 |
| `retail_store` | 门店数 × 坪效（或 客单价 × 客流） | 连锁零售、餐饮 |

模板存为 Python 配置 / YAML。`driver_type` 选定后自动生成 4 个 `Driver` 占位，
人工只需填数值 + 来源 + ABC 等级。

> 映射约定：所有模板归一到 `base × penetration × share × price` 四因子。
> 例如 `service_project`：base=人天产能、penetration=利用率、share=市占、price=人天单价。

---

## 6. 与现有引擎的衔接

- 抽取的 segment → `Segment(name, base=Driver(...), penetration=..., share=..., price=...)`
- 历史收入填入对应年份 → `RevenueModel.validate_all()` 对齐年报总收入
- **residual 自动 = total − Σ(segments)**，吸收 §4 里 `unmodeled` 的零散业务
- 各 segment 独立跑蒙特卡洛 / tornado → 汇总到 `RevenueModel`
- **ABC 分级的杠杆点**：抽取出的 driver 大量是 C 级（估算），分级天然标记
  「哪些要人工加固、哪些可直接信」——tornado 的 per-driver 区间也据此设宽窄。

---

## 7. 半自动边界（自动 vs 人工）

| 环节 | 自动 | 人工 |
|---|---|---|
| 年报解析 | PDF → 文本/表格 | 校验解析正确（尤其合并单元格/跨页表） |
| segment 识别 | LLM 抽业务列表 + 收入 | 确认业务划分口径（产品/地区/行业维度） |
| driver 结构 | 模板匹配 `driver_type` | 选/调模板 |
| driver 数值（A/B 级） | 从年报/行业库取候选 | 核对来源 |
| driver 数值（C 级） | 给候选区间 | **定值 + 不确定性区间** |
| 预测假设 | 给候选（增量法、确定性金字塔） | **拍板**（政策/产品周期判断） |

**定位**：脚手架，不是全自动。价值在「把分析师的重复劳动（找章节、抄数字、搭结构）
自动化，把判断劳动（C 级估值、预测假设）留给人并强制留痕」。

---

## 8. 难点与风险

| 风险 | 说明 | 对策 |
|---|---|---|
| **PDF 表格解析** | A 股表格格式不统一（合并单元格、跨页），解析成功率非 100% | pdfplumber+camelot 双引擎 + 人工兜底 + 累积规则库 |
| **披露颗粒度不一** | 有的按产品、有的按地区、有的按行业 | LLM 判断「主营」维度；模板支持多维度 |
| **跨年口径变化** | 业务重组、口径调整导致历史序列断裂 | 对齐校验 + 标注「口径变更」断点 |
| **LLM 幻觉** | 可能编造数字 | 强制 `evidence` 引用原文 + 占比求和校验 + A 级回查 |
| **合规** | 真实公司年报开源的著作权 / 非法荐股风险 | 见下方 §8.1（已调研，真实数据可用） |

### 8.1 合规方案（真实 A 股年报可用 — 已调研）

经法律调研（大成律所《证券投资咨询业务合规问题研究》+ 证监会《2001》207 号文 + 刑法 225
条），真实年报**可用**，守住三条边界即可。完整声明见 [DISCLAIMER.md](https://github.com/ljftwq-dev/revenue-model-builder/blob/main/DISCLAIMER.md)。

**两层风险**：
- **著作权（低）**：年报财务数据是**事实**，不受著作权保护，可抽取、存储、开源；叙述文字
  少量引用 + 标来源属合理使用。
- **非法荐股（可控）**：非法经营罪（刑法 225）三要件 = 无资质 + **经营行为（持续有偿获利）**
  + 扰乱市场秩序。本项目**免费开源** → 不满足第②要件（核心护城河）。

**三道防线**：
1. **非经营性**：免费开源、MIT、不收费、不定向推送 → 不构成「经营行为」。
2. **非咨询性**：输出 driver tree / 收入模型，**绝不输出买卖建议 / 目标价 / 投资评级**。
3. **教育 / 研究定位**：归投资者教育与学术研究（同 FinRobot 等开源先例）。

**四条措施**：① 强免责声明（中英，README + 每次输出）；② 数据走公开渠道（巨潮 / 交易所 /
tushare），不大段复制年报叙述原文，引用标来源+页码；③ 输出只到「收入预测 / driver 分析」，
不到「买卖建议」；④ 真实公司作「功能演示数据源」而非「投资结论」。

**红线（绝不触碰）**：收费 / 会员 / 利润分成 ❌ ｜ 目标价 / 评级 / 买卖建议 ❌ ｜ 承诺收益 /
暗示操作 ❌ ｜ 大段复制年报原文 ❌ ｜ 定向荐股推送 ❌。

> ⚠️ 警示案例（廖某案）：以「投资者教育」名义**有偿**提供证券分析被判非法经营罪。律所原话：
> 「无论命名如何，业务实质离不开对具体证券的分析预测…未获资质便有风险」——前提仍是**有偿
> 经营**。这反而强化了防线①（绝不收费）。

---

## 9. 分阶段实施

- **Phase 1（MVP）**：手动喂「主营业务分析」章节文本 → LLM 抽 segment JSON →
  转 `Segment` 对象 → 接 `RevenueModel`。**不做 PDF 解析**（文本人工复制）。
  目标：端到端走通，证明思路。
- **Phase 2**：加 PDF 解析（PyMuPDF + pdfplumber），自动定位主营业务章节。
- **Phase 3**：driver 模板库（§5）+ 自动模板匹配。
- **Phase 4**：多市场（港股 IFRS 8、美股 ASC 280）。

每个 Phase 独立 commit + 测试，保持开源迭代节奏。

---

## 10. 决策记录与开放问题

**已定（2026-07-28 review）**：
- ✅ 市场聚焦：**先 A 股**，多市场（IFRS 8 / ASC 280）放 Phase 4。
- ✅ LLM 选型：**智谱 GLM**（已有 key，走 `secrets_loader`，不硬编码）。
- ✅ MVP 年报样本：**真实 A 股年报**（合规已调研，见 §8.1，可用）。

**待定**：
1. **抽取结果存储**：JSON 文件 / YAML / 直接构造 Python 对象？影响可复现与版本管理。
2. **交互形态**：纯库 API（`extract_segments(text) -> list[Segment]`）还是带 CLI？
3. **模板库归属**：放项目内 `revenue_model/templates/`，还是单独配置文件？
4. **MVP 目标公司**：用哪只 A 股？建议选业务清晰、主营披露颗粒度好的（消费电子 / 软件 / 半导体类）。

---

*本提案由 GLM 老师起草，2026-07-28。Review 定稿后进入 Phase 1 MVP。*
