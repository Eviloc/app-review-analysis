# LaienTech iOS App Review Analysis and Version Planning Assessment

## 项目背景
本项目针对美区App Store健身App（Workout for Women: Home Gym, id:839285684）完成用户评论全流程分析，实现从评论采集、清洗、大模型分类分析，最终输出版本规划评估报告。
> 评论数据源：**美国区App Store**

## 技术栈
- Python 3.14
- Conda 虚拟环境：review_analyzer
- openai SDK：调用DeepSeek‑Chat大模型做评论理解、分类、摘要
- JSON：数据中间存储
- Markdown：输出版本规划评估报告

## 项目目录结构
评论整理助手 /
├─ src/                     # 核心业务模块源码
│   ├─ collector.py         # 模块 1：App Store 评论采集，原始数据输出 cache
│   ├─ cleaner.py           # 模块 2：评论文本清洗、过滤无效评论
│   ├─ classifier.py       # 模块 3：调用 DeepSeek 完成评论分类与摘要提取
│   └─ report_generator.py # 模块 4：统计分析，生成版本规划 Markdown 报告
├─ cache/                   # 模块 1 输出：原始采集评论（运行生成，git 忽略）
├─ output/                  # 模块 2‑4 输出：清洗数据、分类结果、report.md 报告（运行生成，git 忽略）
├─ requirements.txt        # Python 依赖清单
├─ .gitignore               # Git 忽略配置
└─ README.md                # 项目说明文档

## 环境部署与运行
### 1. 创建并激活虚拟环境
```powershell
conda activate review_analyzer

### 2. 安装依赖
```pip install -r requirements.txt

### 3. 修改 `src/classifier.py`，填入自己的 DeepSeek api_key

### 4. 按顺序执行完整流水线
    # 步骤1：采集美区App Store评论
    python src/collector.py

    # 步骤2：评论清洗过滤
    python src/cleaner.py

    # 步骤3：大模型评论分类打标签、生成摘要
    python src/classifier.py

    # 步骤4：生成版本规划评估报告 output/report.md
    python src/report_generator.py


## 输出产物说明

1. `cache/*.json`：从 App Store 抓取的原始用户评论
2. `output/cleaned_reviews.json`：清洗过滤后的有效评论数据集
3. `output/classified_reviews.json`：带类别、摘要标签的评论数据
4. `output/report.md`：最终交付 —— 版本规划评估报告，包含统计、问题汇总、迭代版本建议

## 流水线流程

**数据采集 → 评论清洗预处理 → LLM 智能分类 & 摘要提取 → 统计分析 + 版本规划报告生成**

```

保存后提交：
```powershell
# git add README.md
# git commit -m "docs:修复markdown代码块、缩进语法错误"
```

<!-- 导出依赖清单（确认在`review_analyzer`环境） -->

```
pip freeze > requirements.txt
git add requirements.txt
git commit -m "chore:导出项目依赖requirements.txt"
```

#项目全部交付清单

```
评论整理助手/
├─ src/                     # 4份模块源码
├─ cache/                   # 采集原始json数据
├─ output/                  # 3份输出文件，含report.md作业报告
├─ .gitignore
├─ README.md
└─ requirements.txt

> 
> 重要：**不要 git push**，本地 git 保存开发记录即可；上交压缩包务必带上 cache、output 文件夹。

### 查看全部开发提交记录

```
git log --oneline
```