"""
追溯链路管理模块
构建并校验：用户评论 → 分析结论 → 产品需求 → 测试用例
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
            "tc_to_reviews": tc_to_reviews
        }
    }


def validate_traceability(trace: dict) -> dict:
    links = trace["links"]
    review_ids = set(trace["reviews"].keys())
    invalid_items = []
    total = 0

    for pid, rids in links["problem_to_reviews"].items():
        total += 1
        if not rids:
            invalid_items.append(f"问题 {pid} 没有关联任何评论")
        else:
            missing = [rid for rid in rids if rid not in review_ids]
            if missing:
                invalid_items.append(f"问题 {pid} 关联的评论ID不存在: {missing}")

    for rid, pid in links["req_to_problem"].items():
        total += 1
        if not pid:
            invalid_items.append(f"需求 {rid} 没有关联问题")
        elif pid not in trace["problems"]:
            invalid_items.append(f"需求 {rid} 关联的问题 {pid} 不存在")
        rids = links["req_to_reviews"].get(rid, [])
        if not rids:
            invalid_items.append(f"需求 {rid} 没有关联评论")

    for tid, rid in links["tc_to_req"].items():
        total += 1
        if not rid:
            invalid_items.append(f"测试用例 {tid} 没有关联需求")
        elif rid not in trace["requirements"]:
            invalid_items.append(f"测试用例 {tid} 关联的需求 {rid} 不存在")

    valid = total - len(invalid_items)
    return {
        "total": total,
        "valid": valid,
        "invalid": len(invalid_items),
        "invalid_items": invalid_items,
        "pass_rate": f"{valid/total*100:.1f}%" if total else "N/A"
    }
