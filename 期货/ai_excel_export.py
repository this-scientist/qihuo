# -*- coding: utf-8 -*-
"""Excel export shaped for LLM-assisted futures research."""
from __future__ import annotations

import io
import math
import re
import zipfile
from datetime import datetime
from html import escape
from urllib.parse import quote


CONTENT_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def export_filename(asof: str) -> str:
    return f'futures-ai-export-{asof}.xlsx'


def workbook_response_headers(asof: str) -> dict[str, str]:
    filename = export_filename(asof)
    return {
        'Content-Type': CONTENT_TYPE,
        'Content-Disposition': f"attachment; filename*=UTF-8''{quote(filename)}",
        'Cache-Control': 'no-store',
    }


def build_ai_excel(payload: dict, option_payload: dict | None = None,
                   scanner_payload: dict | None = None,
                   real_daily: dict | None = None) -> bytes:
    option_payload = option_payload or {}
    scanner_payload = scanner_payload or {}
    real_daily = real_daily or {}
    sheets = [
        ('说明', _overview_rows(payload)),
        ('品种总览', _commodity_rows(payload)),
        ('决策信号', _decision_rows(payload)),
        ('技术因子', _factor_rows(payload)),
        ('期限结构', _curve_rows(payload)),
        ('席位持仓', _holding_rows(payload)),
        ('期权链', _option_rows(option_payload)),
        ('期权机会', _opportunity_rows(scanner_payload)),
        ('复权主连日线', _daily_rows(payload)),
        ('真实主次合约日线', _real_daily_rows(real_daily)),
        ('技术信号日线', _technical_signal_rows(payload)),
        ('量度走势', _measured_move_rows(payload)),
        ('ML价格行为', _ml_price_action_rows(payload)),
        ('大类指数日线', _sector_index_rows(payload)),
        ('数据质量', _quality_rows(payload)),
    ]
    return _xlsx(sheets)


def _overview_rows(payload: dict) -> list[list[object]]:
    return [
        ['项目', '内容'],
        ['数据日期', payload.get('asof')],
        ['生成时间', datetime.now().isoformat(timespec='seconds')],
        ['数据指纹', payload.get('data_hash')],
        ['用途', '给大模型分析的分门别类期货日度数据包；空白表示缺失，不代表 0。'],
        ['价格口径', payload.get('scope')],
        ['曲线口径', payload.get('curve_scope')],
        ['限制', '期权盘口、实时滑点、完整产业数据不在本导出内；请结合数据质量页判断覆盖。'],
    ]


def _commodity_rows(payload: dict) -> list[list[object]]:
    columns = [
        ('ts_code', '品种代码'), ('name', '名称'), ('sector', '大类'),
        ('main_code', '主力合约'), ('secondary_code', '次主力合约'),
        ('direction', '筛选方向'), ('trend_direction', '技术方向'),
        ('phase', '趋势阶段'), ('phase_age', '阶段持续日'),
        ('close', '复权收盘'), ('raw_close', '真实主力收盘'),
        ('return1', '1日涨跌幅'), ('return5', '5日涨跌幅'), ('return20', '20日涨跌幅'),
        ('rps20', 'RPS20'), ('directional_rps20', '方向RPS20'),
        ('adx', 'ADX14'), ('adx_slope', 'ADX五日变化'), ('atr14', 'ATR14'),
        ('atr_percentile', 'ATR分位'), ('oi_change5', 'OI五日变化'),
        ('volume_ratio', '量比'), ('carry_annualized', '年化Carry'),
        ('carry_change5', 'Carry五日变化'), ('structure', '期限结构'),
        ('sector_direction', '大类方向'), ('sector_strength', '大类内相对强度'),
        ('sector_rank', '大类内排名'),
    ]
    return _table(columns, payload.get('records') or [])


