# -*- coding: utf-8 -*-
"""梁文锋内部讲话观点精简整理 - PDF 文章"""
import os
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

OUT_DIR = Path(__file__).resolve().parents[1] / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PDF_PATH = OUT_DIR / "梁文锋内部讲话观点整理.pdf"

pdfmetrics.registerFont(TTFont('DaimonCJK', os.environ['DAIMON_CJK_FONT_REGULAR']))
pdfmetrics.registerFont(TTFont('DaimonCJK-Bold', os.environ['DAIMON_CJK_FONT_BOLD']))
pdfmetrics.registerFontFamily('DaimonCJK', normal='DaimonCJK', bold='DaimonCJK-Bold',
                              italic='DaimonCJK', boldItalic='DaimonCJK-Bold')

NAVY = HexColor("#1f3a5f"); GRAY = HexColor("#666666"); BODY = HexColor("#333333")
ACCENT = HexColor("#c0504d")

def st(name, **kw):
    base = dict(fontName='DaimonCJK', fontSize=9.6, leading=15.5, textColor=BODY,
                spaceAfter=3)
    base.update(kw)
    return ParagraphStyle(name, **base)

s_title = st('t', fontName='DaimonCJK-Bold', fontSize=18, leading=23, textColor=NAVY, alignment=1, spaceAfter=4)
s_sub   = st('s', fontSize=9, leading=13, textColor=GRAY, alignment=1, spaceAfter=8)
s_h     = st('h', fontName='DaimonCJK-Bold', fontSize=12, leading=16, textColor=NAVY,
             spaceBefore=9, spaceAfter=3)
s_b     = st('b', leftIndent=10, firstLineIndent=-10)
s_note  = st('n', fontSize=8, leading=11.5, textColor=GRAY)
s_quote = st('q', fontName='DaimonCJK-Bold', fontSize=10.5, leading=15, textColor=ACCENT,
             alignment=1, spaceBefore=6, spaceAfter=6)

def P(t, s=s_b): return Paragraph(t, s)

story = [
    P("梁文锋内部讲话观点整理", s_title),
    P("DeepSeek 创始人梁文锋 · 2026 年 5 月投资者交流会（约四小时） · 整理日期：2026-07-26", s_sub),
    HRFlowable(width="100%", thickness=1, color=NAVY, spaceAfter=6),
    P("一句话总纲：<b>克制，是 DeepSeek 最大的战略。</b>不追利润最大化、不抢 C 端流量、不做超级 App、不开源“阉割版”——用一连串的“不”，换取做成 AGI 的最大概率。", s_quote),
]

