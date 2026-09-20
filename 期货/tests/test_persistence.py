import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from snapshot_store import publish_snapshot,read_snapshot,snapshot_source
from research_server import ResearchStore

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
