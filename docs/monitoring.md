# Deepvan 调仓监控配置

这个监控做的是“发现新公开原文 -> 抽取组合/调仓信号 -> 去重 -> 推送 webhook”。默认只把 Deep Van 本人公开内容当作组合事实；第三方总结只能做线索。

## 快速启动

```bash
export ZH_TOKEN="你的知乎开发者 API Key"
export DEEPVAN_NOTIFY_WEBHOOK="你的机器人 webhook"

python3 tools/deepvan_monitor.py monitor --config config.example.json
```

第一次运行主要是建立基线。后续定时运行时，如果发现新的持仓表、调仓动作或组合权重变化，会发送提醒。

## 飞书

配置：

```json
{
  "alert": {
    "provider": "feishu",
    "webhook_url_env": "DEEPVAN_NOTIFY_WEBHOOK"
  }
}
```

环境变量：

```bash
export DEEPVAN_NOTIFY_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/..."
python3 tools/deepvan_monitor.py webhook-test --config config.example.json
```

## QQ / QQBot

不同 QQ 机器人网关的 webhook 格式不完全一样。当前项目内置一种常见文本格式：

```json
{
  "alert": {
    "provider": "qq",
    "webhook_url_env": "DEEPVAN_QQ_WEBHOOK"
  }
}
```

环境变量：

```bash
export DEEPVAN_QQ_WEBHOOK="https://你的 QQ bot webhook"
python3 tools/deepvan_monitor.py webhook-test --config config.example.json
```

如果你的 QQ 网关要求别的字段名，只需要改 `tools/deepvan_monitor.py` 里的 `send_webhook()`，不需要动抽取逻辑。

## 通用 JSON Webhook

```json
{
  "alert": {
    "provider": "generic_json",
    "webhook_url_env": "DEEPVAN_GENERIC_WEBHOOK"
  }
}
```

发送格式：

```json
{
  "text": "调仓提醒正文",
  "source": "deepvan_monitor"
}
```

## 怎么调监控灵敏度

关键词在 `portfolio_keywords`：

```json
[
  "叫兽指数",
  "内地版",
  "国际版",
  "全球版",
  "公募基金版",
  "调仓",
  "持仓",
  "加仓",
  "减仓",
  "清仓",
  "止盈"
]
```

想更敏感，就加主题词，例如 `XBI`、`黄金`、`半导体`、`QDII`。想减少噪音，就删掉泛词，只保留 `叫兽指数`、`调仓`、`内地版`、`全球版`。

频率和预算：

```json
{
  "monitor_query_limit": 80,
  "daily_budget": 1000
}
```

`monitor_query_limit` 控制单次监控查询数量。`daily_budget` 对应知乎搜索 API 的每日预算，不建议一次性打满，留一部分给手工补抓。

## 定时运行

macOS 可以用 cron：

```bash
crontab -e
```

每 30 分钟跑一次：

```cron
*/30 * * * * cd /path/to/deepvan-investment-skill-project && /usr/bin/env ZH_TOKEN=xxx DEEPVAN_NOTIFY_WEBHOOK=https://open.feishu.cn/... python3 tools/deepvan_monitor.py monitor --config config.example.json >> logs/monitor.log 2>&1
```

## 推送内容

调仓推送会尽量包含：

- 组合版本：国内版、国际版、纯 A、公募基金版
- 动作：加仓、减仓、清仓、止盈、换仓
- 标的和权重，如果原文给了
- 简要理由
- 来源链接
- 证据等级

图片持仓表仍要靠 OCR。监控发现新原文后，如果图片里有完整组合表，建议先跑：

```bash
python3 tools/deepvan_image_ocr.py --articles path/to/article_dir --max-images-per-article 40
python3 tools/deepvan_portfolio_timeline.py
python3 tools/deepvan_dashboard.py
```

这样 README 面板和本地指标会同步刷新。
