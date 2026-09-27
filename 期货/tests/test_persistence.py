import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from mysql_store import mysql_config, SCHEMA_SQL, metric_column_migrations
from snapshot_store import publish_snapshot,read_snapshot,snapshot_source
from research_server import ResearchStore,available_snapshots
from dashboard_data import CHART_SCHEMA_VERSION, PAYLOAD_SCHEMA_VERSION
from trend_model import MODEL_VERSION

class PersistenceTests(unittest.TestCase):
    def test_mysql_metric_schema_and_migration_are_ema20_only(self):
        schema=next(sql for sql in SCHEMA_SQL if 'CREATE TABLE IF NOT EXISTS commodity_metrics_daily' in sql)
        self.assertIn('ema20 DECIMAL',schema)
        self.assertIn('ema20_slope5_atr DECIMAL',schema)
        self.assertIn('ema20_distance_atr DECIMAL',schema)
        for old in ['\n      ma20 DECIMAL','\n      ma60 DECIMAL','\n      ma120 DECIMAL']:
            self.assertNotIn(old,schema)
        legacy={'trade_date','commodity_code','ma20','ma60','ma120','payload_json'}
        migration=metric_column_migrations(legacy)
        self.assertEqual(sum(' ADD COLUMN ' in sql for sql in migration),3)
        self.assertEqual(sum(' DROP COLUMN ' in sql for sql in migration),3)
        current={'trade_date','commodity_code','ema20','ema20_slope5_atr','ema20_distance_atr','payload_json'}
        self.assertEqual(metric_column_migrations(current),[])

    def test_snapshot_copies_holding_raw_summary_and_quality(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'working';(source/'quality').mkdir(parents=True)
            (source/'quality/history_run.json').write_text(json.dumps({'prepared':[]}))
            (source/'quality/latest_run.json').write_text('{}')
            files={
                'raw/holding/DCE/20260924/M2701.csv':'raw rows',
                'raw/holding/DCE/20260924/M2701.json':'receipt',
                'processed/holding/20260924.json':'summary',
                'quality/holding_20260924.json':'quality',
            }
            for relative,content in files.items():
                path=source/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content)
            payload={'asof':'20260924','phase_settings':{},'records':[],'decisions':[]}
            publish_snapshot(root,payload,source)
            published=snapshot_source(root,'20260924')
            for relative,content in files.items():
                self.assertEqual((published/relative).read_text(),content)

    def test_store_rebuilds_cached_payload_without_current_payload_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);asof='20260924';source=root/'updates'/asof
            (source/'quality').mkdir(parents=True)
            (source/'quality/history_run.json').write_text(json.dumps({'asof':asof}))
            cached=dict(asof=asof,records=[],decisions=[],factors=[],model_version=MODEL_VERSION,
                        chart_schema_version=CHART_SCHEMA_VERSION)
            fresh=dict(cached,payload_schema_version=PAYLOAD_SCHEMA_VERSION)
            store=ResearchStore.__new__(ResearchStore);store.root=root;store.phase=object()
            with patch('research_server.mysql_cache_get',return_value=cached), \
                    patch('research_server.build_payload',return_value=fresh) as build:
                result=store._load(asof)
            self.assertEqual(result['payload_schema_version'],PAYLOAD_SCHEMA_VERSION)
            build.assert_called_once_with(source,asof,store.phase)

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
