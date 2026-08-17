"""
App Store 评论智能分析工具 - Streamlit 主入口
完整工作流：采集 → 清洗 → 动态分类 → 问题分析 → PRD → 测试用例 → 追溯校验
"""
import os
import sys
import json
import time
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# 路径配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(BASE_DIR, "src")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
CACHE_DIR = os.path.join(BASE_DIR, "cache")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

sys.path.insert(0, SRC_DIR)
load_dotenv(os.path.join(BASE_DIR, ".env"))

# 导入各模块
from collector import extract_app_id, fetch_appstore_reviews, import_reviews_from_file
from cleaner import clean_reviews
from classifier import classify_reviews_dynamic
from analyzer import analyze_problems
from prd_generator import generate_prd
from test_generator import generate_test_cases
from traceability import validate_traceability, build_traceability_chain

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="App Store 评论智能分析工具",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📱 App Store 评论智能分析工具")
st.caption("基于大模型的评论采集 → 清洗 → 分类 → 问题分析 → PRD → 测试用例 全流程工具")

# ==================== 侧边栏输入 ====================
with st.sidebar:
    st.header("⚙️ 分析配置")

    app_url = st.text_input(
        "App Store 链接（美区）",
        value="https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684",
        help="支持美区 App Store 链接，自动提取 app_id"
    )

    analysis_goal = st.text_area(
        "分析目标 / 约束条件",
        value="重点分析订阅转化问题、健身功能可用性、付费墙用户体验。关注低分评论中的功能缺陷。",
        height=100,
        help="描述你想重点分析的方向，系统会根据目标动态生成分类体系"
    )

    col1, col2 = st.columns(2)
    with col1:
        min_rating = st.slider("最低评分", 1, 5, 1)
    with col2:
        max_pages = st.slider("采集页数", 1, 10, 3)

    st.divider()
    st.subheader("📂 数据导入")
    uploaded_file = st.file_uploader(
        "导入评论数据（JSON/CSV）",
        type=["json", "csv"],
        help="无网络时可导入已有评论数据，字段需包含 content/rating"
    )

    st.divider()
    start_btn = st.button("🚀 开始分析", type="primary", use_container_width=True)

# ==================== 状态管理 ====================
if "workflow_state" not in st.session_state:
    st.session_state.workflow_state = {
        "raw_reviews": [],
        "cleaned_reviews": [],
        "classified_reviews": [],
        "analysis_result": None,
        "prd": None,
        "test_cases": [],
        "traceability": None,
        "current_stage": 0,
        "logs": []
    }

