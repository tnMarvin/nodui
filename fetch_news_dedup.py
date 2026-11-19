#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功能：依指定日期範圍抓取台灣酒駕死傷新聞報導（Google News RSS 多關鍵字檢索），
      透過「時間視窗 + 縣市 + 標題字元相似度（Jaccard Bigram）」過濾同事件重複報導，
      嚴格挑選出「最詳細的一家報導」（完全不跨篇拼湊互補，100% 維持單一來源原始事實），
      輸出 news_candidates.csv 供人工審閱。
產生日期與時間：2026-11-18 14:00
"""

import argparse
import csv
import html
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

INCIDENTS_FILE = "incidents.csv"
OUTPUT_CANDIDATES = "news_candidates.csv"

COUNTIES_ORDER = [
    "台北市", "新北市", "基隆市", "桃園市", "新竹市", "新竹縣", "苗栗縣",
    "台中市", "彰化縣", "南投縣", "雲林縣", "嘉義市", "嘉義縣", "台南市",
    "高雄市", "屏東縣", "宜蘭縣", "花蓮縣", "台東縣", "澎湖縣", "金門縣", "連江縣"
]

COUNTY_ALIASES = {
    "台北": "台北市", "北市": "台北市", "信義區": "台北市", "大安區": "台北市", "內湖": "台北市", "士林": "台北市", "北投": "台北市", "萬華": "台北市", "文山區": "台北市",
    "新北": "新北市", "板橋": "新北市", "新莊": "新北市", "中和": "新北市", "永和": "新北市", "三重": "新北市", "蘆洲": "新北市", "土城": "新北市", "樹林": "新北市", "淡水": "新北市", "汐止": "新北市", "新店": "新北市", "林口": "新北市", "五股": "新北市", "鶯歌": "新北市", "三峽": "新北市",
    "基隆": "基隆市", "七堵": "基隆市", "暖暖": "基隆市", "仁愛區": "基隆市", "安樂區": "基隆市",
    "桃園": "桃園市", "中壢": "桃園市", "平鎮": "桃園市", "八德": "桃園市", "楊梅": "桃園市", "蘆竹": "桃園市", "龜山": "桃園市", "龍潭": "桃園市", "大溪": "桃園市", "大園": "桃園市", "觀音": "桃園市",
    "竹市": "新竹市", "新竹市": "新竹市", "香山": "新竹市",
    "竹縣": "新竹縣", "竹北": "新竹縣", "竹東": "新竹縣", "湖口": "新竹縣", "新豐": "新竹縣", "新埔": "新竹縣", "關西": "新竹縣",
    "苗栗": "苗栗縣", "頭份": "苗栗縣", "竹南": "苗栗縣", "苑裡": "苗栗縣", "後龍": "苗栗縣", "通霄": "苗栗縣",
    "台中": "台中市", "中市": "台中市", "西屯": "台中市", "北屯": "台中市", "南屯": "台中市", "豐原": "台中市", "大里": "台中市", "太平": "台中市", "沙鹿": "台中市", "清水": "台中市", "大甲": "台中市", "霧峰": "台中市", "烏日": "台中市",
    "彰化": "彰化縣", "員林": "彰化縣", "鹿港": "彰化縣", "和美": "彰化縣", "北斗": "彰化縣", "溪湖": "彰化縣", "二林": "彰化縣",
    "南投": "南投縣", "草屯": "南投縣", "埔里": "南投縣", "竹山": "南投縣", "名間": "南投縣",
    "雲林": "雲林縣", "斗六": "雲林縣", "虎尾": "雲林縣", "北港": "雲林縣", "西螺": "雲林縣", "麥寮": "雲林縣",
    "嘉市": "嘉義市", "嘉義市": "嘉義市",
    "嘉縣": "嘉義縣", "民雄": "嘉義縣", "水上": "嘉義縣", "太保": "嘉義縣", "朴子": "嘉義縣", "大林": "嘉義縣",
    "台南": "台南市", "南市": "台南市", "永康": "台南市", "歸仁": "台南市", "新營": "台南市", "仁德": "台南市", "善化": "台南市", "安南": "台南市", "安平": "台南市", "新化": "台南市", "佳里": "台南市", "麻豆": "台南市",
    "高雄": "高雄市", "高市": "高雄市", "鳳山": "高雄市", "左營": "高雄市", "三民": "高雄市", "楠梓": "高雄市", "前鎮": "高雄市", "小港": "高雄市", "岡山": "高雄市", "仁武": "高雄市", "路竹": "高雄市", "大寮": "高雄市", "林園": "高雄市", "苓雅": "高雄市", "鼓山": "高雄市",
    "屏東": "屏東縣", "潮州": "屏東縣", "東港": "屏東縣", "恆春": "屏東縣", "內埔": "屏東縣", "萬丹": "屏東縣",
    "宜蘭": "宜蘭縣", "羅東": "宜蘭縣", "礁溪": "宜蘭縣", "蘇澳": "宜蘭縣", "頭城": "宜蘭縣",
    "花蓮": "花蓮縣", "吉安": "花蓮縣", "玉里": "花蓮縣", "新城": "花蓮縣",
    "台東": "台東縣", "卑南": "台東縣", "成功鎮": "台東縣", "太麻里": "台東縣", "綠島": "台東縣", "蘭嶼": "台東縣",
    "澎湖": "澎湖縣", "馬公": "澎湖縣",
    "金門": "金門縣", "金城": "金門縣", "金湖": "金門縣",
    "馬祖": "連江縣", "連江": "連江縣", "南竿": "連江縣",
}

SOURCE_WEIGHTS = {
    "中央社": 25, "CNA": 25, "公視": 22, "自由時報": 20, "聯合新聞網": 20, "聯合報": 20,
    "ETtoday": 18, "東森新聞": 18, "TVBS": 16, "三立": 16, "民視": 16, "華視": 16,
    "中時": 16, "鏡週刊": 14, "太報": 14, "壹蘋": 15, "NOWnews": 14, "新頭殼": 12
}


def clean_html_text(raw: str) -> str:
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def extract_county(text: str) -> str:
    s = text.replace("臺", "台")
    for c in COUNTIES_ORDER:
        if c in s:
            return c
    for alias, c in COUNTY_ALIASES.items():
        if alias in s:
            return c
    return ""


def extract_road(text: str) -> str:
    s = text.replace("臺", "台")
    patterns = [
        r"([\u4e00-\u9fa5]{1,3}[區鄉鎮市][\u4e00-\u9fa5]{1,5}(?:路|街|大道|巷|橋)(?:[一二三四五六七八九十\d]+段)?)",
        r"([\u4e00-\u9fa5]{2,5}(?:路|街|大道|大橋)(?:[一二三四五六七八九十\d]+段)?)",
        r"(國道[一二三四五六七八九十\d]+號|台[\d]+線|省道[\d]+號)",
        r"([\u4e00-\u9fa5]{1,3}[區鄉鎮市])",
    ]
    for pat in patterns:
        m = re.search(pat, s)
        if m:
            val = m.group(1)
            if not any(w in val for w in ("網路", "一路", "生路", "死路", "上路", "走路", "馬路", "道路")):
                return val
    return ""


def extract_casualties(text: str):
    dead, inj = 0, 0
    cn_num = {"一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

    def to_int(v):
        return cn_num.get(v, int(v)) if v in cn_num or v.isdigit() else 1

    m_ds = re.search(r"([\d一二兩三四五六七八九十]+)\s*死\s*([\d一二兩三四五六七八九十]+)\s*傷", text)
    if m_ds:
        dead = to_int(m_ds.group(1))
        inj = to_int(m_ds.group(2))
    else:
        m_d = re.search(r"([\d一二兩三四五六七八九十]+)\s*(?:人|名)?(?:死亡|慘死|不治|身亡|喪命|奪命)", text)
        if m_d:
            dead = to_int(m_d.group(1))
        elif any(k in text for k in ("不治", "身亡", "死亡", "慘死", "喪命", "奪命", "撞死", "亡")):
            dead = 1

        m_j = re.search(r"([\d一二兩三四五六七八九十]+)\s*(?:人|名)?(?:受傷|輕傷|重傷|擦挫傷|送醫)", text)
        if m_j:
            inj = to_int(m_j.group(1))
        elif dead == 0 and any(k in text for k in ("受傷", "重傷", "輕傷", "骨折", "腦出血", "撞傷", "擦傷")):
            inj = 1

    result_str = "死亡" if dead > 0 else ("受傷" if inj > 0 else "待確認")
    return result_str, dead, inj


def char_bigrams(text: str) -> set:
    s = re.sub(r"[-－|｜_].*$", "", text.replace("臺", "台"))
    s = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", s)
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i+2] for i in range(len(s) - 1)}


def jaccard_similarity(set_a: set, set_b: set) -> float:
    if not set_a or not set_b:
        return 0.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    overlap = inter / max(1, min(len(set_a), len(set_b)))
    return max(inter / union, overlap * 0.85)


def score_article_detail(item: dict) -> float:
    full_text = f"{item['title']} {item['snippet']}"
    score = len(full_text) * 0.4

    if item["county"]:
        score += 15
    if item["road"]:
        score += 20
    if re.search(r"\d+\s*歲", full_text):
        score += 18
    if re.search(r"0\.\d+|酒測|毫克|mg/L|超標", full_text, re.I):
        score += 18
    if re.search(r"騎士|行人|外送|單車|腳踏車|乘客|晨運|婦人|老翁|男|女", full_text):
        score += 12
    if re.search(r"移送|公共危險|收押|交保|國民法官|判刑", full_text):
        score += 10

    for src_key, w in SOURCE_WEIGHTS.items():
        if src_key.lower() in item["source"].lower():
            score += w
            break

    return round(score, 2)


def is_same_incident(a: dict, b: dict) -> bool:
    if a["county"] and b["county"] and a["county"] != b["county"]:
        return False

    date_diff = abs((a["dt"] - b["dt"]).days)
    if date_diff > 4:
        return False

    if a["county"] and a["county"] == b["county"] and date_diff <= 2:
        if a["road"] and b["road"] and len(a["road"]) >= 2 and (a["road"] in b["road"] or b["road"] in a["road"]):
            return True

    sim = jaccard_similarity(a["bigrams"], b["bigrams"])
    threshold = 0.22 if (a["county"] and a["county"] == b["county"] and date_diff <= 2) else 0.35
    return sim >= threshold


def cluster_and_pick_best(articles: list) -> list:
    """
    將新聞依事件分群，並直接取每個事件中詳細度分數最高的一篇作為代表。
    【嚴格原則】：完全不進行跨篇資訊拼湊或互補（不拿 B 報導的路名或日期去補 A 報導），
    100% 保持單一獲選報導的原始解析資料，避免不同案件誤併時產生張冠李戴。
    """
    clusters = []
    for art in sorted(articles, key=lambda x: x["dt"]):
        placed = False
        for cl in clusters:
            if any(is_same_incident(art, member) for member in cl):
                cl.append(art)
                placed = True
                break
        if not placed:
            clusters.append([art])

    deduped_events = []
    for cl in clusters:
        cl_sorted = sorted(cl, key=lambda x: x["score"], reverse=True)
        # 直接採用最高分單一報導本身的所有欄位，不做任何跨篇欄位覆寫
        best = dict(cl_sorted[0])
        best["media_count"] = len(cl_sorted)
        best["other_sources"] = "、".join(
            dict.fromkeys(f"{m['source']}" for m in cl_sorted[1:] if m["source"] != best["source"])
        )[:80]
        deduped_events.append(best)

    return sorted(deduped_events, key=lambda x: x["date"], reverse=True)


def fetch_google_news_rss(start_date: str, end_date: str) -> list:
    dt_end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    before_str = dt_end.strftime("%Y-%m-%d")

    queries = [
        f'(酒駕 OR 酒後駕車 OR 酒測超標) (撞死 OR 不治 OR 死亡 OR 身亡 OR 撞傷 OR 車禍) -藝人 -中國 -美國 after:{start_date} before:{before_str}',
        f'酒駕 (騎士 OR 行人 OR 外送員 OR 單車) (送醫 OR 搶救 OR 傷重) -中國 after:{start_date} before:{before_str}'
    ]

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    raw_articles = []
    seen_titles = set()

    for q in queries:
        encoded_q = urllib.parse.quote(q)
        rss_url = f"https://news.google.com/rss/search?q={encoded_q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        req = urllib.request.Request(
            rss_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"}
        )
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
                xml_bytes = resp.read()
        except Exception as e:
            print(f"[提示] RSS 檢索連線失敗 ({e})，請確認執行環境具備外網連線。")
            continue

        root = ET.fromstring(xml_bytes)
        for item in root.findall("./channel/item"):
            full_title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date_raw = (item.findtext("pubDate") or "").strip()
            desc_raw = item.findtext("description") or ""
            source_el = item.find("source")
            source_name = (source_el.text if source_el is not None else "").strip()

            title_clean = full_title
            if " - " in full_title:
                parts = full_title.rsplit(" - ", 1)
                title_clean = parts[0].strip()
                if not source_name:
                    source_name = parts[1].strip()

            if title_clean in seen_titles:
                continue
            seen_titles.add(title_clean)

            try:
                dt = parsedate_to_datetime(pub_date_raw) + timedelta(hours=8)
                date_str = dt.strftime("%Y-%m-%d")
            except Exception:
                dt = datetime.strptime(start_date, "%Y-%m-%d")
                date_str = start_date

            if not (start_date <= date_str <= end_date):
                continue

            snippet = clean_html_text(desc_raw)
            snippet = snippet.replace(title_clean, "").replace(source_name, "").strip()

            combined_text = f"{title_clean} {snippet}"
            if not any(k in combined_text for k in ("撞", "死", "傷", "送醫", "不治", "身亡", "車禍", "追撞", "擦撞", "翻覆", "自撞")):
                continue

            county = extract_county(combined_text)
            road = extract_road(combined_text)
            result_str, dead, inj = extract_casualties(combined_text)

            art = {
                "dt": dt,
                "date": date_str,
                "title": title_clean,
                "snippet": snippet,
                "source": source_name or "新聞媒體",
                "url": link,
                "county": county,
                "road": road,
                "result": result_str,
                "dead": dead,
                "inj": inj,
                "bigrams": char_bigrams(title_clean),
            }
            art["score"] = score_article_detail(art)
            raw_articles.append(art)

    return raw_articles


def load_recorded_keys() -> set:
    recorded = set()
    if not os.path.exists(INCIDENTS_FILE):
        return recorded
    try:
        with open(INCIDENTS_FILE, "r", encoding="utf-8-sig") as f:
            for r in list(csv.reader(f))[1:]:
                if len(r) >= 3:
                    recorded.add((r[1].strip(), r[2].strip().replace("臺", "台")))
    except Exception:
        pass
    return recorded


def generate_markdown_report(events: list, recorded: set, start_date: str, end_date: str) -> str:
    """產生供 GitHub Issue 審閱通知使用的 Markdown 摘要表"""
    lines = [
        f"### 🔔 酒駕新聞定時抓取審閱報告（`{start_date}` ～ `{end_date}`）",
        "",
        f"系統已完成本週新聞抓取與同事件去重，共歸納出 **{len(events)}** 件獨立事件（皆取單一最詳細報導，無跨篇拼湊）：",
        "",
        "| 建議編號 | 報導日期 | 縣市 | 路段 | 死傷初判 | 最詳細代表媒體与標題 | 同事件家數 | 現有資料庫比對 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :---: | :--- |"
    ]
    date_counter = {}
    for ev in events:
        d_compact = ev["date"].replace("-", "")
        date_counter[d_compact] = date_counter.get(d_compact, 0) + 1
        ev_id = f"{d_compact}-{date_counter[d_compact]:02d}"
        status = "⚠️ 同日同縣市已有紀錄" if (ev["date"], ev["county"]) in recorded else "🆕 新事件待整理"
        c_str = ev["county"] or "待確認"
        r_str = ev["road"] or "待確認"
        res_str = f"{ev['result']} ({ev['dead']}死{ev['inj']}傷)"
        title_link = f"[{ev['source']}：{ev['title']}]({ev['url']})"
        lines.append(f"| `{ev_id}` | {ev['date']} | {c_str} | {r_str} | {res_str} | {title_link} | {ev['media_count']} 家 | {status} |")

    lines.extend([
        "",
        "---",
        "#### ✅ 審閱與上架流程（不自動改動網站正式資料）",
        "1. 請打開儲存庫中的 `news_candidates.csv`（或從本頁下方 Actions Artifact 下載）。",
        "2. 點擊上方新聞連結查證，親手填寫 **「酒駕者摘要」** 與 **「被酒駕者摘要」**。",
        "3. 確認無誤後，將審閱完的資料列貼入 `incidents.csv` 並上傳（Commit & Push）至 GitHub，網站即會自動更新呈現，隨後可關閉此 Issue。"
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="抓取指定日期範圍內的酒駕新聞，去重後列出最詳細的一家報導（不跨篇互補）")
    default_end = datetime.now().strftime("%Y-%m-%d")
    default_start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    parser.add_argument("--start", default=default_start, help="起始日期 (YYYY-MM-DD)，預設為 7 天前")
    parser.add_argument("--end", default=default_end, help="結束日期 (YYYY-MM-DD)，預設為今天")
    parser.add_argument("--out", default=OUTPUT_CANDIDATES, help="輸出候選 CSV 檔名")
    parser.add_argument("--md", default="review_summary.md", help="輸出供 Issue 通知使用的 Markdown 摘要檔")
    args = parser.parse_args()

    print(f"[搜尋範圍] {args.start} 至 {args.end}")
    articles = fetch_google_news_rss(args.start, args.end)
    print(f"[初步抓取] 共取得 {len(articles)} 則酒駕相關新聞報導。")

    events = cluster_and_pick_best(articles)
    print(f"[事件去重] 合併重複報導後，共歸納出 {len(events)} 件獨立酒駕事件（嚴格採用單一最佳報導，無跨篇拼湊）。")

    recorded = load_recorded_keys()

    rows_out = [[
        "編號", "事件日期", "發生縣市", "路段",
        "酒駕者摘要", "被酒駕者摘要", "結果",
        "死亡人數", "受傷人數", "新聞網址", "新聞來源",
        "最詳細報導標題(供人工改寫參考)", "媒體報導家數", "其他報導媒體", "比對現有資料庫狀態"
    ]]

    date_counter = {}
    for ev in events:
        d_compact = ev["date"].replace("-", "")
        date_counter[d_compact] = date_counter.get(d_compact, 0) + 1
        ev_id = f"{d_compact}-{date_counter[d_compact]:02d}"

        status = "已有同日同縣市紀錄" if (ev["date"], ev["county"]) in recorded else "新事件待整理"

        rows_out.append([
            ev_id,
            ev["date"],
            ev["county"] or "待確認縣市",
            ev["road"] or "待確認路段",
            "（請依據右側新聞改寫酒駕者事實）",
            "（請依據右側新聞改寫被酒駕者事實，不寫姓名）",
            ev["result"],
            ev["dead"],
            ev["inj"],
            ev["url"],
            ev["source"],
            ev["title"],
            f"共 {ev['media_count']} 家報導 (代表分數:{ev['score']})",
            ev["other_sources"],
            status
        ])

    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(rows_out)

    md_content = generate_markdown_report(events, recorded, args.start, args.end)
    with open(args.md, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"[完成] 已輸出待審閱清單至 {args.out}，並產生審閱通知摘要 {args.md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
