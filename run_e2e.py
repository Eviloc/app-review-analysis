# -*- coding: utf-8 -*-
"""
在你自己的环境里跑一次完整链路（不需要 MCP 客户端、不需要启动 Streamlit）。

用法（在项目根目录）：
    python run_e2e.py

它会：读取 cache/app_839285684.json → 清洗 → 动态分类 → 问题分析 → PRD
      → 测试用例 → 追溯校验，并在 output/ 下写出 report.md 与 traceability.json。

前提：已安装 requirements.txt 依赖，且 .env 里配好 DASHSCOPE_API_KEY。
注意：分类阶段会逐条调用大模型，5 条评论约 1-2 分钟，会产生少量 API 费用。
"""
import json
import os
import time

REPO = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(REPO, "src")
OUTPUT = os.path.join(REPO, "output")
SAMPLE = os.path.join(REPO, "cache", "app_839285684.json")

import sys

sys.path.insert(0, SRC)

from collector import import_reviews_from_file  # noqa: E402
from cleaner import clean_reviews  # noqa: E402
from classifier import classify_reviews_dynamic  # noqa: E402
from analyzer import analyze_problems  # noqa: E402
from prd_generator import generate_prd  # noqa: E402
from test_generator import generate_test_cases  # noqa: E402
from traceability import build_traceability_chain, validate_traceability  # noqa: E402

GOAL = "全面分析用户核心痛点和产品问题"


def save_json(data, name):
    os.makedirs(OUTPUT, exist_ok=True)
    path = os.path.join(OUTPUT, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def step(label, fn, *args):
    print(f"\n>>> {label}")
    t0 = time.time()
    result = fn(*args)
    print(f"    完成，用时 {time.time() - t0:.1f}s")
    return result


def main():
    if not os.path.exists(SAMPLE):
        raise SystemExit(f"找不到样例数据: {SAMPLE}")
    if not os.getenv("DASHSCOPE_API_KEY"):
        print("提示：未在环境变量中检测到 DASHSCOPE_API_KEY，"
              "若 .env 已配置可忽略（模块导入时会自行加载）")

    with open(SAMPLE, "rb") as f:
        raw = import_reviews_from_file(f)
    print(f"原始评论 {len(raw)} 条")

    cleaned = step("清洗", clean_reviews, raw, 1)
    save_json(cleaned, "cleaned_reviews.json")
    print(f"    保留 {len(cleaned)} 条")

    classified = step("动态分类", classify_reviews_dynamic, cleaned, GOAL)
    save_json(classified, "classified_reviews.json")

    analysis = step("问题分析", analyze_problems, classified, GOAL)
    if not analysis.get("problems"):
        raise SystemExit("问题分析没有产出任何问题，已中止。请检查 API 配额。")
    save_json(analysis, "analysis_result.json")
    print(f"    识别 {len(analysis.get('problems', []))} 个问题")

    prd = step("生成 PRD", generate_prd, analysis, classified)
    if not prd.get("requirements"):
        raise SystemExit("PRD 没有产出任何需求，已中止。")
    save_json(prd, "prd.json")
    print(f"    {len(prd.get('requirements', []))} 条需求")

    cases = step("生成测试用例", generate_test_cases, prd, classified)
    if not cases:
        raise SystemExit("测试用例为空，已中止。")
    save_json(cases, "test_cases.json")
    print(f"    {len(cases)} 条用例")

    trace = build_traceability_chain(classified, analysis, prd, cases)
    validation = validate_traceability(trace)
    save_json({"validation": validation, "links": trace["links"]}, "traceability.json")

    print("\n================ 追溯校验结果 ================")
    print(f"总链路数 : {validation['total']}")
    print(f"有效     : {validation['valid']}")
    print(f"无效     : {validation['invalid']}")
    print(f"通过率   : {validation['pass_rate']}")
    if validation.get("missing_layers"):
        print(f"缺失层级 : {validation['missing_layers']}")
    for item in validation["invalid_items"][:10]:
        print(f"  - {item}")

    report = os.path.join(OUTPUT, "report.md")
    lines = [
        "# App Store 评论分析报告",
        "",
        f"- 评论数：{len(classified)}",
        f"- 核心问题：{len(analysis.get('problems', []))}",
        f"- 需求：{len(prd.get('requirements', []))}",
        f"- 测试用例：{len(cases)}",
        f"- 追溯通过率：{validation['pass_rate']}（{validation['valid']}/{validation['total']}）",
        "",
        "## 一、核心问题",
    ]
    for p in analysis.get("problems", []):
        lines += [
            f"### {p.get('id')} {p.get('title')}（置信度：{p.get('confidence', 'N/A')}）",
            f"- 描述：{p.get('description', '')}",
            f"- 影响：{p.get('impact', '')}",
            f"- 证据：{', '.join(e['review_id'] for e in p.get('evidence', []))}",
        ]
    lines += ["", "## 二、需求"]
    for r in prd.get("requirements", []):
        lines.append(f"- [{r.get('priority')}] {r.get('id')} {r.get('title')}")
    lines += ["", "## 三、测试用例"]
    for t in cases:
        lines.append(f"- {t.get('case_id')} {t.get('title')}（验证 {t.get('related_requirement')}）")

    with open(report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n报告已写入：{report}")


if __name__ == "__main__":
    main()