def _decision_rows(payload: dict) -> list[list[object]]:
    columns = [
        ('ts_code', '品种代码'), ('name', '名称'), ('sector', '大类'),
        ('main_code', '主力合约'), ('decision_direction', '决策方向'),
        ('decision_side', '交易侧'), ('state_v2', 'V2状态'),
        ('trend_state_label', '趋势状态'), ('trend_state_score', '趋势状态分'),
        ('trend_transition', '趋势切换'), ('trend_option_gate', '期权门控'),
        ('dir_score', '方向分'), ('start_score', '启动分'),
        ('price_rps', '价格RPS分'), ('vol_rps', '成交量RPS分'),
        ('oi_change_rps', 'OI变化RPS分'), ('oi_behavior', 'OI行为'),
        ('structure_confirm', '结构确认'), ('option_action', '期权动作'),
        ('v2_rank', 'V2排名'),
    ]
    return _table(columns, payload.get('decisions') or payload.get('records') or [])


def _factor_rows(payload: dict) -> list[list[object]]:
    records = payload.get('records') or []
    factors = payload.get('factors') or []
    header = ['品种代码', '名称', '大类', '字段', '中文名', '分组', '单位', '值']
    rows = [header]
    for record in records:
        for factor in factors:
            key = factor.get('key')
            rows.append([
                record.get('ts_code'), record.get('name'), record.get('sector'), key,
                factor.get('label'), factor.get('group'), factor.get('unit'), record.get(key),
            ])
    return rows


def _curve_rows(payload: dict) -> list[list[object]]:
    rows = [['品种代码', '名称', '大类', '合约代码', '交割月', '结算价', '持仓量', '成交量',
             '流动性排序', '曲率']]
    for record in payload.get('records') or []:
        for index, item in enumerate(record.get('curve') or [], 1):
            rows.append([
                record.get('ts_code'), record.get('name'), record.get('sector'),
                item.get('ts_code') or item.get('contract_code'),
                item.get('delivery_month'), item.get('settle'), item.get('oi'),
                item.get('vol'), item.get('liquidity_rank', index), record.get('curvature'),
            ])
    return rows


def _holding_rows(payload: dict) -> list[list[object]]:
    rows = [['品种代码', '名称', '大类', '席位状态', '席位合约', '原因', '前20多仓', '前20空仓',
             '前20净仓', '多仓变化', '空仓变化', '净仓变化', '多仓集中度', '空仓集中度',
             '多头前五', '空头前五']]
    for record in payload.get('records') or []:
        holding = record.get('trader_positions') or {}
        rows.append([
            record.get('ts_code'), record.get('name'), record.get('sector'),
            holding.get('holding_status'), holding.get('holding_contract'),
            holding.get('holding_reason'), holding.get('top20_long'), holding.get('top20_short'),
            holding.get('top20_net'), holding.get('top20_long_change'),
            holding.get('top20_short_change'), holding.get('top20_net_change'),
            holding.get('top20_long_concentration'), holding.get('top20_short_concentration'),
            _broker_text(holding.get('top_long_brokers')), _broker_text(holding.get('top_short_brokers')),
        ])
    return rows


def _option_rows(option_payload: dict) -> list[list[object]]:
    columns = [
        ('ts_code', '期权代码'), ('main_code', '品种代码'), ('underlying_code', '标的合约'),
        ('call_put', 'C/P'), ('exercise_price', '行权价'), ('premium', '权利金'),
        ('close', '收盘价'), ('vol', '成交量'), ('oi', '持仓量'),
        ('delta', 'Delta'), ('gamma', 'Gamma'), ('theta', 'Theta'), ('vega', 'Vega'),
        ('iv_reference', '参考IV'), ('hv20', 'HV20'), ('days_to_expiry', '剩余天数'),
        ('moneyness_pct', '虚实值%'), ('break_even', '盈亏平衡'),
        ('tradability.score', '可做性分'), ('tradability.grade', '可做性等级'),
    ]
    return _table(columns, option_payload.get('records') or [])


