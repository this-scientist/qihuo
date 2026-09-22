# -*- coding: utf-8 -*-
"""DeepSeek 一键分析：把盘面/结构/期权/本地价位作为"事实"喂给模型，输出结构化头寸意见。

三条硬约束（同时写进提示词与返回体，前端必须原样展示）：
1. DeepSeek 官方 API 不提供联网检索，产业逻辑只能来自模型固有知识，非实时、可能过时或错误；
2. 模型给出的支撑/压力位不可复现，只与本地计算并列对照，不做"谁对"的结论；
3. 输出是研究参考，不是可执行交易指令。

API Key 只从环境变量或项目 .env 读取，不写入代码、不落日志、不回传前端。
"""
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import dotenv_values

DEFAULT_BASE_URL = 'https://api.deepseek.com'
DEFAULT_MODEL = 'deepseek-v4-flash'
DEFAULT_TIMEOUT = 60.0
PROJECT_ROOT = Path(__file__).resolve().parent.parent

LIMITATIONS = [
    'DeepSeek 官方 API 不提供联网检索：产业逻辑来自模型固有知识，非实时，可能过时或错误。',
    '模型给出的支撑/压力位不可复现（同一输入两次结果可能不同），仅与本地计算结果并列对照。',
    '本分析是研究参考，不构成可执行交易指令；系统没有买卖盘口数据。',
]

SCHEMA_HINT = """{
  "position": {"stance": "long|short|wait", "instrument": "Call|Put|观望", "delta_range": "如 0.20-0.35",
    "dte_range": "如 20-45天", "stop": "止损参考（价格或权利金亏损比例）", "reasoning": ["依据1", "依据2"]},
  "levels": {"support": [{"price": 数值, "why": "理由"}], "resistance": [{"price": 数值, "why": "理由"}]},
  "industry": {"summary": "产业逻辑与当前状况", "drivers": ["驱动1"], "uncertainty": "不确定性与过时风险"},
  "risks": ["风险1"], "invalidations": ["什么情况下本判断失效"], "data_gaps": ["缺失的数据"],
  "disclaimer": "一句话免责声明"
}"""

SYSTEM_PROMPT = """你是商品期货买方期权的研究助手。用户会提供某品种的当日盘面数据、商品结构数据、期权数据与本地算出的支撑压力位。

必须遵守：
1. 只依据用户提供的数据做判断；缺少的数据写进 data_gaps，绝不编造数值或事件。
2. 你无法联网检索，也没有实时数据源。产业逻辑（供需、库存、政策、产能等）只能来自你的固有知识，你必须明确说明这是模型知识、非实时、可能过时；禁止声称"最新""今日""目前市场"等时效性表述。
3. levels 里的支撑/压力位是你自己的判断，必须给出理由；它只用于与"本地计算"对照，不要在结论中否定本地数据。
4. 头寸意见必须给出：方向、工具（Call/Put/观望）、|Delta| 区间、DTE 区间、止损参考、依据列表；并给出失效条件。
5. 期权买方默认风险有限（最多损失权利金），但仍需提示时间价值衰减与 IV 回落风险。
6. 输出必须是一个 JSON 对象，不要输出任何解释性文字、不要用 Markdown 代码块，字段结构如下：
""" + SCHEMA_HINT


def load_config(env_path=None):
    """读取 DeepSeek 配置：环境变量优先，其次项目 .env。key 缺失返回 None。"""
    path = Path(env_path) if env_path else PROJECT_ROOT / '.env'
    file_values = dotenv_values(path) if path.exists() else {}

    def pick(name, default=None):
        return os.environ.get(name) or file_values.get(name) or default

    timeout_raw = pick('DEEPSEEK_TIMEOUT', DEFAULT_TIMEOUT)
    try:
        timeout = max(5.0, float(timeout_raw))
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT
    return dict(api_key=pick('DEEPSEEK_API_KEY'),
                base_url=str(pick('DEEPSEEK_BASE_URL', DEFAULT_BASE_URL)).rstrip('/'),
                model=pick('DEEPSEEK_MODEL', DEFAULT_MODEL), timeout=timeout)


