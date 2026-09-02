"""
MCP Server: App Store 评论智能分析工具
将流水线（采集→清洗→动态分类→问题分析→PRD→测试用例→追溯校验）
封装为 8 个 MCP 工具，供 Claude Desktop / Cursor 等客户端调用。
依赖:  pip install "mcp[cli]"        （装在 review_analyzer 环境）
调试:  mcp dev mcp_server.py         （打开 MCP Inspector，需 Node.js）
运行:  由 MCP 客户端按 stdio 拉起，无需手动运行
"""
import os
import sys
import json
import threading
from contextlib import contextmanager
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(BASE_DIR, "src")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
SAMPLE_DATA = os.path.join(BASE_DIR, "cache", "app_839285684.json")
sys.path.insert(0, SRC_DIR)
from mcp.server.fastmcp import FastMCP
# 复用现有业务模块（导入时各自完成 .env 加载与 api_key 设置）
from collector import fetch_appstore_reviews, extract_app_id, import_reviews_from_file
from cleaner import clean_reviews
from classifier import classify_reviews_dynamic
from analyzer import analyze_problems as _analyze_problems
from prd_generator import generate_prd as _generate_prd
from test_generator import generate_test_cases as _generate_test_cases
from traceability import build_traceability_chain, validate_traceability as _validate_traceability
mcp = FastMCP(
	"app-review-analyzer",
	instructions="App Store 评论分析流水线。典型用法：load_reviews 加载数据 → "
					"classify_reviews 分类 → analyze_problems 分析问题 → generate_prd → "
					"generate_test_cases → validate_traceability；或直接 run_full_analysis 一键完成。",
)
# ---------------- 会话状态与基础设施 ----------------
_lock = threading.Lock()  # 工具串行执行，保护共享状态
_state = {
	"source": "",
	"analysis_goal": "",
	"raw_reviews": [],
	"cleaned_reviews": [],
	"classified_reviews": [],
	"analysis_result": None,
	"prd": None,
	"test_cases": [],
}
@contextmanager
def _stdout_to_stderr():
	"""把业务模块的 print() 重定向到 stderr。
	stdio 传输下 stdout 是 MCP 协议通道，src 模块的进度 print 会破坏协议。
	传输层启动时已绑定真正的 stdout，运行期临时替换 sys.stdout 不影响协议。
	"""
	old = sys.stdout
	sys.stdout = sys.stderr
	try:
		yield
	finally:
		sys.stdout = old
def _guarded(impl, **kwargs):
	"""统一入口：串行 + print 重定向 + 异常兜底，任何失败都返回结构化结果"""
	with _lock, _stdout_to_stderr():
		try:
			return impl(**kwargs)
		except Exception as e:
			return {"ok": False, "error": f"{type(e).__name__}: {e}"}
def _save_json(data, filename):
	os.makedirs(OUTPUT_DIR, exist_ok=True)
	path = os.path.join(OUTPUT_DIR, filename)
	with open(path, "w", encoding="utf-8") as f:
		json.dump(data, f, ensure_ascii=False, indent=2)
	return path
def _require(*stages):
	"""前置阶段检查；全部满足返回 None，否则返回错误提示"""
	checks = {
		"loaded": ("还没有已加载的评论数据", "先调用 load_reviews"),
		"classified": ("评论还没有分类", "先调用 classify_reviews"),
		"analyzed": ("还没有问题分析结果", "先调用 analyze_problems"),
		"prd": ("还没有生成 PRD", "先调用 generate_prd"),
	}
	have = {
		"loaded": bool(_state["cleaned_reviews"]),
		"classified": bool(_state["classified_reviews"]),
		"analyzed": _state["analysis_result"] is not None,
		"prd": _state["prd"] is not None,
	}
	for s in stages:
		if not have[s]:
			return {"ok": False, "error": checks[s][0], "hint": checks[s][1]}
	return None
