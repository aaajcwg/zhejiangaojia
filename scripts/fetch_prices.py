#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动更新全国大宗建材价格（国家统计局《流通领域重要生产资料市场价格变动情况》）。
- 找到最新一期发布页，解析表格，把大宗品价格映射写入 prices.json 的 regions["全国"]。
- 映射失败或站点不可达时：打印警告并正常退出（exit 0），不阻塞流水线。
"""
import json
import re
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

LIST_URL = "https://www.stats.gov.cn/sj/zxfb/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
# 国家统计局产品名（前缀匹配，括号内规格任意）→ 我们材料库条目 (name, spec, unit)
PREFIX_MAP = [
    ("螺纹钢",      ("螺纹钢 HRB400 Φ16-25", "Φ16-25", "吨")),
    ("线材",        ("高线 HPB300 Φ6.5-10", "Φ6.5-10", "吨")),
    ("普通中板",    ("钢板 Q235 20mm", "Q235 20mm 中板", "吨")),
    ("无缝钢管",    ("无缝钢管 219×6", "20# 219×6mm", "吨")),
    # 统计局玻璃按"吨"发布，与按㎡的零售条目口径不同，单独维护吨价条目
    ("浮法平板玻璃", ("浮法玻璃原片", "5/6mm 吨价", "吨")),
]
# 水泥类按规格关键词匹配
CEMENT_RULES = [
    (("42.5", "散装"), ("普通硅酸盐水泥 PO42.5 散装", "散装", "吨")),
    (("42.5", "袋装"), ("复合硅酸盐水泥 PO42.5 袋装", "袋装", "吨")),
]


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def norm(s):
    return re.sub(r"\s+", "", s or "")


def find_latest_link(html):
    # 列表页链接形如 <a href="./202609/t20260914_xxxx.html">…流通领域重要生产资料市场价格变动情况（2026年9月上旬）…</a>
    pat = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>([^<]*流通领域重要生产资料市场价格变动情况[^<]*)</a>')
    for m in pat.finditer(html):
        href, title = m.group(1), m.group(2)
        if href.startswith("./"):
            href = "https://www.stats.gov.cn/sj/zxfb/" + href[2:]
        elif href.startswith("/"):
            href = "https://www.stats.gov.cn" + href
        elif not href.startswith("http"):
            href = "https://www.stats.gov.cn/sj/zxfb/" + href
        return href, title
    return None, None


def parse_period(title):
    m = re.search(r"(\d{4})年(\d{1,2})月(上|中|下)旬", title or "")
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}{'上' if m.group(3)=='上' else ('中' if m.group(3)=='中' else '下')}旬"
    return date.today().isoformat()


def parse_table(html):
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
    out = {}
    for row in rows:
        cells = [norm(re.sub(r"<[^>]+>", "", c)) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if len(cells) < 3:
            continue
        product = cells[0]  # 第1列=产品名称，第2列=单位，第3列=本期价格
        price = None
        for c in cells[1:]:
            c = c.replace(",", "")
            if re.fullmatch(r"\d+(\.\d+)?", c):
                price = float(c)
                break
        if product and price is not None:
            out[product] = price
    return out


def match_product(product):
    """按前缀/关键词把统计局产品名映射到材料库条目；未匹配返回 None"""
    if "水泥" in product:
        for keys, mapping in CEMENT_RULES:
            if all(k in product for k in keys):
                return mapping
        return None
    for prefix, mapping in PREFIX_MAP:
        if product.startswith(prefix):
            return mapping
    return None


def main():
    root = Path(__file__).resolve().parent.parent
    prices_path = root / "prices.json"
    print("[1] 读取", prices_path)
    data = json.loads(prices_path.read_text(encoding="utf-8"))

    print("[2] 抓取列表页", LIST_URL)
    html = fetch(LIST_URL)
    link, title = find_latest_link(html)
    if not link:
        print("!! 未能找到最新一期链接（页面结构可能变化），跳过更新")
        return
    print("    最新一期:", title, "->", link)

    print("[3] 抓取发布页并解析表格")
    page = fetch(link)
    table = parse_table(page)
    if not table:
        print("!! 表格解析为空，跳过更新")
        return
    period = parse_period(title)

    nat = data.setdefault("regions", {}).setdefault("全国", {"date": "", "source": "", "items": []})
    items = nat.setdefault("items", [])
    idx = {(it["name"] + "|" + (it.get("spec") or "")): it for it in items}

    updated, added = 0, 0
    for product, price in table.items():
        mapping = match_product(product)
        if not mapping:
            continue
        name, spec, unit = mapping
        key = name + "|" + spec
        if key in idx:
            idx[key]["price"] = round(price, 2)
            updated += 1
        else:
            cat = "钢材" if "钢" in name else ("玻璃制品" if "玻璃" in name else "水泥及骨料")
            items.append({"name": name, "category": cat, "spec": spec, "unit": unit, "price": round(price, 2)})
            idx[key] = items[-1]
            added += 1

    if updated + added == 0:
        print("!! 本期表格未匹配到任何映射产品，跳过更新")
        return
    nat["date"] = period
    nat["source"] = "国家统计局·流通领域重要生产资料市场价格（" + period + "）"
    data["updated"] = date.today().isoformat()

    prices_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[4] 完成：更新 {updated} 项，新增 {added} 项，期数 {period}")
    print("    期数时间戳:", datetime.now().isoformat(timespec="seconds"))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # 任何失败都不阻塞流水线
        print("!! 抓取失败（不影响仓库）：", repr(e), file=sys.stderr)
        sys.exit(0)
