"""Local research API with durable snapshots and serial asynchronous jobs."""
import argparse
import json
import threading
import uuid
import shutil
import os
from datetime import datetime
from dataclasses import asdict
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from dashboard_data import build_payload, LABELS, BOOLEAN_FIELDS
from decision_v2 import build_decisions
from collector import DataError, atomic_json, read_csv
from config import DATA_DIR
from trend_phases import PhaseSettings
from snapshot_store import publish_snapshot,read_snapshot,list_snapshots,snapshot_source

def mysql_cache_enabled():
    return os.getenv('MYSQL_READ_CACHE','0').lower() in {'1','true','yes','on'}

def mysql_cache_get(asof,key):
    if not mysql_cache_enabled():
        return None
    try:
        from mysql_store import cache_get
        return cache_get(asof,key)
    except Exception:
        return None

def valid_date(value):
    if not isinstance(value,str) or len(value)!=8 or not value.isdigit():raise ValueError('日期必须为YYYYMMDD')
    datetime.strptime(value,'%Y%m%d');return value

def phase_settings(values):
    settings=PhaseSettings(**values)
    for value in asdict(settings).values():
        if not isinstance(value,(int,float)) or not 0<=value<=100:raise ValueError('阶段阈值必须在0—100之间')
    if settings.max_extension_atr<=0 or settings.forming_adx>settings.adx_min:raise ValueError('阶段阈值顺序或ATR偏离无效')
    return settings

def ensure_decision_payload(payload):
    payload=dict(payload)
    if 'decisions' not in payload:
        payload['decisions']=build_decisions(payload.get('records',[]))
    payload['decision_summary']={state:sum(1 for row in payload['decisions'] if row.get('state_v2')==state) for state in ['WAIT','PREPARE','START','TREND','EXHAUST']}
    factors=list(payload.get('factors',[]));existing={item.get('key') for item in factors}
    for key,value in LABELS.items():
        if key not in existing:
            factors.append(dict(key=key,label=value[0],group=value[1],unit=value[2],type='boolean' if key in BOOLEAN_FIELDS else 'number'))
    payload['factors']=factors
    return payload

