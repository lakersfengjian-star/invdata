# -*- coding: utf-8 -*-
"""长鑫科技（CXMT）科创板 IPO 招股说明书精华摘要 - 一页 PDF"""
import os, sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.executable).parent.parent.parent))
from daimon_runtime import setup_plot
setup_plot()

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, Image, KeepTogether)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

OUT_DIR = Path(__file__).resolve().parents[1] / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PDF_PATH = OUT_DIR / "长鑫科技IPO招股说明书精华摘要.pdf"
CHART_PATH = OUT_DIR / "cxmt_finance_chart.png"

regular_font = os.environ.get('DAIMON_CJK_FONT_REGULAR')
bold_font = os.environ.get('DAIMON_CJK_FONT_BOLD')
pdfmetrics.registerFont(TTFont('DaimonCJK', regular_font))
pdfmetrics.registerFont(TTFont('DaimonCJK-Bold', bold_font))
pdfmetrics.registerFontFamily('DaimonCJK', normal='DaimonCJK', bold='DaimonCJK-Bold',
                              italic='DaimonCJK', boldItalic='DaimonCJK-Bold')

# ---------- 图表：营收 / 归母净利 / 毛利率 ----------
years = ["2023", "2024", "2025", "2026Q1"]
revenue = [90.87, 241.78, 617.99, 508.00]          # 亿元
profit  = [-163.40, -71.45, 18.75, 247.62]          # 归母净利，亿元
margin  = [-2.19, 5.00, 41.02, None]                # 主营毛利率 %

fig, ax1 = plt.subplots(figsize=(7.6, 2.9))
x = np.arange(len(years)); w = 0.36
b1 = ax1.bar(x - w/2, revenue, w, color="#2f5f8f", label="营业收入（亿元）")
b2 = ax1.bar(x + w/2, profit, w, color="#c0504d", label="归母净利润（亿元）")
ax1.axhline(0, color="#888", lw=0.8)
ax1.set_xticks(x); ax1.set_xticklabels(years, fontsize=10)
ax1.tick_params(axis='y', labelsize=9)
for rects in (b1, b2):
    for r in rects:
        v = r.get_height()
        ax1.text(r.get_x() + r.get_width()/2, v + (12 if v >= 0 else -30),
                 f"{v:,.0f}", ha='center', fontsize=8.5, color="#333")
ax2 = ax1.twinx()
mx = [i for i, m in enumerate(margin) if m is not None]
my = [m for m in margin if m is not None]
ax2.plot(mx, my, "o-", color="#e8a33d", lw=1.8, label="主营业务毛利率（右轴）")
for xi, yi in zip(mx, my):
    off = 4 if yi >= 10 else -7
    ax2.text(xi, yi + off, f"{yi:.1f}%", ha='center', fontsize=8.5, color="#b07818")
ax2.set_ylim(-20, 60); ax2.tick_params(axis='y', labelsize=9)
h1, l1 = ax1.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
ax1.legend(h1 + h2, l1 + l2, loc='upper left', fontsize=8.5, frameon=False)
ax1.set_title("业绩爆发：2025 年扭亏为盈，2026Q1 单季归母净利 247.6 亿元", fontsize=11, pad=8)
fig.tight_layout()
fig.savefig(CHART_PATH, dpi=160, bbox_inches="tight")
plt.close(fig)

# ---------- PDF ----------
NAVY = HexColor("#1f3a5f"); GRAY = HexColor("#666666"); BODY = HexColor("#333333")

def st(name, **kw):
    base = dict(fontName='DaimonCJK', fontSize=8.8, leading=12.6, textColor=BODY)
    base.update(kw); return ParagraphStyle(name, **base)

s_title = st('t', fontName='DaimonCJK-Bold', fontSize=17, leading=21, textColor=NAVY, alignment=1)
s_sub   = st('s', fontSize=9, leading=12, textColor=GRAY, alignment=1)
s_h     = st('h', fontName='DaimonCJK-Bold', fontSize=10.5, leading=14, textColor=NAVY,
             spaceBefore=5, spaceAfter=2)
s_b     = st('b')
s_note  = st('n', fontSize=7.6, leading=10, textColor=GRAY)

def P(txt, s=s_b): return Paragraph(txt, s)

story = []
story.append(P("长鑫科技（CXMT）科创板 IPO 招股说明书精华摘要", s_title))
story.append(Spacer(1, 2))
story.append(P("长鑫科技集团股份有限公司 · 上交所科创板（2025-12-30 受理，科创板预先审阅机制首单） · 摘要日期：2026-07-26", s_sub))
story.append(Spacer(1, 4))

