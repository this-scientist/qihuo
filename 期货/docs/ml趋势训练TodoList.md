# 期货趋势机器学习训练 TodoList

目标：用现有 TuShare 日线、主力映射、价格行为状态机和商品结构数据，训练一个“市场周期 + 策略打法”的胜率、盈亏比和期望值评估器。模型不直接预测涨跌，也不覆盖硬风控规则。

## 1. 数据抓取

- [x] 新增 `ml_fetch_daily.py`，专门抓取 ML 原始 `fut_daily`。
- [x] 保存路径：`data/ml/raw/fut_daily/<exchange>/<trade_date>.csv`。
- [x] 对 ML 原始层放宽校验：`amount`、`oi` 可缺失并标记；异常价格行标记 `price_valid=false`，不阻断整天数据。
- [x] 首批抓取：`20260105-20260930`，五个商品交易所各 181 个交易日分区，共 905 个 CSV。
- [ ] 按季度继续向前抓取更多历史，建议顺序：
  - `20250101-20251231`
  - `20240101-20241231`
  - `20230101-20231231`
  - 再根据 TuShare 覆盖质量决定是否继续向前。
- [ ] 新增抓取进度输出：每个交易所/日期完成后打印一行，方便长任务监控。
- [ ] 新增断点报告汇总：统计每个交易所覆盖交易日数、缺失日、异常行数量。

## 2. 主力序列构建

- [ ] 拉取 `fut_mapping`，保存到 `data/ml/raw/fut_mapping/<exchange>/<trade_date>.csv`。
- [ ] 用 `fut_mapping` 把真实合约日线拼成商品主力序列。
- [ ] 换月不使用 `fut_daily_adj` 作为训练主源；优先用真实合约和映射重建。
- [ ] 每条主力序列保留：
  - 当前真实合约 `mapping_ts_code`
  - 商品主代码 `main_code`
  - 是否换月 `roll_changed`
  - 换月前后价格差
  - 是否存在同日重叠价
- [ ] 对训练标签使用“下一交易日开盘”作为可交易入场价，避免把隔夜跳空收益当成可获得收益。

## 3. 特征工程

- [ ] 趋势背景特征：
  - `market_cycle_phase`
  - `ema20_slope5_atr`
  - `directional_ema20_distance_atr`
  - `adx`
  - `plus_di`
  - `minus_di`
  - `rps20`
  - `rps_accel`
  - `atr_change5`
- [ ] 资金与量仓特征：
  - `vol`
  - `volume_ratio`
  - `oi`
  - `oi_change1`
  - `oi_change5`
  - `price_oi_state`
- [ ] 商品结构特征：
  - 近月/远月价差
  - 价差 5 日变化
  - 期限结构方向
  - `structure_confirm`
  - `structure_score`
- [ ] 跳空特征，必须单独做：
  - `gap_pct = next_open / signal_close - 1`
  - `gap_atr = (next_open - signal_close) / atr14`
  - `gap_with_trend`
  - `gap_open_location`
  - `gap_fill_ratio`
  - `gap_follow_through`
  - `gap_close_position`
  - `price_anomaly`
- [ ] 价格位置特征：
  - 距 EMA20
  - 距前高/前低
  - 距支撑/阻力
  - 距通道边界
  - 是否在区间上沿/下沿/中部

## 4. 策略标签

- [ ] 每个交易日、每个商品、每个方向生成策略候选样本。
- [ ] 第一批策略只做四类：
  - 突破尖峰/紧密通道：顺势追随
  - 紧密通道：浅回踩继续
  - 宽通道：顺大方向回踩入场
  - 交易区间：边界反转或不做方向期权
- [ ] 观察窗口：
  - 5 日
  - 10 日
  - 20 日
- [ ] 标签使用下一交易日开盘后路径：
  - `hit_target_first`
  - `hit_stop_first`
  - `mfe_atr`
  - `mae_atr`
  - `return_n`
  - `realized_rr`
  - `expectancy_r`
- [ ] 目标/止损第一版：
  - 顺势目标：`+2 ATR`
  - 顺势止损：`-1 ATR`
  - 之后再加入本地支撑/阻力位目标。

## 5. 先统计，后训练

- [ ] 先生成统计表，不急着 ML：
  - 市场周期
  - 策略打法
  - 样本数
  - 胜率
  - 平均 RR
  - 中位 RR
  - 平均 MFE
  - 平均 MAE
  - 期望值
- [ ] 重点验证：
  - 突破尖峰/紧密通道顺势是否优于其它状态
  - 宽通道中间追单是否显著变差
  - 交易区间追突破是否容易失败
  - 顺势跳空后未回补是否强化趋势
  - 趋势末端顺势跳空是否更像高潮

## 6. 机器学习训练

- [ ] Baseline：逻辑回归。
  - 目标：`hit_target_first`
  - 输出：校准后的胜率概率。
- [ ] 主模型：LightGBM / XGBoost。
  - 目标：胜率、是否先到目标、是否先到止损。
  - 评估：AUC、Brier Score、分桶胜率、收益分组单调性。
- [ ] 盈亏比分布模型：
  - 预测 `mfe_atr`
  - 预测 `mae_atr`
  - 预测 `realized_rr`
  - 用分位数回归输出 25/50/75 分位。
- [ ] 时间切分：
  - 不随机切分。
  - 使用 walk-forward：
    - 训练早期窗口
    - 验证后续窗口
    - 滚动前移。
- [ ] 每个结论必须输出：
  - 样本数
  - 覆盖年份
  - 胜率
  - 期望值
  - 置信度

## 7. 系统接入

- [ ] 新增 `ml_dataset.py`：把原始日线、主力映射和现有状态机结果合成训练表。
- [ ] 新增 `ml_backtest.py`：输出市场周期/策略统计表。
- [ ] 新增 `ml_train.py`：训练逻辑回归和 LightGBM/XGBoost。
- [ ] 新增 `data/ml/model_outputs/strategy_scores.json`。
- [ ] 前端第一版只展示，不参与筛选。
- [ ] 稳定后再让 ML 影响候选排序。
- [ ] 硬规则不允许被模型覆盖：
  - 趋势末端不开新仓
  - 过度延伸不追
  - 结构冲突降级
  - 交易区间默认不做方向期权