def add_log(msg):
    st.session_state.workflow_state["logs"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
    st.toast(msg, icon="ℹ️")

def save_json(data, filename):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path

# ==================== 工作流执行 ====================
def run_workflow():
    ws = st.session_state.workflow_state
    ws["logs"] = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    # ---------- 阶段1：采集 ----------
    ws["current_stage"] = 1
    status_text.text("📥 阶段1/7：采集评论数据...")
    add_log("开始采集评论数据")

    if uploaded_file is not None:
        add_log(f"检测到上传文件: {uploaded_file.name}")
        raw_reviews = import_reviews_from_file(uploaded_file)
    else:
        app_id = extract_app_id(app_url)
        if not app_id:
            st.error("无法从链接中提取 app_id，请检查链接格式")
            return
        add_log(f"提取到 app_id: {app_id}")
        raw_reviews = fetch_appstore_reviews(app_id, max_pages=max_pages)

    if not raw_reviews:
        st.error("未获取到任何评论数据，请检查网络/代理或导入评论文件")
        return

    ws["raw_reviews"] = raw_reviews
    save_json(raw_reviews, "raw_reviews.json")
    add_log(f"采集完成，共 {len(raw_reviews)} 条评论")
    progress_bar.progress(1/7)

    # ---------- 阶段2：清洗 ----------
    status_text.text("🧹 阶段2/7：清洗去重...")
    add_log("开始清洗评论数据")
    cleaned = clean_reviews(raw_reviews, min_rating=min_rating)
    ws["cleaned_reviews"] = cleaned
    save_json(cleaned, "cleaned_reviews.json")
    add_log(f"清洗完成，保留 {len(cleaned)} 条有效评论")
    progress_bar.progress(2/7)

    # ---------- 阶段3：动态分类 ----------
    status_text.text("🏷️ 阶段3/7：大模型动态分类...")
    add_log("开始动态分类（根据分析目标生成分类体系）")
    classified = classify_reviews_dynamic(cleaned, analysis_goal)
    ws["classified_reviews"] = classified
    save_json(classified, "classified_reviews.json")
    add_log(f"分类完成，共 {len(classified)} 条")
    progress_bar.progress(3/7)

    # ---------- 阶段4：问题分析 ----------
    status_text.text("🔍 阶段4/7：大模型问题分析...")
    add_log("开始问题分析（挖掘痛点、置信度、矛盾反馈）")
    analysis = analyze_problems(classified, analysis_goal)
    ws["analysis_result"] = analysis
    save_json(analysis, "analysis_result.json")
    add_log(f"分析完成，识别 {len(analysis.get('problems', []))} 个核心问题")
    progress_bar.progress(4/7)

    # ---------- 阶段5：PRD 生成 ----------
    status_text.text("📋 阶段5/7：生成 PRD 产品需求...")
    add_log("开始生成 PRD（需求追溯到原始评论）")
    prd = generate_prd(analysis, classified)
    ws["prd"] = prd
    save_json(prd, "prd.json")
    add_log(f"PRD 生成完成，共 {len(prd.get('requirements', []))} 条需求")
    progress_bar.progress(5/7)

    # ---------- 阶段6：测试用例 ----------
    status_text.text("🧪 阶段6/7：生成测试用例...")
    add_log("开始生成测试用例（关联需求和评论）")
    test_cases = generate_test_cases(prd, classified)
    ws["test_cases"] = test_cases
    save_json(test_cases, "test_cases.json")
    add_log(f"测试用例生成完成，共 {len(test_cases)} 条")
    progress_bar.progress(6/7)

    # ---------- 阶段7：追溯校验 ----------
    status_text.text("✅ 阶段7/7：追溯链路校验...")
    add_log("开始追溯校验（检查每条结论是否有证据支撑）")
    trace = build_traceability_chain(classified, analysis, prd, test_cases)
    validation = validate_traceability(trace)
    ws["traceability"] = {"chain": trace, "validation": validation}
    save_json(ws["traceability"], "traceability.json")
    add_log(f"校验完成：{validation['valid']} 条有效，{validation['invalid']} 条无证据")
    progress_bar.progress(7/7)

    status_text.text("✅ 分析完成！")
    add_log("全流程执行完毕")

# ==================== 主逻辑 ====================
if start_btn:
    with st.spinner("正在执行分析工作流..."):
        run_workflow()

# ==================== 结果展示 ====================
ws = st.session_state.workflow_state

if ws["raw_reviews"]:
    st.divider()
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📥 原始评论", "🧹 清洗结果", "🏷️ 分类分析",
        "🔍 问题分析", "📋 PRD", "🧪 测试用例", "✅ 追溯校验"
    ])

    # Tab1: 原始评论
    with tab1:
        st.subheader(f"原始评论（{len(ws['raw_reviews'])} 条）")
        df_raw = pd.DataFrame(ws["raw_reviews"])
        st.dataframe(df_raw, use_container_width=True, height=400)

    # Tab2: 清洗结果
    with tab2:
        st.subheader(f"清洗后评论（{len(ws['cleaned_reviews'])} 条）")
        if ws["cleaned_reviews"]:
            df_clean = pd.DataFrame(ws["cleaned_reviews"])
            st.dataframe(df_clean, use_container_width=True, height=400)
            # 评分分布
            st.subheader("评分分布")
            ratings = [r["rating"] for r in ws["cleaned_reviews"]]
            rating_counts = pd.Series(ratings).value_counts().sort_index()
            st.bar_chart(rating_counts)

    # Tab3: 分类分析
    with tab3:
        st.subheader("动态分类结果")
        if ws["classified_reviews"]:
            df_cls = pd.DataFrame(ws["classified_reviews"])
            st.dataframe(df_cls[["review_id", "rating", "category", "summary"]],
                         use_container_width=True, height=400)
            # 分类统计
            st.subheader("分类分布")
            cat_counts = df_cls["category"].value_counts()
            st.bar_chart(cat_counts)

    # Tab4: 问题分析
    with tab4:
        if ws["analysis_result"]:
            analysis = ws["analysis_result"]
            st.subheader("核心问题分析")
            for i, problem in enumerate(analysis.get("problems", []), 1):
                with st.expander(f"问题{i}: {problem.get('title', '未命名')} "
                                 f"（置信度: {problem.get('confidence', 'N/A')}）"):
                    st.markdown(f"**描述**: {problem.get('description', '')}")
                    st.markdown(f"**影响范围**: {problem.get('impact', '')}")
                    st.markdown(f"**样本数量**: {problem.get('sample_count', 0)} 条评论")
                    if problem.get("contradictions"):
                        st.warning(f"⚠️ 矛盾反馈: {problem['contradictions']}")
                    st.markdown("**证据评论**:")
                    for ev in problem.get("evidence", []):
                        st.caption(f"- [{ev.get('review_id', '')}] {ev.get('snippet', '')[:120]}...")

    # Tab5: PRD
    with tab5:
        if ws["prd"]:
            prd = ws["prd"]
            st.subheader("产品需求文档（PRD）")
            st.markdown(f"**版本规划**: {prd.get('version_plan', '')}")
            for req in prd.get("requirements", []):
                priority_color = {"高": "🔴", "中": "🟡", "低": "🟢"}.get(req.get("priority", ""), "⚪")
                with st.expander(f"{priority_color} [{req.get('priority', '')}] {req.get('title', '')}"):
                    st.markdown(f"**描述**: {req.get('description', '')}")
                    st.markdown(f"**目标版本**: {req.get('target_version', '')}")
                    st.markdown(f"**关联评论ID**: {', '.join(req.get('related_review_ids', []))}")

    # Tab6: 测试用例
    with tab6:
        if ws["test_cases"]:
            st.subheader(f"测试用例（{len(ws['test_cases'])} 条）")
            df_tc = pd.DataFrame(ws["test_cases"])
            display_cols = [c for c in ["case_id", "title", "priority", "related_requirement", "related_review_ids"]
                            if c in df_tc.columns]
            st.dataframe(df_tc[display_cols], use_container_width=True, height=400)

    # Tab7: 追溯校验
    with tab7:
        if ws["traceability"]:
            validation = ws["traceability"]["validation"]
            st.subheader("追溯链路校验结果")
            col1, col2, col3 = st.columns(3)
            col1.metric("总链路数", validation.get("total", 0))
            col2.metric("有效（有证据）", validation.get("valid", 0))
            col3.metric("无效（无证据）", validation.get("invalid", 0))

            if validation.get("invalid_items"):
                st.warning("以下结论/需求缺少原始评论证据支撑：")
                for item in validation["invalid_items"]:
                    st.caption(f"- {item}")
            else:
                st.success("✅ 所有结论均有证据支撑，追溯链路完整")

# 导出按钮
if ws["raw_reviews"]:
    st.divider()
    st.subheader("📤 导出结果")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.download_button("下载分类结果",
                           data=json.dumps(ws["classified_reviews"], ensure_ascii=False, indent=2),
                           file_name="classified_reviews.json", mime="application/json")
    with col2:
        st.download_button("下载分析报告",
                           data=json.dumps(ws["analysis_result"], ensure_ascii=False, indent=2),
                           file_name="analysis_result.json", mime="application/json")
    with col3:
        st.download_button("下载PRD",
                           data=json.dumps(ws["prd"], ensure_ascii=False, indent=2),
                           file_name="prd.json", mime="application/json")
    with col4:
        st.download_button("下载测试用例",
                           data=json.dumps(ws["test_cases"], ensure_ascii=False, indent=2),
                           file_name="test_cases.json", mime="application/json")

# 运行日志
if ws["logs"]:
    with st.expander("📜 运行日志"):
        for log in ws["logs"]:
            st.text(log)
