# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

"""
追溯校验器的回归测试。

核心用例 test_missing_layer_no_longer_reports_100 直接复现你发现的缺陷：
同一份数据，旧实现报 100%，新实现报 0%。
"""

from traceability import build_traceability_chain, validate_traceability


# ---------- 旧实现（只保留被验证的那段逻辑，用于对照） ----------
def _old_validate(trace):
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
    return {"total": total, "valid": valid, "invalid": len(invalid_items),
            "pass_rate": f"{valid/total*100:.1f}%" if total else "N/A"}


def _full_chain(test_cases=None, prd=None, problems=None):
    return build_traceability_chain(
        classified_reviews=[{"review_id": "r1"}, {"review_id": "r2"}],
        analysis_result={"problems": problems if problems is not None else [
            {"id": "p1", "evidence": [{"review_id": "r1"}, {"review_id": "r2"}]}
        ]},
        prd={"requirements": prd if prd is not None else [
            {"id": "q1", "related_problem_id": "p1", "related_review_ids": ["r1"]}
        ]},
        test_cases=test_cases if test_cases is not None else [
            {"case_id": "t1", "related_requirement": "q1", "related_review_ids": ["r1"]}
        ],
    )


def test_full_chain_passes():
    res = validate_traceability(_full_chain())
    assert res["pass_rate"] == "100.0%", res
    assert res["total"] == 3
    assert res["missing_layers"] == []


def test_missing_layer_no_longer_reports_100():
    """整层缺失（还没生成测试用例）——旧实现 100%，新实现 0%。"""
    trace = _full_chain(test_cases=[])
    old = _old_validate(trace)
    new = validate_traceability(trace)
    assert old["pass_rate"] == "100.0%", f"旧实现应当复现缺陷，实际 {old}"
    assert new["pass_rate"] == "0.0%", f"新实现应当判 0，实际 {new}"
    assert "test_cases（测试用例层）" in new["missing_layers"]


def test_missing_requirements_layer():
    trace = _full_chain(prd=[])
    assert validate_traceability(trace)["pass_rate"] == "0.0%"


def test_missing_problems_layer():
    trace = _full_chain(problems=[])
    assert validate_traceability(trace)["pass_rate"] == "0.0%"


def test_evidence_pointing_to_unknown_review():
    problems = [{"id": "p1", "evidence": [{"review_id": "rX"}]}]
    res = validate_traceability(_full_chain(problems=problems))
    assert res["invalid"] >= 1
    assert any("不存在" in item for item in res["invalid_items"])


def test_problem_without_evidence():
    problems = [{"id": "p1", "evidence": []}]
    res = validate_traceability(_full_chain(problems=problems))
    assert res["pass_rate"] == "66.7%", res
    assert any("没有关联任何评论" in item for item in res["invalid_items"])


def test_tc_pointing_to_unknown_requirement():
    tcs = [{"case_id": "t1", "related_requirement": "qX", "related_review_ids": []}]
    res = validate_traceability(_full_chain(test_cases=tcs))
    assert any("不存在" in item for item in res["invalid_items"])


def test_denominator_is_declared_not_existing():
    """分母 = 声明条目数，而不是链接里恰好存在的条目数。"""
    trace = _full_chain()
    trace["links"]["problem_to_reviews"] = {}  # 人为清空链路映射
    old = _old_validate(trace)
    new = validate_traceability(trace)
    assert old["total"] == 2 and old["pass_rate"] == "100.0%", old
    assert new["total"] == 3, new
    assert new["pass_rate"] == "66.7%", new


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {name}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
