import unittest
from option_moves import summarize_moves

class OptionMoveTests(unittest.TestCase):
    def test_chronological_same_contract_and_direction(self):
        dates=['20261014','20261015','20261016','20261019','20261020']
        contracts=[dict(ts_code='C',main_code='A',call_put='C',days_to_expiry=10),dict(ts_code='P',main_code='A',call_put='P',days_to_expiry=15)]
        quotes={d:{'C':p,'P':q} for d,p,q in zip(dates,[1,2,6,3,2],[10,9,8,3,1])}
        result=summarize_moves(contracts,dates,quotes)
        self.assertEqual(result['A']['C']['matches'][0]['multiple'],6)
        self.assertEqual(result['A']['C']['matches'][0]['end_date'],'20261016')
        self.assertEqual(result['A']['P']['matches'],[])
        self.assertEqual(result['A']['P']['status'],'complete')

    def test_missing_and_zero_are_not_no_match(self):
        dates=['1','2','3','4','5']
        contracts=[dict(ts_code='C',main_code='A',call_put='C',days_to_expiry=1)]
        result=summarize_moves(contracts,dates,{d:{'C':0} for d in dates})
        self.assertEqual(result['A']['C']['status'],'incomplete')

    def test_excludes_expired_and_longer_contracts(self):
        contracts=[dict(ts_code=str(i),main_code='A',call_put='C',days_to_expiry=i) for i in [0,16]]
        self.assertEqual(summarize_moves(contracts,['1','2','3','4','5'],{}),{})

    def test_history_reader_uses_only_requested_dates(self):
        import tempfile
        from pathlib import Path
        from option_moves import build_option_moves
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'raw/options/daily';path.mkdir(parents=True)
            dates=['20261014','20261015','20261016','20261019','20261020']
            for date,close in zip(dates,[1,2,5,4,3]):
                (path/f'DCE_{date}.csv').write_text(f'ts_code,trade_date,close\nC,{date},{close}\n')
            result=build_option_moves(directory,{'asof':dates[-1],'candles':{'A':[[d] for d in dates]}},{'records':[dict(ts_code='C',main_code='A',call_put='C',days_to_expiry=5)]})
            self.assertEqual(result['groups']['A']['C']['matches'][0]['multiple'],5)
