# src/collector.py
import requests
import time
import json
import os
import re
from dotenv import load_dotenv

# 加载项目 .env
load_dotenv("../.env")
# 获取collector.py所在文件夹
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 向上一层到项目根目录，再指向cache
CACHE_DIR = os.path.join(BASE_DIR, "..", "cache")
CACHE_DIR = os.path.abspath(CACHE_DIR)
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


def fetch_appstore_reviews(app_id: str, sleep_sec: float = 1.0):
    """
    调用苹果官方US RSS接口
    读取.env代理配置；网络失败不崩溃，返回空列表
    :return: list[dict]原始评论
    """
    base_url = f"https://itunes.apple.com/us/rss/customerreviews/id={app_id}/json"
    proxies = get_proxies()
    try:
        time.sleep(sleep_sec)
        resp = requests.get(base_url, timeout=15, proxies=proxies)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as e:
        print(f"[采集警告]网络请求失败: {e}")
        return []
    except json.JSONDecodeError:
        print("[采集警告]接口返回非合法JSON")
        return []

    feed = data.get("feed", {})
    entries = feed.get("entry", [])

    if not entries:
        print(f"[采集警告] app_id={app_id} RSS接口没有返回任何美区评论")
        return []

    raw_reviews = []
    for item in entries:
        review = {
            "review_id": item.get("id", {}).get("label", ""),
            "title": item.get("title", {}).get("label", ""),
            "content": item.get("content", [{}])[0].get("label", ""),
            "rating": int(item.get("im:rating", {}).get("label", 0)),
            "version": item.get("im:version", {}).get("label", ""),
            "date": item.get("updated", {}).get("label", "")
        }
        raw_reviews.append(review)

    cache_path = os.path.join(CACHE_DIR, f"app_{app_id}.json")
    with open(cache_path, "w", encoding="utf‑8") as f:
        json.dump(raw_reviews, f, ensure_ascii=False, indent=2)
    print(f"[线上采集完成] 共获取 {len(raw_reviews)} 条评论，已写入缓存 {cache_path}")
    return raw_reviews


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
        # 优先方案①线上采集
        reviews = fetch_appstore_reviews(aid)
        # 如果线上拿不到数据，自动切换方案②读取缓存
        if len(reviews) == 0:
            reviews = load_cached_reviews(aid)
        for r in reviews[:2]:
            print("-----样例评论-----")
            print(r)
    else:
        print("链接解析失败")
