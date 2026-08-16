# -*- coding: utf-8 -*-
"""生成 demo 用的样例 QESA 库(真实 FRED 数据 24 个月裁剪版, 开源可跑)"""
import sqlite3
from datetime import date, timedelta
from pathlib import Path
import requests

OUT = Path(__file__).parent / 'sample_qesa.db'
if OUT.exists():
    OUT.unlink()

SERIES = [
    ('PCOPPUSDM', 'LME Copper Global Price', 'commodity', '$/mt'),
    ('PALUMUSDM', 'LMA Aluminum Global Price', 'commodity', '$/mt'),
    ('DEXCHUS', 'CNY/USD Exchange Rate', 'fx', 'CNY/USD'),
    ('DGORDER', 'Manufacturers New Orders Durable Goods', 'demand', 'million$'),
]

conn = sqlite3.connect(OUT)
conn.executescript('''
CREATE TABLE series_registry (series_id TEXT PRIMARY KEY, name TEXT,
    category TEXT, unit TEXT, frequency TEXT, impact_note TEXT,
    active INTEGER, added_at TEXT, invert INTEGER DEFAULT 0);
CREATE TABLE observations (series_id TEXT, obs_date TEXT, value REAL,
    prev_value REAL, `change` REAL, yoy REAL, ingest_time TEXT,
    PRIMARY KEY (series_id, obs_date));
CREATE TABLE events (event_id TEXT PRIMARY KEY, source TEXT,
    event_type TEXT, event_time TEXT, ref_date TEXT, title TEXT,
    series_id TEXT, category TEXT, direction TEXT, magnitude REAL,
    tag TEXT, payload TEXT, content_hash TEXT);
''')
for sid, name, cat, unit in SERIES:
    r = requests.get(f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}',
                     timeout=30)
    lines = r.text.strip().split('\n')[1:]
    obs = []
    for ln in lines:
        d, v = ln.split(',')
        if v not in ('', '.'):
            obs.append((d, float(v)))
    obs = [o for o in obs if o[0] >= (date.today() - timedelta(days=800)).isoformat()]
    obs.sort()
    prev_year = {}
    last = None
    for d, v in obs:
        prev_v = last[1] if last else None
        yoy = None
        py = prev_year.get(d[5:])
        if py:
            yoy = round(100 * (v - py[1]) / py[1], 4)
        conn.execute('INSERT INTO observations VALUES (?,?,?,?,?,?,?)',
                     (sid, d, v, prev_v,
                      round(v - prev_v, 6) if prev_v else None, yoy, 'sample'))
        prev_year[d[5:]] = (d, v)
        last = (d, v)
    conn.execute('INSERT INTO series_registry VALUES (?,?,?,?,?,?,1,"sample",0)',
                 (sid, name, cat, unit, 'monthly', ''))
conn.commit()
n = conn.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
print(f'sample_qesa.db: {len(SERIES)} series, {n} obs')
conn.close()
