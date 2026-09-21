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