# ---------------- 各阶段内部实现（无锁无重定向，供工具与全流程复用） ----------------
def _impl_load(app_url="", file_path="", use_sample_data=False, max_pages=3, min_rating=1):
	if err := _require():  # 占位，保持结构一致
		return err
	# 数据来源三选一：样例 > 本地文件 > 在线采集
	if use_sample_data:
		if not os.path.exists(SAMPLE_DATA):
			return {"ok": False, "error": f"样例数据不存在: {SAMPLE_DATA}"}
		with open(SAMPLE_DATA, "rb") as f:
			raw = import_reviews_from_file(f)
		_state["source"] = "内置样例数据 cache/app_839285684.json"
	elif file_path:
		if not os.path.exists(file_path):
			return {"ok": False, "error": f"文件不存在: {file_path}"}
		if os.path.splitext(file_path)[1].lower() not in (".json", ".csv"):
			return {"ok": False, "error": "仅支持 .json / .csv 文件"}
		with open(file_path, "rb") as f:
			raw = import_reviews_from_file(f)
		_state["source"] = f"本地文件 {os.path.basename(file_path)}"
	elif app_url:
		app_id = extract_app_id(app_url)
		if not app_id:
			return {"ok": False, "error": "无法从链接提取 app_id，请检查 App Store 链接格式"}
		raw = fetch_appstore_reviews(app_id, max_pages=max_pages)
		_state["source"] = f"App Store 在线采集 (app_id={app_id}, {max_pages}页)"
	else:
		return {"ok": False, "error": "必须提供 app_url / file_path / use_sample_data 之一"}
	if not raw:
		return {"ok": False, "error": "未获取到评论数据",
				"hint": "在线采集需在 .env 配置美国代理；无代理环境可传 use_sample_data=true 快速演示"}
	cleaned = clean_reviews(raw, min_rating=min_rating)
	if not cleaned:
		return {"ok": False, "error": f"清洗后无有效评论（原始 {len(raw)} 条）", "hint": "尝试调低 min_rating"}
	# 加载新数据 → 重置下游阶段
	_state.update({
		"raw_reviews": raw, "cleaned_reviews": cleaned,
		"classified_reviews": [], "analysis_result": None, "prd": None, "test_cases": [],
	})
	_save_json(raw, "raw_reviews.json")
	_save_json(cleaned, "cleaned_reviews.json")
	rating_dist = {}
	for r in cleaned:
		rating_dist[str(r["rating"])] = rating_dist.get(str(r["rating"]), 0) + 1
	return {
		"ok": True,
		"source": _state["source"],
		"raw_count": len(raw),
		"cleaned_count": len(cleaned),
		"rating_distribution": dict(sorted(rating_dist.items())),
		"preview": [{"rating": r["rating"], "content": r["clean_content"][:80]} for r in cleaned[:3]],
		"next_step": "调用 classify_reviews，传入 analysis_goal（分析目标）",
	}
def _impl_classify(analysis_goal="", limit=50):
	if err := _require("loaded"):
		return err
	goal = analysis_goal or _state["analysis_goal"] or "全面分析用户核心痛点和产品问题"
	target = _state["cleaned_reviews"][: max(1, limit)]
	classified = classify_reviews_dynamic(target, goal)
	_state["classified_reviews"] = classified
	_state["analysis_goal"] = goal
	_save_json(classified, "classified_reviews.json")
	dist = {}
	for r in classified:
		dist[r["category"]] = dist.get(r["category"], 0) + 1
	return {"ok": True, "analysis_goal": goal, "classified_count": len(classified),
			"category_distribution": dist,
			"next_step": "调用 analyze_problems 挖掘核心问题（约10-30秒）"}
def _impl_analyze(analysis_goal=""):
	if err := _require("classified"):
		return err
	goal = analysis_goal or _state["analysis_goal"]
	result = _analyze_problems(_state["classified_reviews"], goal)
	_state["analysis_result"] = result
	_save_json(result, "analysis_result.json")
	problems = result.get("problems", [])
	return {
		"ok": True,
		"summary": result.get("summary", ""),
		"statistics": result.get("statistics", {}),
		"problem_count": len(problems),
		"problems": [
			{"id": p.get("id"), "title": p.get("title"), "confidence": p.get("confidence"),
				"evidence_count": len(p.get("evidence", [])), "contradictions": p.get("contradictions", "无")}
			for p in problems
		],
		"next_step": "调用 generate_prd 生成产品需求文档",
	}
