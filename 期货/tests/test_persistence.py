import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from mysql_store import mysql_config
from snapshot_store import publish_snapshot,read_snapshot,snapshot_source
from research_server import ResearchStore,available_snapshots

class PersistenceTests(unittest.TestCase):
    def test_failed_publish_keeps_previous_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'working';(source/'quality').mkdir(parents=True)
            (source/'quality/history_run.json').write_text(json.dumps({'prepared':[]}))
            (source/'quality/latest_run.json').write_text('old')
            payload={'asof':'20260911','phase_settings':{},'records':[],'curves':{}}
            publish_snapshot(root,payload,source);old=snapshot_source(root,'20260911')
            (source/'quality/latest_run.json').write_text('new')
            with patch('snapshot_store.atomic_json',side_effect=OSError('publication failed')):
                with self.assertRaises(OSError):publish_snapshot(root,payload,source)
            self.assertEqual(snapshot_source(root,'20260911'),old)
            self.assertEqual((old/'quality/latest_run.json').read_text(),'old')
            self.assertEqual(read_snapshot(root,'20260911')['source_id'],old.name)

    def test_supplements_are_copied_into_update_working_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'supplemental').mkdir();(root/'supplemental/fundamentals.csv').write_text('verified')
            store=ResearchStore.__new__(ResearchStore);store.root=root
            store.copy_supplements(root/'updates/20260911')
            self.assertEqual((root/'updates/20260911/supplemental/fundamentals.csv').read_text(),'verified')

    def test_store_uses_file_snapshots_when_mysql_cache_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);published={}
            for asof in ['20260917','20260918']:
                source=root/f'working-{asof}';(source/'quality').mkdir(parents=True)
                (source/'quality/history_run.json').write_text(json.dumps({'prepared':[]}))
                (source/'quality/latest_run.json').write_text('{}')
                payload=dict(asof=asof,phase_settings={},records=[],decisions=[],names={},
                    sectors={},curves={'X':[]},moving={},factors=[],quality={'success':True})
                published[asof]=publish_snapshot(root,payload,source)
            with patch('research_server.mysql_cache_get',return_value=None):
                store=ResearchStore(root,'20260918')
                self.assertEqual(store.get('20260918')['data_hash'],published['20260918']['data_hash'])
                self.assertEqual(store.get('20260917')['data_hash'],published['20260917']['data_hash'])

    def test_mysql_config_uses_short_connection_timeouts(self):
        with patch.dict(os.environ,{'MYSQL_CONNECT_TIMEOUT':'4','MYSQL_READ_TIMEOUT':'5','MYSQL_WRITE_TIMEOUT':'6'}):
            cfg=mysql_config()
        self.assertEqual(cfg['connect_timeout'],4)
        self.assertEqual(cfg['read_timeout'],5)
        self.assertEqual(cfg['write_timeout'],6)

    def test_available_snapshots_falls_back_to_file_bundles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'working';(source/'quality').mkdir(parents=True)
            (source/'quality/history_run.json').write_text(json.dumps({'prepared':[]}))
            (source/'quality/latest_run.json').write_text('{}')
            publish_snapshot(root,dict(asof='20260918',phase_settings={},records=[],decisions=[],
                names={},sectors={},curves={'X':[]},moving={},factors=[],quality={'success':True}),source)
            with patch('research_server.mysql_cached_dates',return_value=[]):
                snapshots=available_snapshots(root)
            self.assertEqual([item['asof'] for item in snapshots],['20260918'])
            self.assertEqual(snapshots[0]['universe'],1)

    def test_hv_rejects_missing_trading_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'processed/options/20260911/report.json';path.parent.mkdir(parents=True)
            record={'main_code':'X','underlying_code':'X2611','rate':.02}
            path.write_text(json.dumps({'records':[record],'success':True}))
            store=ResearchStore.__new__(ResearchStore);store.root=root
            store.lock=threading.RLock();store.option_cache={}
            dates=[str(i) for i in range(22)];values=[[day,100+i] for i,day in enumerate(dates)]
            store.get=lambda asof:{'curves':{'X':values}}
            store.underlying=lambda asof,code:{'values':values[:10]+values[11:]}
            with patch('research_server.snapshot_source',return_value=root):
                result=store.option_payload('20260911')['records'][0]
            self.assertIsNone(result['hv20'])
            self.assertIsNone(result['hv60'])
            store.underlying=lambda asof,code:{'values':values}
            store.option_cache={}
            with patch('research_server.snapshot_source',return_value=root):
                result=store.option_payload('20260911')['records'][0]
            self.assertGreater(result['hv20'],0)
