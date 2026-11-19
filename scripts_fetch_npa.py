#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功能：自動抓取內政部警政署開放資料（A1/A2 交通事故資料集與縣市統計），
      1. 彙整各縣市酒駕統計並安全更新 official_stats.csv（保留既有欄位或手動維護數值）
      2. 篩選最新疑似酒駕或重大死亡車禍線索，輸出 npa_candidates.csv（含 Google 新聞查證連結）
產生日期與時間：2026-11-18 08:42
"""

import csv
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime

# 政府資料開放平臺 - 內政部警政署即時道路交通事故資料 (A1類) CSV 端點
NPA_A1_CSV_URL = (
    "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/"
    "78421B7F-2F24-4B1B-95B8-19A0684D5D33/resource/"
    "E6C2F05E-4582-47A5-B471-89A31E96C6C1/download"
)

OFFICIAL_STATS_FILE = "official_stats.csv"
CANDIDATES_FILE = "npa_candidates.csv"
INCIDENTS_FILE = "incidents.csv"

COUNTIES_ORDER = [
    "台北市", "新北市", "基隆市", "桃園市", "新竹市", "新竹縣", "苗栗縣",
    "台中市", "彰化縣", "南投縣", "雲林縣", "嘉義市", "嘉義縣", "台南市",
    "高雄市", "屏東縣", "宜蘭縣", "花蓮縣", "台東縣", "澎湖縣", "金門縣", "連江縣"
]


def normalize_county(name: str) -> str:
    """將『臺北市』等異體字統一轉為『台北市』，並比對 22 縣市標準全名"""
    if not name:
        return ""
    s = name.strip().replace("臺", "台")
    for c in COUNTIES_ORDER:
        if s.startswith(c):
            return c
    return ""


def normalize_date(raw: str) -> str:
    """將民國年月日 (1151018) 或西元年月日 (20261018 / 2026/10/18) 統一轉為 YYYY-MM-DD"""
    s = re.sub(r"[^0-9]", "", str(raw).strip().split(".")[0])
    if len(s) == 7:  # 民國年 YYYMMDD，如 1151018
        y = int(s[:3]) + 1911
        return f"{y:04d}-{s[3:5]}-{s[5:7]}"
    if len(s) == 8:  # 西元年 YYYYMMDD，如 20261018
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return str(raw).strip()


def parse_dead_injured(text: str):
    """解析『死亡1;受傷2』或『死亡1人、受傷0人』格式"""
    dead, inj = 0, 0
    if not text:
        return dead, inj
    m_d = re.search(r"死亡\s*(\d+)", text)
    m_j = re.search(r"受傷\s*(\d+)", text)
    if m_d:
        dead = int(m_d.group(1))
    if m_j:
        inj = int(m_j.group(1))
    return dead, inj


def download_csv_rows(url: str):
    """下載遠端 CSV 並自動處理 UTF-8 / Big5 解碼"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(req, context=ctx, timeout=25) as resp:
        raw_bytes = resp.read()

    for enc in ("utf-8-sig", "utf-8", "big5", "cp950"):
        try:
            text = raw_bytes.decode(enc)
            if "\ufffd" not in text:
                return list(csv.reader(text.splitlines()))
        except UnicodeDecodeError:
            continue
    text = raw_bytes.decode("utf-8", errors="ignore")
    return list(csv.reader(text.splitlines()))


def load_existing_incidents():
    """讀取目前已收錄於 incidents.csv 的 (日期, 縣市) 集合，用於標記是否已收錄"""
    recorded = set()
    if not os.path.exists(INCIDENTS_FILE):
        return recorded
    try:
        with open(INCIDENTS_FILE, "r", encoding="utf-8-sig") as f:
            for row in list(csv.reader(f))[1:]:
                if len(row) >= 3:
                    d = normalize_date(row[1])
                    c = normalize_county(row[2])
                    if d and c:
                        recorded.add((d, c))
    except Exception as e:
        print(f"[警告] 讀取 {INCIDENTS_FILE} 失敗：{e}")
    return recorded