def _impl_prd():
	if err := _require("analyzed"):
		return err
	prd = _generate_prd(_state["analysis_result"], _state["classified_reviews"])
	_state["prd"] = prd
	_save_json(prd, "prd.json")
	reqs = prd.get("requirements", [])
	return {
		"ok": True,
		"version_plan": prd.get("version_plan", ""),
		"requirement_count": len(reqs),
		"requirements": [
			{"id": r.get("id"), "title": r.get("title"),
				"priority": r.get("priority"), "target_version": r.get("target_version")}
			for r in reqs
		],
		"next_step": "调用 generate_test_cases 生成测试用例",
	}
def _impl_test_cases():
	if err := _require("prd"):
		return err
	cases = _generate_test_cases(_state["prd"], _state["classified_reviews"])
	_state["test_cases"] = cases
	_save_json(cases, "test_cases.json")
	return {
		"ok": True,
		"test_case_count": len(cases),
		"cases": [
			{"case_id": t.get("case_id"), "title": t.get("title"),
				"priority": t.get("priority"), "related_requirement": t.get("related_requirement")}
			for t in cases
		],
		"next_step": "调用 validate_traceability 校验全链路证据完整性",
	}
def _impl_validate():
	if err := _require("analyzed", "prd"):
		return err
	trace = build_traceability_chain(
		_state["classified_reviews"], _state["analysis_result"],
		_state["prd"], _state["test_cases"],
	)
	validation = _validate_traceability(trace)
	_save_json({"validation": validation, "links": trace["links"]}, "traceability.json")
	return {"ok": True, **validation}
def _save_markdown_report():
	"""汇总各阶段结果为 Markdown 报告（可直接阅读，也方便简历/演示）"""
	a, prd, tcs = _state["analysis_result"], _state["prd"], _state["test_cases"]
	lines = [
		"# App Store 评论分析报告", "",
		f"- 数据来源：{_state['source']}",
		f"- 分析目标：{_state['analysis_goal']}",
		f"- 评论数：{len(_state['classified_reviews'])} | "
		f"核心问题：{len(a.get('problems', []))} | 需求：{len(prd.get('requirements', []))} | "
		f"测试用例：{len(tcs)}", "",
		"## 一、核心问题",
	]
	for p in a.get("problems", []):
		lines += [f"### {p.get('id')} {p.get('title')}（置信度：{p.get('confidence', 'N/A')}）",
					f"- 描述：{p.get('description', '')}", f"- 影响：{p.get('impact', '')}"]
		if p.get("contradictions") and p["contradictions"] != "无":
			lines.append(f"- ⚠️ 矛盾反馈：{p['contradictions']}")
	lines += ["", "## 二、产品需求（PRD）", prd.get("version_plan", ""), ""]
	for r in prd.get("requirements", []):
		lines.append(f"- **[{r.get('priority')}] {r.get('id')} {r.get('title')}"
						f"（{r.get('target_version', '')}）**：{r.get('description', '')}")
	lines += ["", "## 三、测试用例", ""]
	for t in tcs:
		lines.append(f"- **{t.get('case_id')} {t.get('title')}**"
						f"（{t.get('priority', '')}，验证 {t.get('related_requirement', '')}）")
	path = os.path.join(OUTPUT_DIR, "report.md")
	with open(path, "w", encoding="utf-8") as f:
		f.write("\n".join(lines))
	return path
