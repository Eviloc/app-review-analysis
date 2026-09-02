"""
数据采集模块
支持：App Store RSS 采集 + JSON/CSV 文件导入
"""
import requests
import time
import json
import os
import re
import pandas as pd
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = BASE_DIR
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

CACHE_DIR = os.path.join(PROJECT_ROOT, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

REGION = "us"


def get_proxies():
    http_proxy = os.getenv("HTTP_PROXY", None)
    https_proxy = os.getenv("HTTPS_PROXY", None)
    if http_proxy and https_proxy:
        return {"http": http_proxy, "https": https_proxy}
    return None


def extract_app_id(url: str) -> str | None:
    match = re.search(r"id(\d+)", url)
    return match.group(1) if match else None


def _parse_entry(item: dict) -> dict:
    content_raw = item.get("content", {})
    if isinstance(content_raw, list):
        content_label = content_raw[0].get("label", "") if content_raw else ""
    elif isinstance(content_raw, dict):
        content_label = content_raw.get("label", "")
    else:
        content_label = str(content_raw)

    rating_raw = item.get("im:rating", {}).get("label", "0")
    try:
        rating = int(rating_raw)
    except (ValueError, TypeError):
        rating = 0

    return {
        "review_id": item.get("id", {}).get("label", ""),
        "title": item.get("title", {}).get("label", ""),
        "content": content_label,
        "rating": rating,
        "version": item.get("im:version", {}).get("label", ""),
        "date": item.get("updated", {}).get("label", ""),
        "region": REGION
    }


def _try_endpoint(url: str, proxies, headers) -> list:
    try:
        resp = requests.get(url, timeout=20, proxies=proxies, headers=headers)
        if resp.status_code != 200:
            return []
        data = resp.json()
        entries = data.get("feed", {}).get("entry", [])
        if not entries:
            return []
        reviews = []
        for item in entries:
            parsed = _parse_entry(item)
            if parsed["rating"] == 0 and not parsed["content"]:
                continue
            reviews.append(parsed)
        return reviews
    except Exception:
        return []


def fetch_appstore_reviews(app_id: str, sleep_sec: float = 1.5, max_pages: int = 3) -> list:
    """多端点采集美区评论"""
    proxies = get_proxies()
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://apps.apple.com/"
    }

    url_templates = [
        f"https://itunes.apple.com/{REGION}/rss/customerreviews/id={{app_id}}/page={{page}}/json",
        f"https://itunes.apple.com/{REGION}/rss/customerreviews/page={{page}}/id={{app_id}}/sortby=mostrecent/json",
        f"https://itunes.apple.com/{REGION}/rss/customerreviews/id={{app_id}}/page={{page}}/sortby=mostrecent/json",
    ]

    all_reviews = []
    working_template = None

    for page in range(1, max_pages + 1):
        page_reviews = []
        if working_template:
            url = working_template.format(app_id=app_id, page=page)
            page_reviews = _try_endpoint(url, proxies, headers)
        else:
            for tpl in url_templates:
                url = tpl.format(app_id=app_id, page=page)
                page_reviews = _try_endpoint(url, proxies, headers)
                if page_reviews:
                    working_template = tpl
                    break

        if not page_reviews:
            break
        all_reviews.extend(page_reviews)
        time.sleep(sleep_sec)

    if all_reviews:
        cache_path = os.path.join(CACHE_DIR, f"app_{app_id}.json")
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(all_reviews, f, ensure_ascii=False, indent=2)

    return all_reviews


def import_reviews_from_file(uploaded_file) -> list:
    """
    从上传的 JSON/CSV 文件导入评论
    支持字段：review_id, content, rating, title, version, date
    """
    filename = uploaded_file.name.lower()
    reviews = []

    if filename.endswith(".json"):
        data = json.loads(uploaded_file.read().decode("utf-8"))
        if isinstance(data, list):
            reviews = data
        elif isinstance(data, dict) and "feed" in data:
            entries = data.get("feed", {}).get("entry", [])
            reviews = [_parse_entry(e) for e in entries]
    elif filename.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
        reviews = df.to_dict("records")

    # 标准化字段
    normalized = []
    for i, r in enumerate(reviews):
        normalized.append({
            "review_id": str(r.get("review_id", r.get("id", f"imported_{i}"))),
            "title": r.get("title", ""),
            "content": r.get("content", r.get("review", r.get("text", ""))),
            "rating": int(r.get("rating", r.get("score", 0))),
            "version": r.get("version", ""),
            "date": r.get("date", r.get("updated", "")),
            "region": r.get("region", "imported")
        })

    return normalized


if __name__ == "__main__":
    test_url = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"
    aid = extract_app_id(test_url)
    if aid:
        reviews = fetch_appstore_reviews(aid, max_pages=3)
        print(f"采集到 {len(reviews)} 条评论")
