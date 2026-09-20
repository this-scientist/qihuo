"""Populate the conversation's curve comparison with validated radar histories."""
import argparse
import json
import re
from pathlib import Path

from strategy import Settings
from screen_futures import load_inputs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--asof', default='20260911')
    parser.add_argument('--template', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).parent / 'data'
    _, histories, _, _ = load_inputs(root, args.asof, Settings())
    common = sorted(set.intersection(*(set(h.trade_date) for h in histories.values())))[-251:]
    if len(common) < 251:
        raise ValueError('Need 251 shared trading dates for comparison')
    names = dict(SC='原油', EG='乙二醇', MA='甲醇', BU='沥青', LU='低硫燃料油',
        TA='PTA', PX='对二甲苯', PR='瓶片', PF='短纤', EB='苯乙烯',
        L='塑料', PP='聚丙烯', V='PVC', BR='丁二烯橡胶', RU='天然橡胶',
        NR='20号胶', FU='燃料油', LC='碳酸锂', CU='铜', AL='铝', AU='黄金',
        AG='白银', NI='镍', ZN='锌', PB='铅', SN='锡', AO='氧化铝',
        AD='铸造铝合金', SS='不锈钢', RB='螺纹钢', HC='热卷', I='铁矿石',
        J='焦炭', JM='焦煤', SF='硅铁', SM='锰硅', SI='工业硅', PS='多晶硅',
        FG='玻璃', SA='纯碱', SH='烧碱', UR='尿素', SP='纸浆', EC='集运欧线',
        A='豆一', B='豆二', M='豆粕', Y='豆油', P='棕榈油', OI='菜油',
        RM='菜粕', C='玉米', CS='玉米淀粉', RR='粳米', SR='白糖', CF='棉花',
        CY='棉纱', AP='苹果', CJ='红枣', PK='花生', JD='鸡蛋', LH='生猪',
        PG='液化石油气', FB='纤维板', LG='原木', BZ='纯苯', PL='丙烯')
    payload = {'names': {}, 'series': {}}
    for code, history in histories.items():
        values = history.set_index('trade_date').loc[common, 'close']
        payload['names'][code] = names.get(code.split('.')[0], code)
        payload['series'][code] = [[day, round(float(close), 6)] for day, close in values.items()]
    text = args.template.read_text(encoding='utf-8')
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    text, matches = re.subn(r'(<script type="application/json" id="fc-data">).*?(</script>)',
        lambda match: match[1] + encoded + match[2], text, flags=re.S)
    if matches != 1:
        raise ValueError('Expected exactly one chart data block')
    args.template.write_text(text, encoding='utf-8')
    print(f'Embedded {len(histories)} validated commodities, {len(common)} shared dates; {args.template.stat().st_size} bytes')


if __name__ == '__main__':
    main()