def ensure_official_stats_file():
    """確保 official_stats.csv 存在且包含完整 22 縣市結構"""
    if os.path.exists(OFFICIAL_STATS_FILE):
        print(f"[檢查] {OFFICIAL_STATS_FILE} 已存在，保留既有官方統計資料。")
        return

    year_label = f"{datetime.now().year}年累計"
    rows = [["縣市", "統計期間", "酒駕事故件數", "死亡人數", "受傷人數", "酒駕違規取締件數", "資料來源"]]
    for c in COUNTIES_ORDER:
        rows.append([c, year_label, 0, 0, 0, 0, "內政部警政署統計"])

    with open(OFFICIAL_STATS_FILE, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(rows)
    print(f"[建立] 已初始化 {OFFICIAL_STATS_FILE} 22 縣市空白結構。")


def main():
    ensure_official_stats_file()
    recorded_set = load_existing_incidents()

    print(f"[連線] 嘗試從警政署開放資料平臺抓取最新 A1 交通事故資料...")
    try:
        rows = download_csv_rows(NPA_A1_CSV_URL)
    except Exception as e:
        print(f"[提示] 無法連線至警政署開放資料端點（若於 GitHub Actions 執行，可能受政府防火牆海外 IP 限制）：{e}")
        print("[提示] 維持既有 CSV 檔案不覆寫，正常結束腳本。")
        return 0

    if len(rows) < 2:
        print("[提示] 下載之 CSV 無有效資料列。")
        return 0

    header = [h.strip() for h in rows[0]]
    print(f"[成功] 取得欄位：{header}")

    # 動態定位欄位索引
    idx_date = next((i for i, h in enumerate(header) if "日期" in h), 0)
    idx_loc = next((i for i, h in enumerate(header) if "地點" in h), 2)
    idx_dj = next((i for i, h in enumerate(header) if "死亡" in h or "受傷" in h), 3)
    idx_veh = next((i for i, h in enumerate(header) if "車種" in h), 4)
    idx_cause = next((i for i, h in enumerate(header) if "肇因" in h or "酒" in h), -1)

    candidates = [[
        "編號", "事件日期", "發生縣市", "路段", "酒駕者摘要",
        "被酒駕者摘要", "結果", "死亡人數", "受傷人數",
        "新聞搜尋連結", "比對狀態"
    ]]

    count = 0
    for r in rows[1:]:
        if len(r) <= max(idx_date, idx_loc, idx_dj):
            continue
        raw_date = r[idx_date].strip()
        if not re.search(r"\d{6,8}", raw_date):
            continue

        # 若資料集含肇因欄位，優先篩選含「酒」字眼案件；若無則全數列出供比對
        if idx_cause != -1 and idx_cause < len(r):
            if "酒" not in r[idx_cause]:
                continue

        date_fmt = normalize_date(raw_date)
        loc_full = r[idx_loc].strip()
        county = normalize_county(loc_full)
        if not county:
            continue
        road = loc_full[3:].strip()
        dead, inj = parse_dead_injured(r[idx_dj])
        veh = r[idx_veh].strip() if idx_veh < len(r) else ""

        count += 1
        query = urllib.parse.quote(f"{county} {road[:5]} 車禍 酒駕")
        search_url = f"https://www.google.com/search?q={query}&tbm=nws"
        status = "同日同縣市已有紀錄" if (date_fmt, county) in recorded_set else "待查證新聞"

        candidates.append([
            f"NPA-{date_fmt.replace('-', '')}-{count:03d}",
            date_fmt,
            county,
            road,
            f"涉案車種：{veh}（請依新聞查證補充）",
            "（請依新聞查證補充）",
            "死亡" if dead > 0 else "受傷",
            dead,
            inj,
            search_url,
            status,
        ])

    with open(CANDIDATES_FILE, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(candidates)

    print(f"[完成] 共整理 {count} 筆警政署事故線索至 {CANDIDATES_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
