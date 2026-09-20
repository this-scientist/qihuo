import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from collector import atomic_csv, atomic_json, SUFFIX
from strategy import Settings
from screen_futures import screen
from test_strategy import bars


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def fixture(self, count=20):
        selected=[];prepared=[]
        exchanges=list(SUFFIX)
        for i in range(count):
            exchange=exchanges[i%len(exchanges)]
            suffix=SUFFIX[exchange]; product=chr(65+i)
            code=f'{product}.{suffix}'; main=f'{product}2701.{suffix}'; second=f'{product}2705.{suffix}'
            data=bars(100+np.arange(300)*(1+i*.1))
            asof=data.trade_date.iloc[-1]
            data['ts_code'],data['mapping_ts_code'],data['exchange']=code,main,exchange
            data['adjustment']='forward_ratio_same_day_overlap'
            data['raw_close']=data.close
            data['adj_factor']=1
            path=self.root/f'processed/history/{code.replace(".","_")}.csv'
            atomic_csv(data,path)
            pair=[]
            for role,real in [('main',main),('secondary',second)]:
                part=data.tail(65).copy()
                part['ts_code'],part['role'],part['main_code']=real,role,code
                part['oi']=10000+np.arange(len(part))*10
                part['settle']=part.close+(1 if role=='secondary' else 0)
                pair.append(part)
                selected.append(dict(ts_code=real,main_code=code,role=role,exchange=exchange,trade_date=asof,close=data.close.iloc[-1]))
            pairpath=self.root/f'processed/pair_history/{code.replace(".","_")}.csv'
            atomic_csv(pd.concat(pair,ignore_index=True),pairpath)
            prepared.append(dict(ts_code=code,exchange=exchange,history_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),pair_sha256=hashlib.sha256(pairpath.read_bytes()).hexdigest()))
        atomic_csv(pd.DataFrame(selected),self.root/f'raw/selected/{asof}.csv')
        atomic_json(dict(mode='focused',success=True,exchanges=exchanges,published_days=[asof]),self.root/'quality/latest_run.json')
        atomic_json(dict(asof=asof,prepared=prepared,exclusions=[]),self.root/'quality/history_run.json')
        return asof

    def test_pipeline_writes_scores_and_does_not_force_startups(self):
        asof=self.fixture()
        report,lists=screen(self.root,asof,Settings())
        self.assertTrue(report['success'])
        self.assertEqual(report['eligible_universe'],20)
        scores=pd.read_csv(self.root/f'processed/radar/{asof}/scores.csv')
        self.assertEqual(len(scores),40)
        self.assertTrue(scores.trend_score.between(0,100).all())
        self.assertTrue(scores.startup_score.between(0,100).all())
        self.assertTrue(lists['long_startup'].empty and lists['short_startup'].empty)
        self.assertLessEqual(len(lists['long_trend']),5)

    def test_small_universe_withholds_formal_lists(self):
        asof=self.fixture(3)
        report,lists=screen(self.root,asof,Settings())
        self.assertFalse(report['success'])
        self.assertTrue(all(frame.empty for frame in lists.values()))

    def test_corrupted_history_excluded_before_rps(self):
        asof=self.fixture(3)
        path=next((self.root/'processed/history').glob('*.csv'))
        path.write_text('broken',encoding='utf-8')
        report,_=screen(self.root,asof,Settings(min_universe=2))
        self.assertEqual(report['eligible_universe'],2)
