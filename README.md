# Deepvan 投研 Skill 项目

这个项目想做一件比较朴素、但很费工的事：把 Deepvan 这类投资创作者的原文、图片表格、调仓记录和判断逻辑，整理成一套可以反复调用的研究工具。

它不是“模仿某个人说话”的玩具。更准确地说，它会学习一套投研工作方式：先问交易问题，再找主导变量，再映射到可买资产，最后留下组合变化和反证条件。说人话就是：别只记结论，要把他为什么这么想、怎么下手、后面怎么证明对错，都拆出来。

> 免责声明：本项目只做公开内容整理、结构化抽取和历史复盘，不构成投资建议。

## 现在做到哪了

截至 2026-07-10，本地已经把当前主页列表里发现的原文 URL 补了一轮。

| 项目 | 当前结果 |
|---|---:|
| 主页列表原始行 | 126 |
| 规范化后的原文 URL | 101 |
| 已缓存原文 | 106 |
| 当前列表缺失原文 | 0 |
| 缓存文本量 | 约 27.1 万字 |
| 图片 URL | 2078 个 |
| 有效 OCR 原文 | 53 篇 |
| OCR 文本 | 约 5.9 万字 |
| 当前缓存时间范围 | 2024-07-23 到 2026-07-10 |

为什么缓存原文是 106，反而比 101 个 URL 多？因为之前还通过候选抓取和旧接口线索补过一些额外原文。这个是好事，不是重复计数。

但这里要讲清楚：这还不等于“Deepvan 从 2024 年到现在的全量内容”。现在做到的是，当前已经翻到的主页列表，原文已经补齐。下一步要继续翻更深的主页分页，把 2024 年初到现在的内容尽量拉齐。老内容只保留正文和 OCR 文本，不长期存图片。

## 它能干什么

### 1. 维护组合快照

它会把不同组合分开算，不再把国内版、国际版、纯 A 版混成一坨。

目前的规则是：

- `叫兽指数国际版/全球配置版` 自己加总 100%
- `叫兽指数内地版/公募基金版` 自己加总 100%
- `纯A版` 自己加总 100%
- 回答里出现的“当前持仓”如果给了完整比例，也单独作为一个组合
- 只有“减仓、止盈、加到、平出”但没给新比例的内容，只记成调仓事件，不强行改权重

这个点很重要。之前我犯过一次错，把国内和国际拼成 100%。后来发现 Deepvan 的表经常是两个版本，各自都是完整组合。现在 schema 已经按 `portfolio_id` 拆开。

### 2. 抽调仓事件

能识别这些动作：

- 加仓、减仓
- 止盈、止损
- 清仓、平出
- 换仓、换入、转入
- 加到某个标的
- 完整组合表持仓

每条事件会尽量保留：

- 日期
- 组合版本
- 标的
- 旧权重和新权重，如果原文有
- 简要理由
- 来源链接
- 证据等级

### 3. 抽象投研 Skill

这里的 skill 不是一句“他看好 AI”这么粗糙。好的 skill 应该能指导下一次分析。

目前抽出来的骨架包括：

- 组合优先：先确定组合版本和权重，再讨论单个标的
- 主导变量：把叙事变成可以验证的变量
- 海外到国内映射：从海外产业链信号映射到 A 股、港股、QDII 或 ETF
- 可执行替代：同一个观点要有美股账户、国内基金账户、纯 A 账户的表达方式
- 风控和对冲：变量变坏先降风险，变量没坏但波动大可以用仓位或期权处理
- 复盘意识：每个观点要能回到日期、标的、价格和基准上验证

### 4. 学思想结构和回答方式

这部分我单独放进了 skill 的 `thinking-and-style.md`。

调用 skill 后，AI 不应该说“我是 Deepvan”，也不应该复制他的口头禅。正确做法是学他的思考顺序：

1. 先把问题改写成一个交易问题  
   是买、卖、减仓、持有，还是先观察？

2. 找一两个主导变量  
   比如美债利率、云厂商 CapEx、HBM 供需、长鑫 IPO、ETF 溢价、真实利率。

3. 写清传导链  
   变量怎么影响行业，行业怎么影响盈利或估值，最后怎么影响价格。

4. 映射到可买资产  
   美股账户怎么买，国内账户怎么买，纯 A 账户能不能表达。

5. 给组合动作  
   加、减、换、对冲、拿现金，不能只说“看好”。

6. 写出怎么错  
   哪个变量变了，说明这套判断该撤。

这个比“模仿口吻”有用。口吻学多了容易变油，结构学到了才真的能用。

## 胜率、夏普、年化能不能做

能做，但要分清楚两类东西。

### 单条观点复盘

适合算：

- 方向胜率
- 相对基准超额收益
- 最大回撤
- 持有期收益
- 5D、20D、60D、120D 分窗口结果
- 变量是否兑现

例子：

- 他说减仓半导体，之后半导体相对基准是否跑输？
- 他说加到 XBI 或标普生物，之后 XBI 相对 SPY 是否有超额？
- 他说黄金逻辑取决于真实利率，之后 TIPS 或实际利率有没有配合？

