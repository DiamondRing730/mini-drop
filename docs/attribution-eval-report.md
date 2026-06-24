# Mini-Drop 智能归因评测报告

> 本报告由 `tools/eval_attribution.py` 自动生成,所有数字均可 `python tools/eval_attribution.py` 复现。

> 生成时间(由调用方注入):2026-06-21 11:06:36 UTC

## 一、摘要

| 指标 | 离线引擎(确定性规则) | DeepSeek(真实 LLM) |
|---|---|---|
| 根因 Top-1 命中率 | 100.0% | 100.0% |
| 首条引用 self_pct 平均误差(百分点) | 0.0 | 0.0 |
| 校验通过率(结论可独立核对) | 100.0% | 100.0% |
| 校验器防幻觉准确率 | **100.0%**(对两种引擎通用) | |

**结论一句话**:离线引擎按构造必然命中热点、数字零误差,是稳定的安全基线;DeepSeek 需自行通过工具推理,命中率与数字准确性见上表;无论哪个引擎,独立校验器都能以高准确率拦截被造假/算错的结论,确保"可验证"。

## 二、评测方法

- **数据集**:5 个带标准答案的合成 profile(标准答案 = 设计上自耗时最高的函数)+ 运行栈上的真实任务 profile。

- **被测对象**:同一套受约束的只读工具(get_profile_summary / get_top_functions / get_hot_path / get_function_callers),两个引擎——离线确定性规则、DeepSeek 真实工具调用循环。

- **指标**:① 根因 Top-1 命中率(引擎首条根因是否等于 profile 实测最热函数);② 引用 self_pct 与实测值的绝对误差;③ 校验通过率;④ 校验器对真话/谎言的查全率与特异度。

- **校验口径**:声称的 self_pct 与从原始 profile 重新推导的值相差 ≤ 1.0 个百分点即判通过,函数必须确实是自耗时热点,否则判失败。

## 三、归因准确性(逐场景)

### 离线引擎

| 场景 | 标准答案 | 引擎 Top-1 | 命中 | self_pct 误差 | 校验 |
|---|---|---|---|---|---|
| cpu-before(朴素递归 fib 主导) | fib | fib | ✓ | 0.0 | 3/3 |
| cpu-after(fib 经 lru_cache 消除) | crunch_numbers | crunch_numbers | ✓ | 0.0 | 3/3 |
| numeric(两个相近的数值循环) | crunch_numbers | crunch_numbers | ✓ | 0.0 | 3/3 |
| io(read 主导) | read_file | read_file | ✓ | 0.0 | 3/3 |
| flat(无明显热点,近似平局) | f1 | f1 | ✓ | 0.0 | 3/3 |

### DeepSeek 引擎(真实 LLM,实跑)

| 场景 | 标准答案 | 引擎 Top-1 | 命中 | self_pct 误差 | 校验 |
|---|---|---|---|---|---|
| cpu-before(朴素递归 fib 主导) | fib | fib | ✓ | 0.0 | 3/3 |
| cpu-after(fib 经 lru_cache 消除) | crunch_numbers | crunch_numbers | ✓ | 0.0 | 3/3 |
| numeric(两个相近的数值循环) | crunch_numbers | crunch_numbers | ✓ | 0.0 | 2/2 |
| io(read 主导) | read_file | read_file | ✓ | 0.0 | 3/3 |
| flat(无明显热点,近似平局) | f1 | f1 | ✓ | 0.0 | 5/5 |

## 四、校验器防幻觉能力(测谎)

把校验器当"测谎仪":灌入若干真话与谎言(虚构函数、虚高/虚低百分比、缺数字、越界),看它能否正确判定。这是"可验证结论"的核心保障——无论 LLM 说什么,数字都要过这一关。

| 输入结论 | 期望 | 校验器判定 | 正确 |
|---|---|---|---|
| 真话·首热点 fib=74.0 | pass | pass | ✓ |
| 真话·容差内 fib=74.6 | pass | pass | ✓ |
| 真话·次热点 crunch=16.0 | pass | pass | ✓ |
| 谎言·虚构函数 ghost=50 | fail | fail | ✓ |
| 谎言·虚高 fib=95 | fail | fail | ✓ |
| 谎言·虚低 fib=30 | fail | fail | ✓ |
| 谎言·缺数字 fib=None | fail | fail | ✓ |
| 谎言·越界 fib=75.5 | fail | fail | ✓ |

- 谎言查全率(抓住造假结论):**100.0%**(5/5)
- 真话特异度(不误伤真实结论):**100.0%**(3/3)
- 查准率:100.0% · 总体准确率:**100.0%**

## 五、真实任务上的实跑

对运行栈上真实采集的 profile 各跑一次,标准答案取该 profile 实测最热函数。

| 任务 | 引擎 | Top-1 | 命中 | self_pct 误差 | 校验 |
|---|---|---|---|---|---|
| demo-cpu-after-optimized | offline | warm_path | ✓ | 0.0 | 3/3 |
| demo-cpu-after-optimized | deepseek | warm_path | ✓ | 0.0 | 3/3 |
| demo-cpu-after-optimized | offline | warm_path | ✓ | 0.0 | 3/3 |
| demo-cpu-after-optimized | deepseek | warm_path | ✓ | 0.0 | 3/3 |
| demo-cpu-before-baseline | offline | fib | ✓ | 0.0 | 3/3 |
| demo-cpu-before-baseline | deepseek | fib | ✓ | 0.0 | 4/4 |
| pyspy-pid68085 | offline | warm_path | ✓ | 0.0 | 3/3 |
| pyspy-pid68085 | deepseek | warm_path | ✓ | 0.0 | 4/4 |

## 六、结论与复现

1. **可验证**:每条结论的数字都被独立校验器对照原始 profile 复核,测谎准确率见第四节,被造假或算错的结论无法通过。

2. **双引擎**:离线引擎是零误差的确定性基线(无需网络/Key,保证可复现演示);DeepSeek 提供真实 LLM 归因,且受同一套只读工具约束、过同一道校验闸门。

3. **复现**:`python tools/eval_attribution.py`(在 server 容器内,配 DEEPSEEK_API_KEY 则附带 LLM 实跑)。原始结果同时写入 `docs/attribution-eval-results.json`。
