"""
问题分析模块 - 大模型驱动
挖掘评论中的核心问题，每个问题附带证据、置信度、矛盾反馈
"""
import os
import time
import json
import dashscope
from dashscope import Generation
from dotenv import load_dotenv
import random    # 打乱顺序避免模型感知到排序偏差
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY", "")

# 模型可配置：优先读环境变量，默认 qwen-plus
MODEL = os.getenv("LLM_MODEL", "qwen-plus")
def _call_llm(prompt: str) -> str:
    response = Generation.call(
        model=MODEL,
        prompt=prompt,
        temperature=0.3,
        result_format="text",
        max_tokens=4096
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


def _llm_json(prompt: str, retries: int = 2) -> dict:
    """调用模型并解析 JSON；失败自动重试，避免偶发的格式错误毁掉整条链路。"""
    last_err = None
    for _ in range(retries):
        try:
            return _extract_json(_call_llm(prompt))
        except Exception as e:  # 包含调用失败与 JSON 解析失败
            last_err = e
            time.sleep(1)
    raise last_err
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
    # 准备评论数据：改用 1..n 短编号喂给模型。
    # 真实 review_id（长数字）让模型复述极易出错/类型不一致，改为本地换算。
    low_score = [r for r in classified_reviews if r.get("rating", 5) <= 3]
    high_score = [r for r in classified_reviews if r.get("rating", 5) >= 4]
    # 低分取22条，高分取8条，不足则全取
    sample_low = low_score[:22]
    sample_high = high_score[:8]
    sample_reviews = sample_low + sample_high
    random.shuffle(sample_reviews)
    short_map = {str(i): r for i, r in enumerate(sample_reviews, 1)}  # 短编号 → 评论对象
    review_texts = []
    for i, r in enumerate(sample_reviews, 1):
        review_texts.append(
            f"[编号{i}|评分:{r.get('rating',0)}|分类:{r.get('category','?')}] "
            f"{r.get('clean_content', r.get('content', ''))[:200]}"
        )
    reviews_block = "\n".join(review_texts)
    prompt = f"""你是一个资深产品分析师。请基于以下用户评论，围绕分析目标挖掘核心问题。
分析目标：{analysis_goal}
用户评论（包含正负向反馈的混合样本，共{len(sample_reviews)}条，每条开头的[编号x]是该评论的编号）：
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
        "evidence_review_ids": [1, 2]
    }}
    ]
}}
要求：
1. 问题必须基于评论中的真实反馈，不要编造
2. evidence_review_ids 为必填字段，填入支撑该问题的评论编号（1到{len(sample_reviews)}之间的纯数字，至少1条，通常2-3条），不要填其他内容
3. 置信度根据证据充分程度判断
4. 如果评论中存在互相矛盾的反馈，必须在contradictions中说明
5. 最多识别8个核心问题"""
    try:
        result = _llm_json(prompt)
    except Exception as e:
        print(f"[分析] 大模型调用失败: {e}")
        result = {
            "summary": f"分析失败: {e}",
            "problems": []
        }
    # 回填证据详情：ID 全部归一化为字符串后匹配；
    # 兼容模型返回 数字/字符串/"编号1"/"R1" 等写法，也兼容直接给真实 review_id。
    review_map = {str(r.get("review_id")): r for r in classified_reviews}
    for problem in result.get("problems", []):
        raw_ids = problem.pop("evidence_review_ids", [])
        evidence, seen = [], set()
        for rid in raw_ids:
            key = str(rid).strip()
            candidates = [key]
            if not key.isdigit():  # 如 "编号1"、"R1" → 提取数字再试
                digits = "".join(ch for ch in key if ch.isdigit())
                if digits:
                    candidates.append(digits)
            matched = None
            for c in candidates:  # 优先按短编号换算
                if c in short_map:
                    matched = short_map[c]
                    break
            if matched is None:
                for c in candidates:  # 其次兼容真实 review_id
                    if c in review_map:
                        matched = review_map[c]
                        break
            if matched is not None and matched.get("review_id") not in seen:
                seen.add(matched.get("review_id"))
                evidence.append({
                    "review_id": matched.get("review_id"),
                    "snippet": matched.get("clean_content", matched.get("content", ""))[:150],
                    "rating": matched.get("rating", 0),
                    "category": matched.get("category", "")
                })
        problem["evidence"] = evidence
        if not evidence and raw_ids:
            print(f"[分析] 警告: 问题{problem.get('id')}({problem.get('title')}) "
                    f"的证据ID {raw_ids} 未匹配到任何评论（可用编号: {list(short_map)}）")
    result["statistics"] = statistics
    result["analysis_goal"] = analysis_goal
    result["model"] = f"{MODEL} (DashScope)"
    result["note"] = "statistics为客观统计数据，problems为大模型生成结论"
    return result