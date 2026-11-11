# -*- coding: utf-8 -*-
"""
traceability.py 的修复版（只改 validate_traceability，其余保持原样）。

原缺陷
------
原实现遍历的是 links 里「已存在」的链条条目，total 只统计这些条目：

    for pid, rids in links["problem_to_reviews"].items():
        total += 1

因此当某一层整体为空（例如还没生成 PRD），这一层的条目根本不会进入循环，
total 自动变小，valid/total 仍然等于 100% ——「整层缺失」被算成了「全部通过」。

修复原则
--------
1. total 改为「声明的条目数」：len(problems) + len(requirements) + len(test_cases)，
   与链路上实际存在多少条目无关。
2. 三层（问题 / 需求 / 测试用例）任一为空，直接判 0 并写明缺哪一层，
   不再靠分母收缩来「蒙混过关」。
3. 遍历对象也从 links 改为「声明的层」，保证每个条目恰好被检查一次。
"""


def build_traceability_chain(classified_reviews, analysis_result, prd, test_cases) -> dict:
    review_map = {r.get("review_id"): r for r in classified_reviews}
    problem_map = {p["id"]: p for p in analysis_result.get("problems", [])}
    req_map = {r["id"]: r for r in prd.get("requirements", [])}
    tc_map = {t["case_id"]: t for t in test_cases}

    problem_to_reviews = {}
    for pid, p in problem_map.items():
        problem_to_reviews[pid] = [e["review_id"] for e in p.get("evidence", [])]

    req_to_problem = {}
    req_to_reviews = {}
    for rid, req in req_map.items():
        req_to_problem[rid] = req.get("related_problem_id", "")
        req_to_reviews[rid] = req.get("related_review_ids", [])

    tc_to_req = {}
    tc_to_reviews = {}
    for tid, tc in tc_map.items():
        tc_to_req[tid] = tc.get("related_requirement", "")
        tc_to_reviews[tid] = tc.get("related_review_ids", [])

    return {
        "reviews": review_map,
        "problems": problem_map,
        "requirements": req_map,
        "test_cases": tc_map,
        "links": {
            "problem_to_reviews": problem_to_reviews,
            "req_to_problem": req_to_problem,
            "req_to_reviews": req_to_reviews,
            "tc_to_req": tc_to_req,
            "tc_to_reviews": tc_to_reviews,
        },
    }


def validate_traceability(trace: dict) -> dict:
    links = trace.get("links", {})
    reviews = trace.get("reviews", {})
    problems = trace.get("problems", {})
    requirements = trace.get("requirements", {})
    test_cases = trace.get("test_cases", {})

    # --- 1. 先做层级存在性校验：缺任何一整层，直接判 0 ---
    missing_layers = []
    if not problems:
        missing_layers.append("problems（问题层）")
    if not requirements:
        missing_layers.append("requirements（需求层）")
    if not test_cases:
        missing_layers.append("test_cases（测试用例层）")

    total = len(problems) + len(requirements) + len(test_cases)

    if missing_layers:
        return {
            "total": total,
            "valid": 0,
            "invalid": total,
            "pass_rate": "0.0%",
            "missing_layers": missing_layers,
            "invalid_items": [f"整层缺失：{layer}" for layer in missing_layers],
        }

    # --- 2. 逐条校验，遍历「声明的层」而不是「已存在的链路」 ---
    invalid_items = []
    review_ids = set(reviews.keys())

    for pid in problems:
        rids = links.get("problem_to_reviews", {}).get(pid, [])
        if not rids:
            invalid_items.append(f"问题 {pid} 没有关联任何评论")
            continue
        missing = [rid for rid in rids if rid not in review_ids]
        if missing:
            invalid_items.append(f"问题 {pid} 关联的评论ID不存在: {missing}")

    for rid in requirements:
        pid = links.get("req_to_problem", {}).get(rid, "")
        rids = links.get("req_to_reviews", {}).get(rid, [])
        if not pid:
            invalid_items.append(f"需求 {rid} 没有关联问题")
        elif pid not in problems:
            invalid_items.append(f"需求 {rid} 关联的问题 {pid} 不存在")
        if not rids:
            invalid_items.append(f"需求 {rid} 没有关联评论")

    for tid in test_cases:
        rid = links.get("tc_to_req", {}).get(tid, "")
        if not rid:
            invalid_items.append(f"测试用例 {tid} 没有关联需求")
        elif rid not in requirements:
            invalid_items.append(f"测试用例 {tid} 关联的需求 {rid} 不存在")

    valid = total - len(invalid_items)
    return {
        "total": total,
        "valid": valid,
        "invalid": len(invalid_items),
        "invalid_items": invalid_items,
        "pass_rate": f"{valid / total * 100:.1f}%" if total else "0.0%",
        "missing_layers": [],
    }
