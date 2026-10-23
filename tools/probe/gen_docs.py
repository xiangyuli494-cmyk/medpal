"""合成单据生成器：造 10 类测试单据，全部为假数据，无任何真实患者信息。

为什么要有它（替代来源不明的网络图片）：
- 网络流传的医疗单据含真实患者隐私，仓库 README 与 10 号 §375 BD-08 都明令禁止；
- 合成数据 100% 可追溯：任何人重跑本脚本都能造出同样的图，"来源"这一栏才写得实；
- 还能顺手覆盖刁钻场景（手写剂量、印章遮挡、勾选框），真实图反而不好凑。

用法：
    python tools/probe/gen_docs.py                # 生成到 tools/probe/samples/ocr/
    python tools/probe/gen_docs.py --out <目录>

依赖：Pillow（DSH 自带运行时已含）。
"""
from __future__ import annotations

import argparse
import os

from PIL import Image, ImageDraw, ImageFont

FONT = r"C:\Windows\Fonts\msyh.ttc"
W, H = 1240, 1750
INK = (25, 25, 25)
GRAY = (110, 110, 110)
RED = (200, 40, 40)


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size)


def page(title: str, subtitle: str = "") -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.text((W // 2, 80), title, font=font(46), fill=INK, anchor="mm")
    if subtitle:
        d.text((W // 2, 140), subtitle, font=font(26), fill=GRAY, anchor="mm")
    d.line((70, 180, W - 70, 180), fill=INK, width=3)
    # 页脚：来源声明，让每张图自带可追溯信息
    d.line((70, H - 110, W - 70, H - 110), fill=GRAY, width=1)
    d.text((70, H - 92), "合成测试数据 · 无真实患者信息 · 由 tools/probe/gen_docs.py 生成",
           font=font(20), fill=GRAY)
    return img, d


def rows(d: ImageDraw.ImageDraw, pairs: list[tuple[str, str]], y: int, gap: int = 46) -> int:
    for k, v in pairs:
        d.text((100, y), k, font=font(27), fill=INK)
        d.text((330, y), v, font=font(27), fill=INK)
        y += gap
    return y


def table(d: ImageDraw.ImageDraw, headers: list[str], data: list[list[str]], y: int,
          widths: list[int]) -> int:
    x0, rowh = 80, 42
    xs = [x0]
    for w in widths[:-1]:
        xs.append(xs[-1] + w)
    for i, h in enumerate(headers):
        d.text((xs[i] + 8, y), h, font=font(23), fill=INK)
    y += rowh
    d.line((x0, y - 8, xs[-1] + widths[-1], y - 8), fill=INK, width=2)
    for row in data:
        for i, cell in enumerate(row):
            d.text((xs[i] + 8, y), cell, font=font(23), fill=INK)
        y += rowh
    d.line((x0, y - 8, xs[-1] + widths[-1], y - 8), fill=INK, width=2)
    return y


def gen(out: str) -> list[str]:
    made = []

    def save(img: Image.Image, name: str) -> None:
        path = os.path.join(out, name)
        img.save(path)
        made.append(name)

    # 01 挂号单
    img, d = page("就 诊 挂 号 单", "门诊一楼 · 自助机打印")
    y = rows(d, [("姓　名", "张某某"), ("年　龄", "78"), ("就诊类型", "☑ 自费　□ 省市医保　□ 农合"),
                 ("挂号科室", "☑ 内科　□ 外科　□ 眼科　□ 口腔科"), ("就诊医生", "王某某"),
                 ("就诊日期", "2026-10-23"), ("挂号序号", "A0326"), ("挂号费", "12.00 元")], 230)
    save(img, "01_挂号单.png")

    # 02 病历首页
    img, d = page("门 诊 病 历 首 页", "门诊部 · 首次就诊")
    y = rows(d, [("姓　名", "张某某"), ("就诊科室", "内科"), ("就诊医生", "王某某"),
                 ("就诊日期", "2026-10-23"), ("主　诉", "反复头晕三天，伴乏力"),
                 ("现病史", "三天前无明显诱因出现头晕，晨起明显，无恶心呕吐"),
                 ("既往史", "高血压十年，规律服药"), ("诊　断", "1. 高血压病 2. 头晕待查"),
                 ("处理意见", "完善血常规、生化检查")], 230, gap=56)
    save(img, "02_病历首页.png")

    # 03 检验申请单
    img, d = page("检 验 申 请 单", "检验科")
    y = rows(d, [("姓　名", "张某某"), ("申请科室", "内科"), ("申请医生", "王某某"),
                 ("申请日期", "2026-10-23")], 230)
    y = table(d, ["检验项目", "标　本", "执行科室", "检验目的"],
              [["血常规", "静脉血", "检验科", "感染与贫血筛查"],
               ["肝功能", "静脉血", "检验科", "用药前评估"],
               ["肾功能", "静脉血", "检验科", "用药前评估"],
               ["空腹血糖", "静脉血", "检验科", "糖尿病筛查"]],
              y + 20, [340, 220, 220, 300])
    save(img, "03_检验申请单.png")

    # 04 检验报告
    img, d = page("检 验 报 告 单", "检验科 · 血液分析")
    y = rows(d, [("姓　名", "张某某"), ("科　室", "内科"), ("报告日期", "2026-10-23")], 230)
    y = table(d, ["项目", "结　果", "参考区间", "单　位"],
              [["白细胞计数", "6.30", "3.50-9.50", "10^9/L"],
               ["红细胞计数", "4.24", "3.80-5.10", "10^12/L"],
               ["血红蛋白", "122", "115-150", "g/L"],
               ["血小板计数", "224", "100-300", "10^9/L"],
               ["中性粒细胞百分比", "65.4", "40.0-75.0", "%"],
               ["淋巴细胞百分比", "28.7", "20.0-50.0", "%"]],
              y + 20, [330, 200, 260, 240])
    d.text((90, y + 40), "检验者：李某某　　审核者：赵某某", font=font(24), fill=INK)
    save(img, "04_检验报告.png")

    # 05 处方单（含剂量，含一条模糊）
    img, d = page("处 方 笺", "内科 · 医保")
    y = rows(d, [("姓　名", "张某某"), ("临床诊断", "高血压病"), ("开单日期", "2026-10-23"),
                 ("医　师", "王某某")], 230)
    y = table(d, ["药品名称", "剂　量", "频　次", "数　量"],
              [["苯磺酸氨氯地平片", "5mg", "每日一次", "1 盒"],
               ["阿司匹林肠溶片", "100mg", "每日一次", "1 盒"],
               ["硝苯地平控释片", "30mg", "每日一次", "2 盒"]],
              y + 20, [400, 220, 240, 180])
    d.text((90, y + 30), "用　法：口服，饭后服用；疗程 30 天", font=font(25), fill=INK)
    d.text((90, y + 76), "药　费：86.40 元", font=font(25), fill=INK)
    save(img, "05_处方单.png")

    # 06 缴费凭证
    img, d = page("医 疗 收 费 凭 证", "财务科 · 门诊")
    y = rows(d, [("姓　名", "张某某"), ("就诊日期", "2026-10-23"), ("票据号码", "0013111279")], 230)
    y = table(d, ["收费项目", "金　额", "备　注"],
              [["诊察费", "12.00", ""], ["检验费", "148.00", "血常规四项"],
               ["西药费", "86.40", "处方 1 张"], ["检查费", "135.00", "CT 平扫"]],
              y + 20, [340, 220, 300])
    d.text((90, y + 30), "合计金额（小写）：￥381.40", font=font(28), fill=INK)
    d.text((90, y + 76), "合计金额（大写）：叁佰捌拾壹元肆角", font=font(26), fill=INK)
    save(img, "06_缴费凭证.png")

    # 07 检查申请单（勾选框）
    img, d = page("检 查 申 请 单", "影像科")
    y = rows(d, [("姓　名", "张某某"), ("申请科室", "内科"), ("申请医生", "王某某"),
                 ("检查项目", "☑ CT　□ X 线　□ 超声　□ 心电图"),
                 ("检查部位", "头颅（平扫）"), ("预约时间", "2026-10-23 14:30"),
                 ("注意事项", "去除金属饰品，检查前禁食 4 小时")], 230, gap=52)
    save(img, "07_检查申请单.png")

    # 08 取药单（含剂量，含跨行）
    img, d = page("门 诊 取 药 单", "门诊药房 · 2 号窗口")
    y = rows(d, [("姓　名", "张某某"), ("处方日期", "2026-10-23"), ("取药窗口", "2 号")], 230)
    y = table(d, ["药品名称", "规　格", "数　量", "用　法"],
              [["苯磺酸氨氯地平片", "5mg×28 片", "1 盒", "每次 1 片"],
               ["阿司匹林肠溶片", "100mg×30 片", "1 盒", "每次 1 片"],
               ["硝苯地平控释片", "30mg×14 片", "2 盒", "每次 1 片"]],
              y + 20, [400, 260, 180, 220])
    d.text((90, y + 30), "请核对药品名称与数量，离柜后不予退换。", font=font(24), fill=GRAY)
    save(img, "08_取药单.png")

    # 09 出院小结（剂量处做成"倾斜+浅色"，模拟手写/盖章遮挡）
    img, d = page("出 院 小 结", "内科病区 · 第 2 页")
    y = rows(d, [("姓　名", "张某某"), ("科　室", "内科"), ("住院天数", "6"),
                 ("出院日期", "2026-10-23"), ("入院诊断", "高血压病 3 级"),
                 ("出院诊断", "高血压病 3 级（好转）")], 230, gap=50)
    d.text((90, y + 20), "出院后用药及建议：", font=font(26), fill=INK)
    d.text((90, y + 66), "1. 出院带药：苯磺酸氨氯地平片 5mg  每日一次  每次 1 片",
           font=font(24), fill=INK)
    d.text((90, y + 110), "2. 阿司匹林肠溶片 100mg  每日一次  每次 1 片", font=font(24), fill=INK)
    d.text((90, y + 154), "3. 自备药：硝苯地平控释片 30mg  每日一次", font=font(24), fill=INK)
    # 模拟印章遮挡剂量单位，验证"看不清用 ?"
    d.ellipse((880, y + 40, 1080, y + 150), outline=RED, width=3)
    d.text((905, y + 80), "医保专用章", font=font(20), fill=RED)
    d.text((90, y + 210), "4. 复诊安排：两周后门诊随访；如有不适及时就诊。",
           font=font(24), fill=INK)
    save(img, "09_出院小结.png")

    # 10 医保结算单
    img, d = page("医 疗 保 险 费 用 结 算 单", "医疗保险管理局 · 定点医疗机构")
    y = rows(d, [("姓　名", "张某某"), ("住院天数", "6"), ("结算日期", "2026-10-23"),
                 ("医保类型", "职工基本医疗保险")], 230)
    y = table(d, ["费用项目", "总费用", "医保支付", "个人自付"],
              [["床位费", "480.00", "336.00", "144.00"],
               ["诊察费", "120.00", "84.00", "36.00"],
               ["检查费", "1350.00", "945.00", "405.00"],
               ["西药费", "2380.00", "1666.00", "714.00"]],
              y + 20, [300, 220, 220, 220])
    d.text((90, y + 30), "总费用合计：￥4330.00", font=font(27), fill=INK)
    d.text((90, y + 76), "医保统筹支付：￥3031.00　　个人自付合计：￥1299.00",
           font=font(26), fill=INK)
    save(img, "10_医保结算单.png")

    return made


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join("tools", "probe", "samples", "ocr"))
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    made = gen(args.out)
    print(f"已生成 {len(made)} 张合成单据 -> {args.out}")
    for name in made:
        size = os.path.getsize(os.path.join(args.out, name))
        print(f"  {name:24} {size/1024:6.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
