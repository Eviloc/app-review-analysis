"""
PRD 生成模块 - 大模型驱动
基于问题分析生成产品需求，每条需求追溯到原始评论
"""
import os
import json
import re
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
    text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


def generate_prd(analysis_result: dict, classified_reviews: list) -> dict:
    problems = analysis_result.get("problems", [])
    if not problems:
        return {"version_plan": "无足够数据生成PRD", "requirements": [], "note": "问题分析结果为空"}

    problems_text = []
    for p in problems:
        problems_text.append(
            f"问题{p['id']}: {p['title']}\n"
            f"  描述: {p['description']}\n"
            f"  影响: {p['impact']}\n"
            f"  置信度: {p['confidence']}\n"
            f"  关联评论ID: {[e['review_id'] for e in p.get('evidence', [])]}"
        )
    problems_block = "\n\n".join(problems_text)

    prompt = f"""你是一个资深产品经理。请基于以下用户问题分析，生成产品需求文档（PRD）。

分析目标：{analysis_result.get('analysis_goal', '')}

识别到的核心问题：
{problems_block}

请严格以JSON格式返回，不要输出其他内容。格式如下：
{{
  "version_plan": "版本规划整体说明，2-3句话",
  "requirements": [
    {{
      "id": "REQ-001",
      "title": "需求标题",
      "description": "需求详细描述，包含用户场景和解决的问题",
      "priority": "高或中或低",
      "target_version": "V1.1或V1.2或V1.3",
      "related_problem_id": "P1",
      "related_review_ids": ["评论ID1", "评论ID2"],
      "acceptance_criteria": ["验收标准1", "验收标准2", "验收标准3"]
    }}
  ]
}}

要求：
1. 每条需求必须关联至少一个问题ID和至少2条评论ID
2. 高优先级需求放入V1.1（修复Bug和严重体验问题）
3. 中优先级需求放入V1.2（功能迭代）
4. 低优先级需求放入V1.3（体验增强）
5. 需求描述要具体可执行，不要空泛
6. 验收标准要可验证
7. 最多生成10条需求"""

    try:
        raw_output = _call_llm(prompt)
        result = _extract_json(raw_output)
    except Exception as e:
        print(f"[PRD] 大模型调用失败: {e}")
        result = {"version_plan": f"PRD生成失败: {e}", "requirements": []}

    result["model"] = "qwen-turbo (DashScope)"
    result["note"] = "需求均关联原始评论ID，可追溯"
    return result
