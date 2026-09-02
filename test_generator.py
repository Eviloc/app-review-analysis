"""
测试用例生成模块 - 大模型驱动
基于 PRD 生成测试用例，每条用例关联需求和原始评论
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
        temperature=0.2,
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


def generate_test_cases(prd: dict, classified_reviews: list) -> list:
    requirements = prd.get("requirements", [])
    if not requirements:
        return []

    req_texts = []
    for req in requirements:
        req_texts.append(
            f"需求{req['id']}: {req['title']}\n"
            f"  描述: {req['description']}\n"
            f"  优先级: {req['priority']}\n"
            f"  关联评论ID: {req.get('related_review_ids', [])}\n"
            f"  验收标准: {req.get('acceptance_criteria', [])}"
        )
    req_block = "\n\n".join(req_texts)

    all_review_ids = set()
    for req in requirements:
        all_review_ids.update(req.get("related_review_ids", []))

    review_map = {r.get("review_id"): r for r in classified_reviews}
    review_details = []
    for rid in all_review_ids:
        if rid in review_map:
            r = review_map[rid]
            review_details.append(
                f"[{rid}] 评分:{r.get('rating',0)} - {r.get('clean_content', r.get('content',''))[:100]}"
            )
    review_block = "\n".join(review_details)

    prompt = f"""你是一个资深测试工程师。请基于以下产品需求生成测试用例。

产品需求：
{req_block}

关联的用户评论（用于理解用户痛点）：
{review_block}

请严格以JSON格式返回，不要输出其他内容。格式如下：
{{
  "test_cases": [
    {{
      "case_id": "TC-001",
      "title": "用例标题",
      "related_requirement": "REQ-001",
      "related_review_ids": ["评论ID1"],
      "priority": "高或中或低",
      "preconditions": "前置条件描述",
      "steps": ["操作步骤1", "操作步骤2", "操作步骤3"],
      "expected_result": "预期结果，要具体可验证",
      "test_type": "功能测试或性能测试或体验测试或兼容性测试"
    }}
  ]
}}

要求：
1. 每条需求至少生成1条测试用例
2. 测试用例必须能验证需求是否解决了用户评论中的问题
3. 步骤要具体可执行，预期结果要可验证
4. 高优先级需求的用例优先级也设为高
5. 覆盖功能、性能、体验等不同测试类型
6. 最多生成15条测试用例"""

    try:
        raw_output = _call_llm(prompt)
        result = _extract_json(raw_output)
        test_cases = result.get("test_cases", [])
    except Exception as e:
        print(f"[测试用例] 大模型调用失败: {e}")
        test_cases = []

    for tc in test_cases:
        tc["model"] = "qwen-turbo (DashScope)"
        tc["note"] = "测试用例关联需求ID和评论ID，可追溯"

    return test_cases