class ResearchStore:
    def __init__(self,root,asof):
        self.root=Path(root);self.lock=threading.RLock();self.job={'status':'idle'};self.active=asof;self.option_cache={}
        phase_path=self.root/'quality/phase_settings.json'
        self.phase=phase_settings(json.loads(phase_path.read_text(encoding='utf-8'))) if phase_path.exists() else PhaseSettings()
        archive=self.root/f'processed/dashboard/{asof}.json'
        self.payload=ensure_decision_payload(read_snapshot(self.root,asof) if archive.exists() or archive.with_suffix('.bundle.json').exists() else publish_snapshot(self.root,build_payload(self.root,asof,self.phase),self.root))
        self._persist_state()
    def _persist_state(self):atomic_json(dict(active=self.active,job=self.job),self.root/'quality/dashboard_state.json')
    def get(self,asof=None):
        asof = asof or self.active
        cached=mysql_cache_get(asof,'api:data')
        if cached is not None:return ensure_decision_payload(cached)
        with self.lock:return self.payload if asof==self.active else ensure_decision_payload(read_snapshot(self.root,asof))
    def begin(self,kind,request):
        with self.lock:
            if self.job['status'] in ['queued','running']:raise ValueError('已有任务运行，请等待完成')
            asof=valid_date(request.get('asof',self.active))
            if kind=='update':
                now=datetime.now()
                if asof>now.strftime('%Y%m%d') or asof==now.strftime('%Y%m%d') and now.hour<17:raise ValueError('只能更新已收盘日期；当日17点后开放')
            elif asof!=self.active:read_snapshot(self.root,asof)
            self.job=dict(id=uuid.uuid4().hex,kind=kind,asof=asof,status='queued',message='等待执行',started_at=datetime.now().isoformat(timespec='seconds'))
            self._persist_state();threading.Thread(target=self._worker,args=(kind,asof,request),daemon=True).start();return dict(self.job)
    def progress(self,message):
        with self.lock:self.job.update(status='running',message=message);self._persist_state()
    def _worker(self,kind,asof,request):
        try:
            self.progress('任务开始')
            if kind=='update':
                from fetch_futures_data import make_collector
                from focused import run_focused
                from history import prepare_history
                source=self.root/'updates'/asof;collector=make_collector(root=source)
                self.progress('采集五交易所主力与次主力；旧快照继续可用')
                result=run_focused(collector,asof,asof,bool(request.get('force',False)))
                if not result['success'] or asof not in result['published_days']:raise DataError('日期休市或采集不完整，保留原快照')
                self.progress('补齐历史与换月校正')
                prepare_history(collector,read_csv(source/f'raw/selected/{asof}.csv'),asof,force=bool(request.get('force',False)),progress=self.progress)
                self.progress('验证指标并发布快照');self.copy_supplements(source);payload=build_payload(source,asof,self.phase)
                if not payload['quality']['success']:raise DataError('有效篮子不足，保留原快照')
                payload=publish_snapshot(self.root,payload,source)
                with self.lock:self.active,self.payload=asof,ensure_decision_payload(payload)
            elif kind=='reload':
                source=self.root/'reloads'/uuid.uuid4().hex
                shutil.copytree(snapshot_source(self.root,asof),source)
                self.copy_supplements(source)
                payload=publish_snapshot(self.root,build_payload(source,asof,self.phase),source)
                with self.lock:self.active,self.payload=asof,ensure_decision_payload(payload)
            elif kind=='options':
                from option_data import fetch_options
                result=fetch_options(self.root,asof,bool(request.get('force',False)),self.progress,selected_root=snapshot_source(self.root,asof))
                if not result['records']:raise DataError('期权接口没有可用链，请查看覆盖报告')
                if result['failures']:
                    with self.lock:self.job.update(status='partial',message=f'期权链已保存，{len(result["failures"])}项覆盖失败')
                    return
            with self.lock:self.job.update(status='success',message='任务完成',finished_at=datetime.now().isoformat(timespec='seconds'));self.option_cache={}
        except Exception as exc:
            with self.lock:self.job.update(status='failed',message=str(exc) if isinstance(exc,(DataError,ValueError)) else type(exc).__name__,finished_at=datetime.now().isoformat(timespec='seconds'))
        finally:
            with self.lock:self._persist_state()
    def copy_supplements(self,source):
        for relative in ['supplemental/fundamentals.csv','raw/reference/quote_units.json']:
            src=self.root/relative;dst=Path(source)/relative
            if src.exists():dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    def option_payload(self,asof,code=None,rate=.02):
        if not 0<=rate<=.2:raise ValueError('参考无风险利率须在0—20%之间')
        if code is None and abs(rate-.02)<1e-12:
            cached=mysql_cache_get(asof,'api:options:rate:0.02')
            if cached is not None:return cached
        key=(asof,round(rate,6))
        with self.lock:cached=self.option_cache.get(key)
        if cached is None:
            cached=self._build_option_payload(asof,rate)
            with self.lock:self.option_cache[key]=cached
        if code:
            result=dict(cached);result['records']=[r for r in cached['records'] if r['main_code']==code];return result
        return cached
    def _build_option_payload(self,asof,rate):
        path=self.root/f'processed/options/{asof}/report.json'
        if not path.exists():return dict(asof=asof,records=[],coverage=[],failures=[],status='尚未采集该日期期权数据')
        from option_analysis import option_metrics
        import numpy as np
        result=json.loads(path.read_text(encoding='utf-8'));records=[];hv={};source=snapshot_source(self.root,asof)
        for record in result['records']:
            if record['underlying_code'] not in hv:
                value={'hv20':None,'hv60':None}
                try:
                    data=self.underlying(asof,record['underlying_code'])
                    expected=self.get(asof)['curves'][record['main_code']]
                    for n in [20,60]:
                        window=data['values'][-n-1:]
                        if len(window)==n+1 and [v[0] for v in window]==[v[0] for v in expected[-n-1:]]:
                            prices=np.array([v[1] for v in window]);value[f'hv{n}']=float(np.std(np.diff(np.log(prices)),ddof=1)*np.sqrt(252)*100)
                    if any(v is None for v in value.values()):value['hv_reason']=data.get('reason','Insufficient or discontinuous underlying history')
                except (DataError,OSError,KeyError,StopIteration):value['hv_reason']='Underlying history validation failed'
                hv[record['underlying_code']]=value
            if (rate!=record['rate'] or 'delta' not in record) and 'premium' in record and 'underlying_close' in record:
                metadata=dict(record,opt_multiplier=record.get('multiplier'));record.update(option_metrics(metadata,dict(close=record['premium'],vol=record['vol'],oi=record['oi']),asof,record['underlying_close'],rate))
            records.append(record|hv[record['underlying_code']])
        result['records']=records;result['status']='已采集' if result['success'] else '部分覆盖'
        try:
            from option_scanner import annotate_options
            annotate_options(self.get(asof),result)
        except Exception as exc:
            result['tradability_error']=type(exc).__name__
        return result
    def underlying(self,asof,code):
        cached=mysql_cache_get(asof,f'api:options:underlying:{code}')
        if cached is not None:return cached
        import hashlib
        import pandas as pd
        payload=self.get(asof);row=next((r for r in payload['records'] if code in [r.get('main_code'),r.get('secondary_code')]),None)
        if row is None:return dict(code=code,values=[],reason='标的未通过期货历史校验')
        source=snapshot_source(self.root,asof);path=source/f'processed/pair_history/{row["ts_code"].replace(".","_")}.csv'
        entries=json.loads((source/'quality/history_run.json').read_text(encoding='utf-8'))['prepared'];entry=next(e for e in entries if e['ts_code']==row['ts_code'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['pair_sha256']:raise DataError('真实标的历史哈希不匹配')
        frame=read_csv(path);frame=frame[frame.ts_code.eq(code)&frame.trade_date.le(asof)].sort_values('trade_date')
        if frame.empty or frame.trade_date.iloc[-1]!=asof:return dict(code=code,values=[],reason='真实标的历史不足或过期')
        if not frame.close.gt(0).all():raise DataError('真实标的价格无效')
        moving={key:[float(value) if pd.notna(value) else None for value in frame.close.rolling(n).mean()] for key,n in [('ma20',20),('ma60',60)]}
        return dict(code=code,values=[[day,float(close)] for day,close in zip(frame.trade_date,frame.close)],moving=moving)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--asof');parser.add_argument('--data-dir',type=Path,default=DATA_DIR);parser.add_argument('--port',type=int,default=8765);args=parser.parse_args()
    state=args.data_dir/'quality/dashboard_state.json'
    asof=args.asof or (json.loads(state.read_text(encoding='utf-8'))['active'] if state.exists() else json.loads((args.data_dir/'quality/history_run.json').read_text(encoding='utf-8'))['asof'])
    store=ResearchStore(args.data_dir,valid_date(asof));frontend=Path(__file__).with_name('frontend')
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*params,**kwargs):super().__init__(*params,directory=str(frontend),**kwargs)
        def respond(self,value,status=200):
            payload=json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8');self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        def do_GET(self):
            parsed=urlparse(self.path);params=parse_qs(parsed.query)
            try:
                asof=valid_date(params['asof'][0]) if 'asof' in params else store.active
                if parsed.path=='/api/data':self.respond(store.get(asof))
                elif parsed.path=='/api/snapshots':self.respond(dict(active=store.active,snapshots=list_snapshots(store.root)))
                elif parsed.path=='/api/jobs':self.respond(store.job)
                elif parsed.path=='/api/options':self.respond(store.option_payload(asof,params.get('code',[None])[0],float(params.get('rate',[.02])[0])))
                elif parsed.path=='/api/scanner':
                    from option_scanner import build_scanner
                    top=min(max(int(params.get('top',['5'])[0]),1),10)
                    cached=mysql_cache_get(asof,f'api:scanner:top:{top}')
                    self.respond(cached if cached is not None else build_scanner(store.get(asof),store.option_payload(asof),top))
                elif parsed.path=='/api/options/underlying':self.respond(store.underlying(asof,params.get('code',[''])[0]))
                elif parsed.path=='/api/runs':self.respond([json.loads(path.read_text(encoding='utf-8')) for path in sorted((store.root/'processed/filter_runs').glob('*.json'),reverse=True)][:30])
                elif parsed.path=='/api/template':self.respond(dict(columns=['ts_code','trade_date','available_date','underlying_code','quote_unit','source','spot_price','commodity_oi'],records=[]))
                elif parsed.path.startswith('/api/'):self.respond(dict(error='Unknown API'),404)
                else:super().do_GET()
            except (ValueError,DataError,OSError,TypeError) as exc:self.respond(dict(error=str(exc) if isinstance(exc,(ValueError,DataError)) else type(exc).__name__),400)
        def do_POST(self):
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=2_000_000:raise ValueError('请求体大小无效')
                request=json.loads(self.rfile.read(length));path=urlparse(self.path).path
                if path in ['/api/update','/api/reload','/api/options/refresh']:self.respond(store.begin({'/api/update':'update','/api/reload':'reload','/api/options/refresh':'options'}[path],request),202)
                elif path=='/api/phases':
                    with store.lock:
                        if store.job['status'] in ['queued','running']:raise ValueError('已有任务运行，暂不修改阶段参数')
                        store.phase=phase_settings(request);atomic_json(asdict(store.phase),store.root/'quality/phase_settings.json');self.respond(store.begin('reload',dict(asof=store.active)),202)
                elif path=='/api/validate':
                    from historical_validation import run_validation
                    asof=valid_date(request.pop('asof',store.active));report=run_validation(snapshot_source(store.root,asof),asof,request);atomic_json(report,store.root/f'processed/validation/{report["id"]}.json');self.respond(report)
                elif path=='/api/supplements':
                    from supplements import import_supplements
                    with store.lock:
                        if store.job['status'] in ['queued','running']:raise ValueError('已有任务运行，暂不修改补充数据')
                        result=import_supplements(store.root,request['records']);result['job']=store.begin('reload',dict(asof=store.active));self.respond(result,202)
                elif path=='/api/runs':
                    from research_rules import validate_rules,rule_matches
                    config=request['config'];validate_rules(config['rules'],config['match'],LABELS);asof=valid_date(request.get('asof',store.active));payload=store.get(asof)
                    if config['direction'] not in ['long','short']:raise ValueError('Invalid direction')
                    rows=payload.get('decisions') or payload['records'];state_filter=request.get('phase','all')
                    records=[r['ts_code'] for r in rows if (rows is payload.get('decisions') or r.get('direction')==config['direction']) and (request.get('sector','all')=='all' or r.get('sector')==request['sector']) and (state_filter=='all' or r.get('state_v2',r.get('phase'))==state_filter) and rule_matches(r,config['rules'],config['match'])[0]]
                    record=dict(id=uuid.uuid4().hex,asof=asof,data_hash=payload['data_hash'],config=config,sector=request.get('sector','all'),phase_filter=request.get('phase','all'),matches=records,time=datetime.now().isoformat(timespec='seconds'))
                    atomic_json(record,store.root/f'processed/filter_runs/{record["time"].replace(":","-")}_{record["id"]}.json');self.respond(record)
                else:self.respond(dict(error='Unknown API'),404)
            except (ValueError,DataError,OSError,KeyError,TypeError) as exc:self.respond(dict(error=str(exc) if isinstance(exc,(ValueError,DataError)) else type(exc).__name__),400)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);print(f'Dashboard {asof}: http://127.0.0.1:{args.port}',flush=True)
    threading.Thread(target=lambda:store.option_payload(store.active),daemon=True).start()
    try:server.serve_forever()
    except KeyboardInterrupt:server.server_close()

if __name__=='__main__':main()
