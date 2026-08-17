"""
问题分析模块 - 大模型驱动
挖掘评论中的核心问题，每个问题附带证据、置信度、矛盾反馈
"""
import os
import json
import dashscope
from dashscope import Generation
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY", "")


def _call_llm(prompt: str) -> str:
    response = Generation.call(
        model="qwen-turbo",
        prompt=prompt,
        temperature=0.3,
        result_format="text"
    )
    if response.status_code != 200:
        raise RuntimeError(f"LLM调用失败: {getattr(response, 'message', response)}")
    return response.output.text


def _extract_json(text: str) -> dict:
    import re
    text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


def analyze_problems(classified_reviews: list, analysis_goal: str) -> dict:
    # 客观统计
    total = len(classified_reviews)
    ratings = [r.get("rating", 0) for r in classified_reviews]
    avg_rating = round(sum(ratings) / total, 2) if total else 0

    rating_dist = {}
    for r in ratings:
        rating_dist[str(r)] = rating_dist.get(str(r), 0) + 1

    category_dist = {}
    for r in classified_reviews:
        cat = r.get("category", "其他")
        category_dist[cat] = category_dist.get(cat, 0) + 1

    statistics = {
        "total_reviews": total,
        "avg_rating": avg_rating,
        "rating_distribution": rating_dist,
        "category_distribution": category_dist
    }

    # 准备评论数据
    sorted_reviews = sorted(classified_reviews, key=lambda x: x.get("rating", 5))
    sample_reviews = sorted_reviews[:30]

    review_texts = []
    for r in sample_reviews:
        review_texts.append(
            f"[ID:{r.get('review_id','?')}|评分:{r.get('rating',0)}|分类:{r.get('category','?')}] "
            f"{r.get('clean_content', r.get('content', ''))[:200]}"
        )
    reviews_block = "\n".join(review_texts)

    prompt = f"""你是一个资深产品分析师。请基于以下用户评论，围绕分析目标挖掘核心问题。

分析目标：{analysis_goal}

用户评论（按评分从低到高排序，共{len(sample_reviews)}条）：
{reviews_block}

请严格以JSON格式返回，不要输出其他内容。格式如下：
{{
  "summary": "整体分析摘要，2-3句话",
  "problems": [
    {{
      "id": "P1",
      "title": "问题标题（简短）",
      "description": "问题详细描述",
      "impact": "影响范围和严重程度",
      "confidence": "高或中或低",
      "sample_count": 涉及的评论数量,
      "contradictions": "是否存在矛盾反馈，没有则填'无'",
      "evidence_review_ids": ["评论ID1", "评论ID2"]
    }}
  ]
}}

要求：
1. 问题必须基于评论中的真实反馈，不要编造
2. 每个问题至少关联2条评论证据
3. 置信度根据证据充分程度判断
4. 如果评论中存在互相矛盾的反馈，必须在contradictions中说明
5. 最多识别8个核心问题"""

    try:
        raw_output = _call_llm(prompt)
        result = _extract_json(raw_output)
    except Exception as e:
        print(f"[分析] 大模型调用失败: {e}")
        result = {
            "summary": f"分析失败: {e}",
            "problems": []
        }

    # 补充证据详情
    review_map = {r.get("review_id"): r for r in classified_reviews}
    for problem in result.get("problems", []):
        evidence = []
        for rid in problem.get("evidence_review_ids", []):
            if rid in review_map:
                r = review_map[rid]
                evidence.append({
                    "review_id": rid,
                    "snippet": r.get("clean_content", r.get("content", ""))[:150],
                    "rating": r.get("rating", 0),
                    "category": r.get("category", "")
                })
        problem["evidence"] = evidence
        del problem["evidence_review_ids"]

    result["statistics"] = statistics
    result["analysis_goal"] = analysis_goal
    result["model"] = "qwen-turbo (DashScope)"
    result["note"] = "statistics为客观统计数据，problems为大模型生成结论"

    return result