# 发行概况 + 公司定位（两栏表）
info = Table([
    [P("<b>发行概况</b>", s_h), P("<b>公司定位</b>", s_h)],
    [P("• 拟发行 ≤106.22 亿股（超额配售前），占发行后总股本 ≥10%<br/>"
       "• 拟募资 <b>295 亿元</b>：75 亿晶圆产线技改 + 130 亿 DRAM 技术升级 + 90 亿前瞻研发<br/>"
       "• 上市标准：科创板第四套（预计市值≥30亿 + 年营收≥3亿）<br/>"
       "• 保荐：中金公司 + 中信建投；审计：德勤<br/>"
       "• 无控股股东、无实际控制人", s_b),
     P("• 中国规模最大、布局最全的 DRAM IDM 企业，合肥/北京 3 座 12 英寸晶圆厂<br/>"
       "• Omdia：产能、出货量、销售额均为<b>中国第一、全球第四</b>；2025Q4 全球销售额份额 <b>7.67%</b><br/>"
       "• 产品覆盖 DDR4/DDR5、LPDDR4X/LPDDR5/5X（晶圆/芯片/模组）<br/>"
       "• 客户：阿里云、字节跳动、腾讯、联想、小米、荣耀、OPPO、vivo 等<br/>"
       "• 2025 年产能利用率 95.73%；专利境内 3,929 件 + 境外 3,043 件", s_b)],
], colWidths=[8.6*cm, 8.6*cm])
info.setStyle(TableStyle([
    ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ('LINEABOVE', (0,0), (-1,0), 1.2, NAVY),
    ('LINEBELOW', (0,-1), (-1,-1), 1.2, NAVY),
    ('TOPPADDING', (0,0), (-1,-1), 3), ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ('LEFTPADDING', (0,0), (-1,-1), 2), ('RIGHTPADDING', (0,0), (-1,-1), 8),
]))
story.append(info)

# 核心财务表
story.append(P("<b>核心财务数据</b>（单位：亿元人民币）", s_h))
fin = [
    ["项目", "2023", "2024", "2025", "2026Q1", "2026H1E"],
    ["营业收入", "90.87", "241.78", "617.99", "508.00 (+719%)", "1,100–1,200"],
    ["归母净利润", "-163.40", "-71.45", "18.75（扭亏）", "247.62", "500–570"],
    ["主营业务毛利率", "-2.19%", "5.00%", "41.02%", "—", "—"],
    ["研发投入（占营收比）", "46.70 / 51.4%", "63.41 / 26.2%", "95.93 / 15.5%", "—", "—"],
    ["经营现金流净额", "-72.72", "68.97", "365.20", "425.66", "—"],
]
t = Table([[P(f"<b>{c}</b>", s_b) if i == 0 else P(c, s_b) for c in row] for i, row in enumerate(fin)],
          colWidths=[4.1*cm, 2.5*cm, 2.5*cm, 2.9*cm, 2.6*cm, 2.6*cm])
t.setStyle(TableStyle([
    ('LINEABOVE', (0,0), (-1,0), 1.2, NAVY),
    ('LINEBELOW', (0,0), (-1,0), 0.6, NAVY),
    ('LINEBELOW', (0,-1), (-1,-1), 1.2, NAVY),
    ('TOPPADDING', (0,0), (-1,-1), 2.5), ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
    ('LEFTPADDING', (0,0), (-1,-1), 2),
]))
story.append(t)
story.append(P("注：2023–2025 年营收复合增速 160.78%；2026Q1 数据经德勤审阅，2026H1 预告未经审计/审阅。截至 2025 年末总资产 3,367.85 亿元，合并资产负债率 54.24%。", s_note))

# 图表
story.append(Spacer(1, 3))
story.append(Image(str(CHART_PATH), width=17.2*cm, height=6.5*cm))

# 股东 + 风险（两栏）
tail = Table([
    [P("<b>主要股东（发行前）</b>", s_h), P("<b>核心风险提示</b>", s_h)],
    [P("• 清辉集电 21.67%（第一大股东）<br/>"
       "• 大基金二期 9.80%、合肥集鑫（员工持股）8.37%、安徽省投 8.88%<br/>"
       "• 阿里、腾讯、小米产投、兆易创新（0.95%，董事长朱一明任其董事长）、人保、国调基金、君联资本等", s_b),
     P("• <b>累计未弥补亏损 -366.5 亿元</b>，短期内无法现金分红<br/>"
       "• DRAM 强周期：2024/2025 年产品均价 +55%/+34%，行业转弱将直接冲击业绩<br/>"
       "• 固定资产 1,830 亿元（占总资产 54%），折旧压力大<br/>"
       "• 前五大客户收入占比约 68%，集中度偏高<br/>"
       "• 技术与三星/海力士/美光仍有差距；研发、人才与知识产权风险", s_b)],
], colWidths=[8.6*cm, 8.6*cm])
tail.setStyle(TableStyle([
    ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ('LINEABOVE', (0,0), (-1,0), 1.2, NAVY),
    ('LINEBELOW', (0,-1), (-1,-1), 1.2, NAVY),
    ('TOPPADDING', (0,0), (-1,-1), 3), ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ('LEFTPADDING', (0,0), (-1,-1), 2), ('RIGHTPADDING', (0,0), (-1,-1), 8),
]))
story.append(Spacer(1, 3))
story.append(tail)
story.append(Spacer(1, 4))
story.append(P("资料来源：长鑫科技集团股份有限公司《首次公开发行股票并在科创板上市招股说明书》（上交所披露，报告期 2023–2025 年度）；Omdia。本摘要仅供研究参考，不构成投资建议。", s_note))

doc = SimpleDocTemplate(str(PDF_PATH), pagesize=A4,
                        topMargin=1.2*cm, bottomMargin=1.0*cm,
                        leftMargin=1.6*cm, rightMargin=1.6*cm,
                        title="长鑫科技IPO招股说明书精华摘要", author="投研助手")
doc.build(story)
print("PDF:", PDF_PATH, "pages check...")
from pypdf import PdfReader
print("pages:", len(PdfReader(str(PDF_PATH)).pages))
