"""revenue-model-builder · Streamlit 交互 app（C3）。

把 B3 的四张图做成可交互：左侧调每个 driver 的区间滑块，右侧实时看收入
分布、龙卷风、瀑布、历史+预测趋势如何变化。默认载入立讯精密真实 demo
（公开年报数据）。

运行：    streamlit run examples/streamlit_app.py
依赖：    pip install -e ".[viz]"   且   pip install streamlit

声明：数据来自公开年报（立讯精密 002475）。本 app 仅供研究 / 教育，
非投资建议。
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "examples", "luxun-real-demo"))

import matplotlib.pyplot as plt
import streamlit as st

from revenue_model import simulate_segment, tornado, scenarios
from revenue_model.viz import (
    plot_revenue_distribution, plot_tornado, plot_waterfall,
    plot_forecast,
)
from luxun_demo import build_luxun, add_forecast, FORECAST_YEARS

# Guard: 必须 `streamlit run` 启动；直接用 python 运行会刷一堆 ScriptRunContext
# 警告且 app 不渲染。用错方式时打印正确命令并退出。
from streamlit.runtime.scriptrunner import get_script_run_ctx
if get_script_run_ctx() is None:
    print("=" * 64)
    print("这个 app 必须用 streamlit 启动，不能直接用 python 运行。")
    print("在终端执行：")
    print(f'  streamlit run "{os.path.abspath(__file__)}"')
    print("=" * 64)
    raise SystemExit(0)

st.set_page_config(page_title="收入模型可视化", page_icon="📊", layout="wide")


@st.cache_data
def load_model():
    """默认立讯；架构上换模型只需改这里（返回一个 RevenueModel）。"""
    m = build_luxun()
    add_forecast(m)
    return m


model = load_model()

st.title("📊 收入拆分模型 · 交互可视化")
st.caption(
    f"{model.company}（002475）· driver-based 收入预测 · 研究/教育用途，非投资建议"
)

# ---- sidebar: 参数 + driver 区间 ----
with st.sidebar:
    st.header("参数设置")
    seg_names = [s.name for s in model.segments]
    seg_name = st.selectbox("业务 segment", seg_names, index=0)
    seg = next(s for s in model.segments if s.name == seg_name)

    years = sorted(seg.base.years())
    default_year = FORECAST_YEARS[0] if FORECAST_YEARS[0] in years else years[-1]
    year = st.selectbox("目标年份", years, index=years.index(default_year))

    n = st.slider("蒙特卡洛模拟次数", 1000, 50000, 10000, step=1000)

    st.markdown("**driver 区间**（默认按 driver 类别：价格/份额不确定性 > 市场基数/渗透率）")
    kind_spread = {"base": 0.08, "penetration": 0.10, "share": 0.25, "price": 0.30}
    ranges = {}
    for d in seg.drivers():
        v = d.get(year)
        spread = kind_spread[d.kind]
        lo_b, hi_b = v * 0.7, v * 1.3
        if d.kind in ("penetration", "share"):  # bounded
            hi_b = min(hi_b, 1.0)
        low, high = st.slider(
            f"{d.name} [{d.kind}]", float(lo_b), float(hi_b),
            (float(v * (1 - spread)), float(v * (1 + spread))),
            key=f"{d.name}_{year}",
        )
        ranges[d.name] = (low, high)
    st.caption("💡 拖动滑块改 driver 区间，右侧所有图实时重算。")

# ---- 计算 ----
mc = simulate_segment(seg, year, ranges, n=n, seed=0)
items = tornado(seg, year, ranges)
scen = scenarios(mc)

# ---- 指标卡 ----
c1, c2, c3, c4 = st.columns(4)
c1.metric("中位收入", f"{mc.median / 100:.0f} 亿")
c2.metric("P5（悲观）", f"{mc.percentiles['p5'] / 100:.0f} 亿")
c3.metric("P95（乐观）", f"{mc.percentiles['p95'] / 100:.0f} 亿")
c4.metric("标准差", f"{mc.stdev / 100:.0f} 亿")

st.markdown("---")

# ---- 收入分布 ----
st.subheader(f"① 收入分布 · {seg.name} {year}年")
fig = plt.figure(figsize=(10, 5))
plot_revenue_distribution(mc, scenarios=scen, ax=fig.gca())
fig.tight_layout()
st.pyplot(fig, width="stretch")
plt.close(fig)

# ---- 龙卷风 + 瀑布 ----
col_l, col_r = st.columns(2)
with col_l:
    st.subheader("② 龙卷风（敏感度）")
    fig = plt.figure()
    plot_tornado(items, ax=fig.gca())
    fig.tight_layout()
    st.pyplot(fig, width="stretch")
    plt.close(fig)
with col_r:
    st.subheader("③ 瀑布图（上行累积）")
    fig = plt.figure()
    plot_waterfall(items, ax=fig.gca())
    fig.tight_layout()
    st.pyplot(fig, width="stretch")
    plt.close(fig)

# ---- 趋势 ----
st.subheader("④ 历史（实线）+ 预测（虚线）收入轨迹")
fig = plt.figure(figsize=(11, 5.5))
plot_forecast(model, forecast_years=FORECAST_YEARS, ax=fig.gca())
fig.tight_layout()
st.pyplot(fig, width="stretch")
plt.close(fig)

with st.expander("Bear / Base / Bull 情景表"):
    st.dataframe(
        [{"情景": s.name, "收入(亿)": round(s.revenue / 100, 0),
          "分位": s.percentile} for s in scen],
        hide_index=True,
    )