def _opportunity_rows(scanner_payload: dict) -> list[list[object]]:
    rows = [['方向', '品种代码', '名称', '爆发分', '命中信号', '适用信号', '四重共振',
             '十倍分', '十倍标签', '最佳合约']]
    for side in ['long', 'short']:
        for item in scanner_payload.get(side) or []:
            rows.append([
                side, item.get('ts_code'), item.get('name'), item.get('explosion_score'),
                item.get('signals_met'), item.get('signals_applicable'), item.get('resonance'),
                item.get('tenbagger_score'), item.get('tenbagger_label'),
                item.get('best_option_code') or _best_option(item),
            ])
    return rows


def _daily_rows(payload: dict) -> list[list[object]]:
    rows = [['品种代码', '日期', '开盘', '最高', '最低', '收盘', '成交量', '持仓量', 'EMA20']]
    moving = payload.get('moving') or {}
    for code, candles in (payload.get('candles') or {}).items():
        ema = ((moving.get(code) or {}).get('ema20') or [])
        for index, candle in enumerate(candles):
            values = list(candle) + [None] * (7 - len(candle))
            rows.append([code] + values[:7] + [ema[index] if index < len(ema) else None])
    return rows


def _real_daily_rows(real_daily: dict) -> list[list[object]]:
    rows = [['品种代码', '合约代码', '角色', '日期', '开盘', '最高', '最低', '收盘',
             '结算价', '成交量', '持仓量', '昨收', '昨结', '持仓变化']]
    for code, records in real_daily.items():
        for item in records or []:
            rows.append([
                code, item.get('ts_code'), item.get('role'), item.get('trade_date'),
                item.get('open'), item.get('high'), item.get('low'), item.get('close'),
                item.get('settle'), item.get('vol'), item.get('oi'),
                item.get('pre_close'), item.get('pre_settle'), item.get('oi_chg'),
            ])
    return rows


def _technical_signal_rows(payload: dict) -> list[list[object]]:
    rows = [['品种代码', '日期', '信号', '方向', '价格', '标签', '说明']]
    for code, signals in (payload.get('technical_signals') or {}).items():
        for item in signals or []:
            rows.append([
                code, item.get('trade_date') or item.get('date'), item.get('signal') or item.get('type'),
                item.get('side') or item.get('direction'), item.get('price'),
                item.get('label'), item.get('note') or item.get('reason'),
            ])
    return rows


def _measured_move_rows(payload: dict) -> list[list[object]]:
    rows = [['品种代码', '字段', '值']]
    for code, value in (payload.get('measured_moves') or {}).items():
        if isinstance(value, dict):
            for key, item in value.items():
                rows.append([code, key, item])
        elif isinstance(value, list):
            for index, item in enumerate(value, 1):
                if isinstance(item, dict):
                    for key, entry in item.items():
                        rows.append([code, f'{index}.{key}', entry])
                else:
                    rows.append([code, index, item])
        else:
            rows.append([code, 'value', value])
    return rows


def _ml_price_action_rows(payload: dict) -> list[list[object]]:
    columns = [
        ('trade_date', '日期'), ('close', '收盘'), ('side', '方向'),
        ('label', '短标签'), ('market_cycle_phase', '市场周期阶段'),
        ('market_cycle_label', '周期标签'), ('signal_bar', '信号K'),
        ('signal_bar_label', '信号K中文'), ('strategy', '策略'),
        ('samples', '样本数'), ('win_rate', '胜率'), ('avg_r', '平均R'),
        ('median_r', '中位R'),
    ]
    rows = [['品种代码'] + [label for _, label in columns]]
    for code, annotations in (payload.get('ml_price_action') or {}).items():
        for item in annotations or []:
            rows.append([code] + [_dig(item, key) for key, _ in columns])
    return rows


