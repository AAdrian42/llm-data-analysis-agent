# LLM 数据分析 Agent

面向业务分析人员的“自然语言查数 + 自动出图”产品原型。用户输入业务问题，系统将其转换为结构化分析计划，通过受控 SQL 和 Pandas 工具执行计算，再返回图表、结论、指标口径和完整执行轨迹。

**在线体验：** [aadrian42-data-analysis-agent.streamlit.app](https://aadrian42-data-analysis-agent.streamlit.app/)

> 项目定位：独立个人项目，灵感来自信贷项目中反复查数、对口径和制作图表的工作。默认数据全部为合成演示数据，不代表京东或任何机构的真实客户。

## 核心能力

- 自然语言理解：识别指标、维度、筛选条件、排序和 Top N。
- Function Calling：GPT/Claude 可调用 `describe_dataset` 和 `submit_analysis_plan` 工具；无 API Key 时使用可复现的本地规划器。
- 语义层：集中定义违约率、审批通过率、平均贷款金额等指标口径。
- 安全 SQL：仅允许单条只读查询，限制表、字段、函数、结果行数和执行时长。
- Pandas 质检：检查空结果、样本量、缺失值、数值异常和可视化适配性。
- 自动出图：支持指标卡、柱状图、折线图、热力图和分布图。
- 可解释执行：展示结构化计划、SQL、工具调用和指标定义，不展示模型私有思维过程。
- 离线评测：验证规划准确率、执行成功率、SQL 安全和答案证据完整性。

## 快速开始

```powershell
cd llm_data_analysis_agent
python -m pip install -r requirements.txt
python scripts\build_demo_data.py
python scripts\evaluate.py
streamlit run app.py --server.port 8502
```

应用默认使用 `local` 模式，不需要 API Key。配置 `.env.example` 中的环境变量后，可切换 OpenAI 或 Anthropic Function Calling。

## 示例问题

- 各信用等级的违约率是多少？
- 2025 年各产品的审批通过率，按从高到低排序。
- 最近 12 个月申请量趋势。
- 不同 DTI 区间的违约率和样本量。
- 各地区平均贷款金额最高的前 5 名。
- 不同信用等级和贷款期限的违约率对比。
- 各渠道平均人工审核时长。

## 关键边界

- 默认数据为合成数据，不能用于真实经营判断。
- 大模型只负责生成受约束的分析计划，不直接编造数字。
- SQL 和计算结果由本地工具执行，所有结果均展示口径和查询依据。
- 离线评测集规模有限，不能把评测准确率直接等同于线上真实准确率。
- “提效约 50%”尚未经过真实用户对照实验，当前不应作为实测成果写入简历。

## 项目结构

```text
llm_data_analysis_agent/
|-- app.py
|-- analysis_agent/
|   |-- agent.py               # 多节点编排
|   |-- planner.py             # 本地与 LLM Function Calling 规划
|   |-- semantic_layer.py      # 指标、维度和口径
|   |-- sql_compiler.py        # 计划转 SQL
|   |-- sql_guard.py           # 只读安全校验
|   |-- tools.py               # SQL/Pandas 工具
|   `-- charting.py            # 自动图表
|-- scripts/build_demo_data.py
|-- scripts/evaluate.py
|-- docs/PRD.md
|-- docs/ARCHITECTURE.md
|-- docs/INTERVIEW_GUIDE.md
|-- docs/USER_TEST_PLAN.md
|-- tests/
`-- reports/evaluation_report.json
```
