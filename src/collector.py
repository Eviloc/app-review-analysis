import requests
import time
import json
import os
import re
from dotenv import load_dotenv

# 修复：用绝对路径加载 .env，和 classifier.py 保持一致
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# 向上一层到项目根目录，再指向 cache
CACHE_DIR = os.path.join(PROJECT_ROOT, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def get_proxies():
    """从环境变量读取代理，本地调试使用，无配置返回None"""
    http_proxy = os.getenv("HTTP_PROXY", None)
    https_proxy = os.getenv("HTTPS_PROXY", None)
    if http_proxy and https_proxy:
        return {
            "http": http_proxy,
            "https": https_proxy
        }
    return None


def extract_app_id(url: str) -> str | None:
    """从美区App Store链接提取app_id数字"""
    match = re.search(r"id(\d+)", url)
    if match:
        return match.group(1)
    return None


def _parse_entry(item: dict) -> dict:
    """解析单条评论 entry，健壮处理字段缺失"""
    # content 可能是列表也可能是 dict，兼容处理
    content_raw = item.get("content", {})
    if isinstance(content_raw, list):
        content_label = content_raw[0].get("label", "") if content_raw else ""
    elif isinstance(content_raw, dict):
        content_label = content_raw.get("label", "")
    else:
        content_label = str(content_raw)

    # rating 安全转 int
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
        "date": item.get("updated", {}).get("label", "")
    }


def fetch_appstore_reviews(app_id: str, sleep_sec: float = 1.0, max_pages: int = 3):
    """
    调用苹果官方US RSS接口，支持分页采集
    读取.env代理配置；网络失败不崩溃，返回空列表
    :param max_pages: 最多采集几页（每页约50条，上限10页）
    :return: list[dict] 原始评论
    """
    proxies = get_proxies()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
    }

    all_reviews = []

    for page in range(1, max_pages + 1):
        # 分页 URL：/page=N/json
        base_url = f"https://itunes.apple.com/us/rss/customerreviews/id={app_id}/page={page}/json"

        try:
            time.sleep(sleep_sec)
            resp = requests.get(base_url, timeout=15, proxies=proxies, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as e:
            print(f"[采集警告] 第{page}页网络请求失败: {e}")
            break
        except json.JSONDecodeError:
            print(f"[采集警告] 第{page}页接口返回非合法JSON")
            break

        feed = data.get("feed", {})
        entries = feed.get("entry", [])

        if not entries:
            print(f"[采集提示] 第{page}页无数据，停止采集")
            break

        page_reviews = []
        for item in entries:
            parsed = _parse_entry(item)
            # 修复1：跳过 App 元信息条目（rating=0 且 content 为空的非评论）
            if parsed["rating"] == 0 and not parsed["content"]:
                continue
            page_reviews.append(parsed)

        print(f"[采集] 第{page}页获取 {len(page_reviews)} 条评论")
        all_reviews.extend(page_reviews)

        # 如果本页少于 50 条，说明是最后一页
        if len(page_reviews) < 50:
            break

    if not all_reviews:
        print(f"[采集警告] app_id={app_id} 未获取到任何评论")
        return []

    cache_path = os.path.join(CACHE_DIR, f"app_{app_id}.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(all_reviews, f, ensure_ascii=False, indent=2)
    print(f"[线上采集完成] 共获取 {len(all_reviews)} 条评论，已写入缓存 {cache_path}")
    return all_reviews


def load_cached_reviews(app_id: str):
    """方案②：离线读取本地缓存，无网络时直接调用此函数"""
    cache_path = os.path.join(CACHE_DIR, f"app_{app_id}.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"[离线缓存模式]读取本地缓存，共{len(data)}条评论")
        return data
    print("[离线缓存模式]未找到该App的缓存文件")
    return []


if __name__ == "__main__":
    test_url = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"
    aid = extract_app_id(test_url)
    if aid:
        print(f"解析到 app_id: {aid}")
        # 优先方案①线上采集
        reviews = fetch_appstore_reviews(aid, max_pages=3)
        # 如果线上拿不到数据，自动切换方案②读取缓存
        if len(reviews) == 0:
            reviews = load_cached_reviews(aid)
        print(f"\n最终获取 {len(reviews)} 条评论")
        for r in reviews[:3]:
            print("-----样例评论-----")
            print(f"  rating: {r['rating']}")
            print(f"  title: {r['title']}")
            print(f"  content: {r['content'][:80]}...")
    else:
        print("链接解析失败")