### 组合级复盘

适合算：

- 净值曲线
- 年化收益
- 年化波动
- 夏普
- 最大回撤
- Calmar
- 相对基准收益
- 调仓前后贡献

这个尤其适合 `叫兽指数国际版/全球配置版` 和 `内地版/公募基金版`。因为它们有完整权重表，只要接上稳定行情源，就可以做得比较扎实。

### 最值得看的榜单

后面报告里应该固定输出几张榜：

- Top 5 最成功决策  
  按超额收益、回撤控制、变量验证综合排序。

- Top 5 最失败决策  
  不是为了挑刺，而是看错在哪里：变量错、时间错、资产映射错，还是执行品种有问题。

- Top 5 最有价值调仓  
  比如一次减仓有没有明显降低回撤。

- Top 5 争议判断  
  方向对了但过程错，或者变量对了但资产没涨，这类最有研究价值。

现在项目里已经有可信度评分框架，但正式跑出稳定的夏普、年化和榜单，还需要补行情源。A 股、港股、美股 ETF、QDII、公募基金净值都要有日线数据，否则会把缺数据误当成判断错误。

## 数据路线

下一步数据要这样做：

### 第一阶段：把 2024 至今原文补全

目标：

- 从主页继续分页
- 覆盖 2024-01-01 到当前日期
- 每条内容存正文
- 图片只做 OCR，保留 OCR 文本
- 不长期保存图片

这一步是 skill 变扎实的基础。否则只靠高热或高关键词内容，容易把他的思想结构抽偏。

### 第二阶段：按用途分语料

不是所有内容都进入投研评分。

- 投研内容：进入组合、调仓、可信度评分
- 非投研内容：进入思想结构和回答方式分析
- 第三方总结：只做发现线索，不做组合事实
- 评论区：只作为辅助上下文，不能当持仓证据

### 第三阶段：行情和净值

需要接：

- A 股日线
- 港股日线
- 美股 ETF 日线
- QDII / LOF / ETF 净值
- 黄金、TIPS、BEI、美元、美债等宏观变量

接上以后，才能稳定输出：

- 分主题胜率
- 超额收益
- 最大回撤
- 夏普
- 年化收益
- 最成功和最失败决策

## 目录结构

```text
skill/deepvan-investment-research/
  SKILL.md
  references/
    portfolio-schema.md
    research-skill-taxonomy.md
    thinking-and-style.md
    credibility-rubric.md
    data-strategy.md

tools/
  deepvan_candidate_filter.py
  deepvan_corpus_inventory.py
  deepvan_monitor.py
  deepvan_image_ocr.py
  deepvan_pipeline.py
  deepvan_profile_report.py
  deepvan_evaluator.py
  deepvan_period_report.py
  scripts/vision_ocr.swift

examples/
config.example.json
credibility_config.example.json
```

## 怎么安装这个 skill

把 skill 目录复制到 Codex 的 skills 目录：

```bash
mkdir -p ~/.codex/skills
cp -R skill/deepvan-investment-research ~/.codex/skills/
```

然后在 Codex 里这样叫它：

```text
Use $deepvan-investment-research to analyze this post in a Deepvan-style research structure.
```

它会按“问题、结论、主导变量、推理链、可执行表达、组合动作、怎么错、接下来盯什么”的结构来回答。

## 依赖

核心脚本尽量只用 Python 标准库。

必需：

- Python 3.11+

可选：

- macOS Command Line Tools，用于 `swiftc`
- `curl` 和 `sips`，用于本地图片 OCR
- 飞书 webhook，通过 `DEEPVAN_NOTIFY_WEBHOOK` 传入
- 知乎搜索 token，通过环境变量传入

不要把 API key、cookie、登录态、webhook 写进仓库。

## 常用命令

```bash
cd tools
python3 -m py_compile *.py
python3 deepvan_corpus_inventory.py --root .. --out data/corpus_inventory.json --missing-out data/backfill_missing_urls.json
python3 deepvan_image_ocr.py --dirs ../data/original_pages_recent --max-images-per-article 4 --limit 120
python3 deepvan_pipeline.py --config ../config.example.json --candidate-limit 80 --fetch-budget 0
```

飞书测试：

```bash
DEEPVAN_NOTIFY_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/...' \
python3 tools/deepvan_pipeline.py --config config.example.json --candidate-limit 80 --fetch-budget 0 --send detailed
```

## 我希望它最后变成什么

我希望这个项目最后不是一个“爬虫加摘要器”，而是一个小型投研档案系统。

它应该能回答：

- 他现在每个组合版本到底持有什么？
- 哪几次调仓真的有效？
- 哪些判断只是方向对，执行并不好？
- 哪个主题他最稳定，哪个主题他容易错？
- 他的分析套路到底是什么？
- 如果今天出现一个新问题，按这套思路应该先看什么变量？

做到这里，这个 skill 才算有点意思。