def _impl_run_full(app_url="", file_path="", use_sample_data=False,
					analysis_goal="全面分析用户核心痛点和产品问题",
					max_pages=3, min_rating=1, classify_limit=50):
	steps = [
		("load_reviews", _impl_load,
			dict(app_url=app_url, file_path=file_path, use_sample_data=use_sample_data,
				max_pages=max_pages, min_rating=min_rating)),
		("classify_reviews", _impl_classify, dict(analysis_goal=analysis_goal, limit=classify_limit)),
		("analyze_problems", _impl_analyze, dict(analysis_goal=analysis_goal)),
		("generate_prd", _impl_prd, {}),
		("generate_test_cases", _impl_test_cases, {}),
		("validate_traceability", _impl_validate, {}),
	]
	results = {}
	for name, impl, kwargs in steps:
		r = impl(**kwargs)
		results[name] = r
		if not r.get("ok"):
			return {"ok": False, "failed_at": name, "error": r.get("error"),
					"completed_steps": [k for k in results if results[k].get("ok")]}
	report = _save_markdown_report()
	return {
		"ok": True,
		"source": _state["source"],
		"analysis_goal": _state["analysis_goal"],
		"review_count": results["load_reviews"]["cleaned_count"],
		"problem_count": results["analyze_problems"]["problem_count"],
		"requirement_count": results["generate_prd"]["requirement_count"],
		"test_case_count": results["generate_test_cases"]["test_case_count"],
		"traceability_pass_rate": results["validate_traceability"].get("pass_rate"),
		"output_files": {
			"report": report,
			"analysis": os.path.join(OUTPUT_DIR, "analysis_result.json"),
			"prd": os.path.join(OUTPUT_DIR, "prd.json"),
			"test_cases": os.path.join(OUTPUT_DIR, "test_cases.json"),
			"traceability": os.path.join(OUTPUT_DIR, "traceability.json"),
		},
	}
def _impl_get_results(stage="status", max_items=20):
	if stage == "status":
		return {
			"ok": True,
			"source": _state["source"] or "(未加载数据)",
			"analysis_goal": _state["analysis_goal"] or "(未设置)",
			"stages_done": {
				"load_reviews": bool(_state["cleaned_reviews"]),
				"classify_reviews": bool(_state["classified_reviews"]),
				"analyze_problems": _state["analysis_result"] is not None,
				"generate_prd": _state["prd"] is not None,
				"generate_test_cases": bool(_state["test_cases"]),
			},
			"counts": {"raw": len(_state["raw_reviews"]),
						"cleaned": len(_state["cleaned_reviews"]),
						"classified": len(_state["classified_reviews"])},
		}
	if stage == "classified":
		data = _state["classified_reviews"]
		if not data:
			return {"ok": False, "error": "还没有分类数据", "hint": "get_results(stage='status') 查看进度"}
		items = [{c: r.get(c) for c in ("review_id", "rating", "category", "summary")}
					for r in data[:max_items]]
		return {"ok": True, "total": len(data), "showing": len(items), "items": items}
	if stage == "test_cases":
		data = _state["test_cases"]
		if not data:
			return {"ok": False, "error": "还没有测试用例", "hint": "先调用 generate_test_cases"}
		return {"ok": True, "total": len(data), "showing": min(len(data), max_items),
				"items": data[:max_items]}
	if stage == "analysis":
		if not _state["analysis_result"]:
			return {"ok": False, "error": "还没有分析结果", "hint": "先调用 analyze_problems"}
		return {"ok": True, "data": _state["analysis_result"]}
	if stage == "prd":
		if not _state["prd"]:
			return {"ok": False, "error": "还没有 PRD", "hint": "先调用 generate_prd"}
		return {"ok": True, "data": _state["prd"]}
	return {"ok": False, "error": f"未知 stage: {stage}",
			"hint": "可选: status / classified / analysis / prd / test_cases"}
# ---------------- MCP 工具定义（docstring 即工具描述，会展示给客户端模型） ----------------
@mcp.tool()
def load_reviews(app_url: str = "", file_path: str = "", use_sample_data: bool = False,
					max_pages: int = 3, min_rating: int = 1) -> dict:
	"""加载 App Store 评论数据并完成清洗（流水线第一步）。
	数据来源三选一，优先级：use_sample_data > file_path > app_url。
	- app_url：美区 App Store 链接（服务器 .env 需已配置美国代理）
	- file_path：本地 JSON/CSV 评论文件路径（需含 content/rating 字段）
	- use_sample_data：使用内置样例数据（无需网络，适合演示和测试）
	- max_pages：在线采集页数 1-10，每页约 50 条
	- min_rating：仅保留不低于该评分的评论，1-5
	"""
	return _guarded(_impl_load, app_url=app_url, file_path=file_path,
					use_sample_data=use_sample_data, max_pages=max_pages, min_rating=min_rating)
