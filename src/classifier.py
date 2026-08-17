"""
动态分类模块 - 大模型驱动
根据分析目标动态生成分类体系，不依赖固定关键词
"""
import os
import re
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
        temperature=0.1,
        result_format="text"
    )
    if response.status_code != 200:
        raise RuntimeError(f"LLM调用失败: {getattr(response, 'message', response)}")
    return response.output.text


def _extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


def generate_categories(analysis_goal: str, sample_reviews: list) -> list:
    sample_text = "\n".join([
        f"[{r.get('rating',0)}星] {r.get('clean_content', '')[:100]}"
        for r in sample_reviews[:10]
    ])
    prompt = f"""你是一个产品分析专家。根据以下分析目标和样例评论，设计一套评论分类体系。

分析目标：{analysis_goal}

样例评论：
{sample_text}

请设计5-8个分类标签，要求：
1. 分类要覆盖评论中的主要问题类型
2. 分类名称要简洁明确（2-6个字）
3. 必须包含"其他"分类
4. 分类之间互斥，不重叠

请严格以JSON格式返回：
{{"categories": ["分类1", "分类2", "分类3", "其他"]}}"""

    try:
        raw = _call_llm(prompt)
        result = _extract_json(raw)
        categories = result.get("categories", [])
        if "其他" not in categories:
            categories.append("其他")
        return categories
    except Exception as e:
        print(f"[分类] 动态生成分类失败，使用默认分类: {e}")
        return ["功能Bug", "体验问题", "功能建议", "好评", "其他"]


def classify_single_review(text: str, categories: list) -> dict:
    cat_str = "、".join(categories)
    prompt = f"""你是一个评论分类助手。请对以下评论进行分类，并生成简短摘要。

分类标签（只能选一个）：{cat_str}

评论内容：{text}

请严格以JSON格式返回：
{{"category": "分类标签", "summary": "一句话摘要"}}"""

    try:
        raw = _call_llm(prompt)
        result = _extract_json(raw)
        category = result.get("category", "其他")
        if category not in categories:
            category = "其他"
        return {
            "category": category,
            "summary": result.get("summary", "")
        }
    except Exception as e:
        return {
            "category": "其他",
            "summary": f"分类失败:{str(e)[:50]}"
        }


def classify_reviews_dynamic(cleaned_reviews: list, analysis_goal: str) -> list:
    if not cleaned_reviews:
        return []
    print(f"[分类] 根据分析目标动态生成分分类体系...")
    categories = generate_categories(analysis_goal, cleaned_reviews)
    print(f"[分类] 生成的分类体系: {categories}")
    classified = []
    for i, r in enumerate(cleaned_reviews):
        print(f"[分类] 处理第 {i+1}/{len(cleaned_reviews)} 条...")
        result = classify_single_review(r.get("clean_content", ""), categories)
        r["category"] = result["category"]
        r["summary"] = result["summary"]
        classified.append(r)
    return classified