SECTIONS = [
    ("一、战略主线：只有一条主线，产品是 AGI 的副产物", [
        "现在不是收益最大化的时候。通往 AGI 的路上要经过产品这个台阶，但不需要花太多心思做 C 端、B 端产品；站在技术高位做低一级技术是降维打击，<b>产品是 AGI 路上的副产物</b>。",
        "不在主线上的坚决不做：3D、视频生成、世界模型与智能上限关系不大；多模态对 C 端重要，但只是组件，不是智能本身。幻觉被内部归结为“产品问题”，会解决，但不是重点。",
        "现阶段最重要的是 <b>Coding Agent</b>；国内最合理的做法是全力做通用 Agent，金融、医疗等垂直 Agent 优先级较低。",
    ]),
    ("二、技术路线：CoT → Agent → 持续学习 → AI 自迭代 → 具身智能", [
        "AI 现在不缺品味和直觉，<b>缺的是持续学习的能力</b>。人类能持续学习，而 AI 做同一件事需要给全所有上下文，这几乎不可能——所以下一代模型必须具备持续学习能力，全世界目前都还没有找到好方法。",
        "AGI 路线如爬楼梯：去年的阶梯是 CoT（思维链），今年的阶梯是 Agent，Agent 之后就是持续学习。",
        "持续学习突破后会来到“渐进的奇点”：AI 能完成人类能做的所有事，包括自己研发更前沿的模型（<b>AI 加速 AI</b>）；这一步走完才是具身智能。智能的终点可能是具身——因为人的需求不是电脑，而是人力。",
        "先解决持续学习、再用 AI 辅助做通用智能是最轻松的路线；反过来先做具身是苦活。",
    ]),
    ("三、商业化：只赚合理利润，离彻底商业化很遥远", [
        "API 定价逻辑是<b>“十个月收回设备成本”</b>（约六倍利润），不是利润最大化。一款模型价格降到四分之一时公司群里一片欢呼——让大家都用得起，才是把模型做好的目的。",
        "还有降价空间但不继续降：再降需求也不会增加多少，对公司没更多收入，对社会也没更多价值。",
        "低成本是结果而非口号：架构上持续往更低成本走；算力有限时，计算效率高才能训更大的模型。大公司靠加资源，DeepSeek 优先考虑成本效率。",
        "卖 API 吸引力有限：几个人维护即可，没有客服和销售，用户自己来。<b>一直在商业化，只是不以商业化为目标</b>；哪怕技术冻结、全力卖 API 也够撑起一家上市公司，“但我们有更大的梦想”。",
    ]),
    ("四、开源：是这个规模公司的 Sweet Point", [
        "开源就是让利：对内员工有成就感、公司有凝聚力；对外同行和普通人都受益。AI 最终可能占人类 GDP 的 10%，想独占这个利益一定会被历史抛弃。",
        "开源模型与自部署模型完全一样，不会开源差版本、自用好版本；也不担心别人部署来竞争——创业公司没力量做，大公司难组织，这正是 DeepSeek 这个规模的甜区。",
        "只要你不贪一百倍利润，开源和赚钱就不冲突。第三方自建部署做不到 DeepSeek 的成本，开源反而做大生态蛋糕。",
    ]),
    ("五、行业判断：中美差距在资源不在人才；竞争终局是成本", [
        "中美 AI 差距主要在资源（算力有数量级差距），目前落后 12–18 个月；全面超越不现实，<b>在有取舍的地方超越是可能的</b>。目标：用几分之一的算力把差距缩到 6 个月、3 个月。",
        "人才几乎没有差距——就是同一批人，国内人才不缺；人才短缺是阶段性的。",
        "国内模型公司太多、资源分散，最终一定收敛：每家只拿合理利润的话，两家大公司加两家小公司就够了。<b>大模型公司不可能拿走 AI 行业大部分利润</b>。",
        "竞争终局体现为三点：<b>成本、时间、用户体验</b>。成本第一（同样质量的服务能以什么成本提供），时间第二（早几个月晚几个月不一样），体验有粘性但不本质。Anthropic 超过 OpenAI 是阶段性的，OpenAI 与 Google 未来大概率交替上升。",
        "不想做下一个超级 App、下一个字节或腾讯：“后面还有西瓜，前面的可能都是芝麻。”去年抢 C 端流量、今年抢 To B 收入，都不是 DeepSeek 关心的事。",
    ]),
    ("六、组织与文化：团队稳定是唯一不能退让的底线", [
        "<b>“只要能够保持团队的稳定性，我一定能做成 AGI。”</b>这是最大风险，融资最大的作用就是解除这个风险；不愿与任何大厂小厂成为对手。",
        "组织两条线：从上到下“做正事”（希望不超过员工一半时间），从下到上自由研究。一般不太加班——做研究需要松弛感，且足够聚焦、没那么多事要做。",
        "愿景驱动而非 KPI 驱动：愿景甚至不成文，存在于做事的方法和对待世界的态度里。“一个公司最重要的是愿景。愿景不是墙上的标语，不是怎么说，而是怎么做。”",
        "“一群平凡的人做出了不平凡的事”：两年前成立时没钱、没卡、没知名度、没号召力。除了愿景，并没有非常多其他优势。",
    ]),
    ("七、投资视角要点（整理者注）", [
        "模型层：利润天花板有限、成本为王——利好低成本算力与推理降本链条，警惕模型公司高估值叙事。",
        "算力：中美算力差距是核心矛盾，国产芯片产能问题五年后大概率解决，国产算力替代是长逻辑。",
        "应用层：模型公司主动让利的生态下，应用与 Agent 是价值重分配的方向；终局看具身智能（机器人、人力替代）。",
    ]),
]

for title, points in SECTIONS:
    story.append(P(f"<b>{title}</b>", s_h))
    for i, pt in enumerate(points, 1):
        story.append(P(f"{i}. {pt}"))

story.append(Spacer(1, 8))
story.append(HRFlowable(width="100%", thickness=0.6, color=GRAY, spaceAfter=4))
story.append(P("资料来源：据网络流传的 DeepSeek 投资者交流会（2026 年 5 月 20 日）录音转写精编实录（金融界、华尔街见闻等媒体报道）综合整理，未经梁文锋本人确认，内容可能与原话略有出入；第七部分为整理者投资视角归纳。仅供研究参考，不构成投资建议。", s_note))

def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('DaimonCJK', 8)
    canvas.setFillColor(GRAY)
    canvas.drawCentredString(A4[0] / 2, 1.0 * cm, f"梁文锋内部讲话观点整理 · 第 {doc.page} 页")
    canvas.restoreState()

doc = SimpleDocTemplate(str(PDF_PATH), pagesize=A4,
                        topMargin=1.5*cm, bottomMargin=1.6*cm,
                        leftMargin=1.8*cm, rightMargin=1.8*cm,
                        title="梁文锋内部讲话观点整理", author="投研助手")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
from pypdf import PdfReader
print("PDF:", PDF_PATH, "pages:", len(PdfReader(str(PDF_PATH)).pages))
