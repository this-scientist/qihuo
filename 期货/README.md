# 期货

中国商品期货/商品期权数据获取项目。

## 文件

- `config.py`：Tushare 与目录配置
- `fetch_futures_data.py`：核心数据采集脚本
- `requirements.txt`：Python 依赖

## 安装

在项目根目录执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r 期货/requirements.txt
cp .env.example .env
```

然后在 `.env` 中填写 `OAR_TUSHARE_TOKEN`。`OAR_TUSHARE_HTTP_URL` 默认使用项目已配置的数据接口。

## 首次测试

```bash
cd 期货
../.venv/bin/python fetch_futures_data.py
```

脚本默认测试 2026-09-08 大连商品交易所期货日线数据。

## 正式下载

确认测试成功后，在 `fetch_futures_data.py` 底部解除：

```python
init_database()

download_history(
    start_date="20200101",
    end_date="20260908",
)
```

的注释。

## 期权候选验证页与 AI 分析

`/scanner.html` 的「自定义品种」页签可任选品种，用与「做多/做空候选」**完全相同**的列与详情面板复核它的期权综合分、结构分解、组合信号与候选合约（后端 `GET /api/candidate`）。

详情面板底部有「AI 一键分析」（`POST /api/ai/analyze`）：把技术面、商品结构、期权候选与**本地支撑压力位**一起发给 DeepSeek，返回头寸意见、依据、失效条件、风险与产业逻辑。使用前在 `.env` 填写：

```bash
DEEPSEEK_API_KEY=sk-xxxx
DEEPSEEK_MODEL=deepseek-v4-flash
```

三处必须知道的限制：① DeepSeek 官方 API **不提供联网检索**，产业逻辑是模型固有知识、非实时，可能过时或错误，且不参与任何评分；② 模型给出的支撑/压力位**不可复现**，只与本地计算结果并列对照；③ 分析是研究参考，不是可执行交易指令。本地支撑压力位由 `price_levels.py` 用**真实月合约未复权历史**计算（前高前低、整数关口、ATR 通道、成交密集区），可复现、作为事实基准。