def _sector_index_rows(payload: dict) -> list[list[object]]:
    rows = [['大类', '日期', '等权指数', '成员数', '成员']]
    for name, group in (payload.get('sectors') or {}).items():
        members = group.get('members') or []
        member_text = ','.join(members)
        for day, value in group.get('values') or []:
            rows.append([name, day, value, group.get('count'), member_text])
    return rows


def _quality_rows(payload: dict) -> list[list[object]]:
    rows = [['类别', '品种代码', '字段', '值']]
    for key, value in (payload.get('quality') or {}).items():
        rows.append(['采集质量', '', key, value])
    for item in payload.get('exclusions') or []:
        rows.append(['排除品种', item.get('ts_code'), 'reason', item.get('reason')])
    for item in payload.get('supplemental_status') or []:
        code = item.get('ts_code')
        for key, value in item.items():
            if key != 'ts_code':
                rows.append(['补充数据覆盖', code, key, value])
    return rows


def _table(columns: list[tuple[str, str]], records: list[dict]) -> list[list[object]]:
    rows = [[label for _, label in columns]]
    for record in records:
        rows.append([_dig(record, key) for key, _ in columns])
    return rows


def _dig(record: dict, dotted: str):
    value = record
    for part in dotted.split('.'):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _broker_text(rows):
    if not rows:
        return None
    return '；'.join(f"{item.get('name') or item.get('broker')}:{item.get('value') or item.get('position')}"
                    for item in rows[:5])


def _best_option(item: dict):
    contracts = item.get('contracts') or []
    return contracts[0].get('ts_code') if contracts else None


def _xlsx(sheets: list[tuple[str, list[list[object]]]]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', _content_types(len(sheets)))
        archive.writestr('_rels/.rels', _root_rels())
        archive.writestr('xl/workbook.xml', _workbook_xml(sheets))
        archive.writestr('xl/_rels/workbook.xml.rels', _workbook_rels(len(sheets)))
        archive.writestr('xl/styles.xml', _styles_xml())
        for index, (_, rows) in enumerate(sheets, 1):
            archive.writestr(f'xl/worksheets/sheet{index}.xml', _sheet_xml(rows))
    return output.getvalue()


def _sheet_xml(rows: list[list[object]]) -> str:
    body = []
    for row_index, row in enumerate(rows, 1):
        cells = ''.join(_cell_xml(row_index, column_index, value)
                        for column_index, value in enumerate(row, 1))
        body.append(f'<row r="{row_index}">{cells}</row>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData>' + ''.join(body) + '</sheetData></worksheet>')


def _cell_xml(row: int, column: int, value) -> str:
    if value is None or value == '':
        return ''
    ref = f'{_column_name(column)}{row}'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return f'<c r="{ref}"><v>{value}</v></c>'
    text = _clean_text(str(value))
    return f'<c r="{ref}" t="inlineStr"><is><t>{escape(text)}</t></is></c>'


def _column_name(index: int) -> str:
    name = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _clean_text(value: str) -> str:
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', value)


def _workbook_xml(sheets: list[tuple[str, list[list[object]]]]) -> str:
    entries = ''.join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, (name, _) in enumerate(sheets, 1)
    )
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{entries}</sheets></workbook>')


def _workbook_rels(count: int) -> str:
    sheet_rels = ''.join(
        f'<Relationship Id="rId{index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, count + 1)
    )
    style_id = count + 1
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{sheet_rels}<Relationship Id="rId{style_id}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
            'Target="styles.xml"/></Relationships>')


def _content_types(count: int) -> str:
    sheets = ''.join(
        '<Override PartName="/xl/worksheets/sheet{0}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'.format(index)
        for index in range(1, count + 1)
    )
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            f'{sheets}</Types>')


def _root_rels() -> str:
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>')


def _styles_xml() -> str:
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="1"><font><sz val="11"/><name val="Arial"/></font></fonts>'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
            '<borders count="1"><border/></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
            '</styleSheet>')
