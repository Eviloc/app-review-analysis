"""
评论清洗模块 - 确定性规则
去重、过滤、字段标准化
"""
import re


def clean_reviews(raw_reviews: list, min_rating: int = 1) -> list:
    """
    清洗评论：去重、过滤、标准化字段
    返回清洗后的评论列表，每条包含 clean_content 字段
    """
    seen_ids = set()
    seen_contents = set()
    cleaned = []

    for r in raw_reviews:
        # 过滤评分
        rating = r.get("rating", 0)
        if rating < min_rating:
            continue

        # 去重：review_id
        rid = str(r.get("review_id", ""))
        if rid and rid in seen_ids:
            continue
        seen_ids.add(rid)

        # 清洗内容
        content = r.get("content", "")
        if not content or not content.strip():
            continue

        # 去重：内容相似度
        content_key = re.sub(r"\s+", "", content)[:100].lower()
        if content_key in seen_contents:
            continue
        seen_contents.add(content_key)

        # 基础清洗：去除HTML标签、多余空白
        clean_content = re.sub(r"<[^>]+>", "", content)
        clean_content = re.sub(r"\s+", " ", clean_content).strip()

        # 截断过长内容
        if len(clean_content) > 500:
            clean_content = clean_content[:500] + "..."

        cleaned.append({
            "review_id": rid,
            "title": r.get("title", ""),
            "content": content,
            "clean_content": clean_content,
            "rating": rating,
            "version": r.get("version", ""),
            "date": r.get("date", ""),
            "region": r.get("region", "unknown")
        })

    return cleaned


if __name__ == "__main__":
    test_data = [
        {"review_id": "1", "content": "  Great app!  ", "rating": 5},
        {"review_id": "1", "content": "Duplicate", "rating": 4},
        {"review_id": "2", "content": "", "rating": 3},
    ]
    result = clean_reviews(test_data)
    print(f"清洗后: {len(result)} 条")
