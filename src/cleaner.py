# src/cleaner.py
import json
import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CACHE_DIR = BASE_DIR / "cache"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def clean_text(raw_text: str) -> str:
    """文本清洗：去除换行、多余空格、特殊符号"""
    if not raw_text:
        return ""
    text = raw_text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    return text


def load_raw_reviews(json_path: str):
    """加载原始采集的评论json"""
    with open(json_path, "r", encoding="utf‑8") as f:
        return json.load(f)


def filter_reviews(review_list):
    """过滤无效评论"""
    valid = []
    discard = []
    for item in review_list:
        content = clean_text(item.get("content", ""))
        # 过滤条件：文本长度小于5直接丢弃
        if len(content) < 5:
            discard.append(item)
            continue
        item["clean_content"] = content
        valid.append(item)
    return valid, discard


def run_clean_pipeline(input_json_name: str):
    """执行完整清洗流水线"""
    input_path = str(CACHE_DIR / input_json_name)
    raw_data = load_raw_reviews(input_path)
    raw_count = len(raw_data)

    valid_reviews, discard_reviews = filter_reviews(raw_data)
    valid_count = len(valid_reviews)
    discard_count = len(discard_reviews)

    out_file = OUTPUT_DIR / "cleaned_reviews.json"
    with open(out_file, "w", encoding="utf‑8") as f:
        json.dump(valid_reviews, f, ensure_ascii=False, indent=2)

    print(f"===== 评论清洗完成 =====")
    print(f"原始评论总数：{raw_count}")
    print(f"丢弃无效评论：{discard_count}")
    print(f"保留有效评论：{valid_count}")
    print(f"清洗结果输出路径：{out_file.resolve()}")
    return str(out_file)


if __name__ == "__main__":
    # 修改为你cache里实际的json文件名
    run_clean_pipeline("app_839285684.json")