@mcp.tool()
def classify_reviews(analysis_goal: str = "", limit: int = 50) -> dict:
	"""对已加载的评论做动态分类：先根据分析目标生成分类体系，再逐条分类。
	前置：load_reviews。逐条调用大模型，50 条约 1-3 分钟，请耐心等待。
	- analysis_goal：分析目标/约束条件，决定分类体系，
		例如"重点分析订阅转化问题与付费墙用户体验"
	- limit：最多分类的评论条数（控制耗时与成本）
	"""
	return _guarded(_impl_classify, analysis_goal=analysis_goal, limit=limit)
@mcp.tool()
def analyze_problems(analysis_goal: str = "") -> dict:
	"""挖掘评论中的核心问题：标题、描述、影响范围、置信度、矛盾反馈，每条问题附评论证据。
	前置：classify_reviews。单次大模型调用，约 10-30 秒。
	完整证据明细可用 get_results(stage="analysis") 查看。
	"""
	return _guarded(_impl_analyze, analysis_goal=analysis_goal)
@mcp.tool()
def generate_prd() -> dict:
	"""基于问题分析生成产品需求文档（PRD）：需求描述、优先级、目标版本、验收标准，
	每条需求追溯到问题 ID 与原始评论 ID。前置：analyze_problems。
	"""
	return _guarded(_impl_prd)
@mcp.tool()
def generate_test_cases() -> dict:
	"""基于 PRD 生成测试用例：操作步骤、预期结果、测试类型，
	每条用例关联需求 ID 和评论 ID。前置：generate_prd。
	"""
	return _guarded(_impl_test_cases)
@mcp.tool()
def validate_traceability() -> dict:
	"""校验追溯链路完整性：评论→问题→需求→测试用例，
	检查每条结论是否有关联评论证据，输出通过率与无证据项清单。
	前置：analyze_problems 与 generate_prd（测试用例可选）。
	"""
	return _guarded(_impl_validate)
@mcp.tool()
def run_full_analysis(app_url: str = "", file_path: str = "", use_sample_data: bool = False,
						analysis_goal: str = "全面分析用户核心痛点和产品问题",
						max_pages: int = 3, min_rating: int = 1, classify_limit: int = 50) -> dict:
	"""一键执行完整流水线：加载→分类→问题分析→PRD→测试用例→追溯校验，并生成 Markdown 报告。
	适合一次性出完整报告，总耗时约 3-8 分钟（取决于评论条数）。
	若客户端有工具超时限制，请改用分步工具：
	load_reviews → classify_reviews → analyze_problems → generate_prd → generate_test_cases → validate_traceability
	"""
	return _guarded(_impl_run_full, app_url=app_url, file_path=file_path,
					use_sample_data=use_sample_data, analysis_goal=analysis_goal,
					max_pages=max_pages, min_rating=min_rating, classify_limit=classify_limit)
@mcp.tool()
def get_results(stage: str = "status", max_items: int = 20) -> dict:
	"""查看流水线状态或某阶段结果明细。
	- stage="status"：各阶段完成情况与数据量（默认）
	- stage="classified"：分类明细（review_id/评分/分类/摘要）
	- stage="analysis"：问题分析完整结果（含证据）
	- stage="prd"：PRD 完整结果
	- stage="test_cases"：测试用例明细
	- max_items：列表类结果返回条数上限，防止占用过多上下文
	"""
	return _guarded(_impl_get_results, stage=stage, max_items=max_items)
if __name__ == "__main__":
	mcp.run()  # stdio 模式，由 MCP 客户端拉起