def configured(env_path=None):
    return bool(load_config(env_path).get('api_key'))


def build_prompt(context):
    """把上下文拼成单条 user 消息；JSON 保证模型只看到结构化事实。"""
    return json.dumps(context, ensure_ascii=False, indent=1, default=str)


def build_messages(context):
    return [dict(role='system', content=SYSTEM_PROMPT),
            dict(role='user', content=build_prompt(context))]


def _strip_fence(text):
    cleaned = text.strip()
    if cleaned.startswith('```'):
        cleaned = re.sub(r'^```[a-zA-Z]*\s*', '', cleaned)
        cleaned = re.sub(r'```\s*$', '', cleaned).strip()
    return cleaned


def parse_analysis(text):
    """容错解析：优先整体 JSON，其次剥离代码围栏，最后截取最外层花括号。"""
    if not isinstance(text, str) or not text.strip():
        return dict(data=None, parse_error='模型返回内容为空', raw=text)
    cleaned = _strip_fence(text)
    for candidate in (cleaned,):
        try:
            return dict(data=json.loads(candidate), parse_error=None, raw=text)
        except json.JSONDecodeError:
            pass
    start, end = cleaned.find('{'), cleaned.rfind('}')
    if 0 <= start < end:
        try:
            return dict(data=json.loads(cleaned[start:end + 1]), parse_error=None, raw=text)
        except json.JSONDecodeError as exc:
            return dict(data=None, parse_error='模型输出不是合法 JSON（%s）' % exc.msg, raw=text)
    return dict(data=None, parse_error='模型输出中没有找到 JSON 对象', raw=text)


def _price(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_levels(data):
    """把模型返回的 levels 归一成 [{price, why}]；结构异常时返回空列表。"""
    levels = (data or {}).get('levels') or {}
    out = {}
    for side in ('support', 'resistance'):
        items = []
        for entry in levels.get(side) or []:
            if isinstance(entry, dict):
                price = _price(entry.get('price'))
                if price is not None:
                    items.append(dict(price=price, why=str(entry.get('why') or entry.get('reason') or '')))
            else:
                price = _price(entry)
                if price is not None:
                    items.append(dict(price=price, why=''))
        out[side] = items
    return out


def analyze(context, config=None, opener=None):
    """调用 DeepSeek chat/completions 并解析。失败抛 ValueError（走服务端 400 通道）。"""
    cfg = config or load_config()
    if not cfg.get('api_key'):
        raise ValueError('未配置 DEEPSEEK_API_KEY，请在项目 .env 中填写后重试')
    payload = dict(model=cfg['model'], messages=build_messages(context),
                   temperature=0.2, stream=False)
    request = urllib.request.Request(cfg['base_url'] + '/chat/completions',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                 'Authorization': 'Bearer ' + cfg['api_key']}, method='POST')
    open_fn = opener or urllib.request.urlopen
    try:
        with open_fn(request, timeout=cfg['timeout']) as response:
            body = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        detail = ''
        try:
            detail = exc.read().decode('utf-8')[:300]
        except Exception:
            detail = ''
        raise ValueError('DeepSeek 返回 %s：%s' % (exc.code, detail or exc.reason))
    except urllib.error.URLError as exc:
        raise ValueError('无法连接 DeepSeek（%s），请检查网络或 DEEPSEEK_BASE_URL' % exc.reason)
    except (TimeoutError, OSError) as exc:
        raise ValueError('DeepSeek 请求失败（%s）' % type(exc).__name__)
    if not isinstance(body, dict):
        raise ValueError('DeepSeek 返回格式异常')
    if body.get('error'):
        raise ValueError('DeepSeek 报错：%s' % str(body['error'])[:300])
    choices = body.get('choices') or []
    message = (choices[0].get('message') or {}) if choices else {}
    parsed = parse_analysis(message.get('content'))
    usage = body.get('usage') or {}
    return dict(analysis=parsed['data'], parse_error=parsed['parse_error'], raw=parsed['raw'],
        model=body.get('model') or cfg['model'], usage=usage,
        ai_levels=extract_levels(parsed['data']), limitations=LIMITATIONS)
