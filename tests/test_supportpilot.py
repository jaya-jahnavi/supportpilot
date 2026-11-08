import concurrent.futures
import http.cookiejar
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

class PlatformTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  (ROOT/'.local').mkdir(exist_ok=True)
  cls.temp=tempfile.TemporaryDirectory(dir=ROOT/'.local')
  os.environ['SUPPORTPILOT_DATA']=cls.temp.name
  os.environ['LLM_ENABLED']='0'
  subprocess.run([sys.executable,'-m','app.seed'],cwd=ROOT,check=True,capture_output=True)
  cls.account=json.loads((Path(cls.temp.name)/'demo-credentials.json').read_text())
  with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
  cls.base=f'http://127.0.0.1:{port}'
  cls.server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  for _ in range(100):
   try:urllib.request.urlopen(cls.base+'/health/ready',timeout=1);break
   except Exception:time.sleep(.1)
  else:cls.server.terminate();raise RuntimeError('Test API did not start.')
  from app import worker
  from app.db import connect
  cls.worker=worker;cls.connect=staticmethod(connect)
 @classmethod
 def tearDownClass(cls):
  cls.server.terminate();cls.server.wait(timeout=10);cls.temp.cleanup()
 def setUp(self):
  with self.connect() as db:
   for table in ('events','tickets','sessions','workers','login_limits'):db.execute('DELETE FROM '+table)
  self.client=self.new_client()
  self.assertEqual(self.request('/api/login','POST',self.account)[0],200)
 def new_client(self):return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
 def request(self,path,method='GET',body=None,headers=None,client=None):
  req=urllib.request.Request(self.base+path,method=method,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-SupportPilot-Request':'1',**(headers or {})})
  try:r=(client or self.client).open(req,timeout=10)
  except urllib.error.HTTPError as e:r=e
  raw=r.read()
  try:value=json.loads(raw)
  except ValueError:value=raw.decode()
  return r.status,value,r.headers
 def create(self,subject='Return an unused product',body='I want to return my unused item delivered last week.',key=None):
  code,t,_=self.request('/api/tickets','POST',{'subject':subject,'body':body},headers={'Idempotency-Key':key} if key else {})
  self.assertEqual(code,201,t);return t
 def ready(self):
  t=self.create();self.worker.once();result=self.request('/api/tickets/'+t['id'])[1]
  self.assertEqual(result['status'],'ready',result);return result
 def test_authentication_origin_and_session_revocation(self):
  self.assertEqual(self.request('/api/tickets',client=self.new_client())[0],401)
  self.assertEqual(self.request('/api/tickets','POST',{},headers={'X-SupportPilot-Request':''})[0],403)
  self.assertEqual(self.request('/api/tickets','POST',{},headers={'Origin':'https://evil.example'})[0],403)
  self.request('/api/logout','POST')
  self.assertEqual(self.request('/api/tickets')[0],401)
 def test_password_throttling(self):
  c=self.new_client()
  for _ in range(5):self.assertEqual(self.request('/api/login','POST',{'email':'bad@example.test','password':'bad'},client=c)[0],401)
  self.assertEqual(self.request('/api/login','POST',{'email':'bad@example.test','password':'bad'},client=c)[0],429)
 def test_idempotent_submission_and_payload_conflict(self):
  a=self.create(key='request-1');b=self.create(key='request-1')
  self.assertEqual(a['id'],b['id'])
  self.assertEqual(len(self.request('/api/tickets')[1]),1)
  self.assertEqual(self.request('/api/tickets','POST',{'subject':'Different subject','body':'Different ticket content.'},headers={'Idempotency-Key':'request-1'})[0],409)
 def test_worker_retrieves_policies_and_records_trace(self):
  t=self.ready()
  self.assertEqual(t['draft']['mode'],'retrieval_only')
  self.assertIn('KB-001',t['draft']['citations'])
  self.assertTrue(t['draft']['review_required'])
  self.assertEqual([s['step'] for s in t['trace']],['classify_ticket','search_knowledge','generate_draft'])
 def test_review_edits_and_concurrent_version_conflict(self):
  t=self.ready();url='/api/tickets/'+t['id']+'/review'
  body={'action':'approve','reply':'Thank you. Please share your order number for review.','expected_version':t['version']}
  a=self.request(url,'POST',body)
  self.assertEqual(a[1]['status'],'approved')
  self.assertEqual(a[1]['draft']['reply'],body['reply'])
  self.assertEqual(self.request(url,'POST',body)[0],409)
 def test_failed_generation_retries_are_bounded(self):
  t=self.create()
  with patch.object(self.worker,'draft',side_effect=TimeoutError('provider unavailable')):
   with patch.object(self.worker.log,'exception'):
    self.worker.once();self.worker.once()
  self.assertFalse(self.worker.once())
  r=self.request('/api/tickets/'+t['id'])[1]
  self.assertEqual((r['status'],r['attempts']),('failed',2))
  self.assertEqual(self.request('/api/tickets/'+t['id']+'/retry','POST')[0],200)
 def test_expired_lease_recovers(self):
  t=self.create()
  with self.connect() as db:db.execute("UPDATE tickets SET status='running',attempts=1,worker='dead',lease_until=? WHERE id=?",(time.time()-1,t['id']))
  self.worker.once()
  r=self.request('/api/tickets/'+t['id'])[1]
  self.assertEqual((r['status'],r['attempts']),('ready',2))
 def test_stale_result_cannot_overwrite_review_or_lease(self):
  t=self.create()
  def lose_lease(*args):
   with self.connect() as db:db.execute("UPDATE tickets SET worker='replacement' WHERE id=?",(t['id'],))
   return {'mode':'retrieval_only','reply':'This result must not be saved.','citations':[],'model':None,'prompt_version':'test'}
  with patch.object(self.worker,'draft',side_effect=lose_lease):self.worker.once()
  self.assertIsNone(self.request('/api/tickets/'+t['id'])[1]['draft'])
 def test_competing_workers_claim_only_once(self):
  t=self.create()
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:r=list(pool.map(lambda _:self.worker.once(),range(2)))
  self.assertEqual(sum(r),1)
  self.assertEqual(self.request('/api/tickets/'+t['id'])[1]['attempts'],1)
 def test_bounds_and_queue_capacity(self):
  self.assertEqual(self.request('/api/tickets','POST',{'subject':'ab','body':'short'})[0],422)
  self.assertEqual(self.request('/api/tickets','POST',{'subject':'x'*40000})[0],413)
  for _ in range(20):self.create()
  self.assertEqual(self.request('/api/tickets','POST',{'subject':'Over capacity','body':'A valid request that exceeds queue capacity.'})[0],429)
 def test_search_sanitizes_fts_syntax(self):
  from app.retrieval import search
  self.assertIsInstance(search('" OR * NEAR()'),list)
  self.assertEqual(search('the and my'),[])
 def test_no_evidence_does_not_invent_policy(self):
  from app.llm import draft
  with patch.dict(os.environ,{'LLM_ENABLED':'1'}):
   r=draft('Quantum teleportation','Teleport a quantum banana.',[])
  self.assertEqual(r['mode'],'no_evidence')
  self.assertEqual(r['citations'],[])
 def test_high_priority_security_classification(self):
  from app.retrieval import classify
  self.assertEqual(classify('Unauthorized login','My account is compromised')['priority'],'high')
 def test_metrics_and_audit_require_authentication(self):
  self.ready()
  self.assertIn('supportpilot_tickets{status="ready"} 1',self.request('/metrics')[1])
  self.assertEqual(self.request('/metrics',client=self.new_client())[0],401)
  self.assertIn('draft.ready',[e['action'] for e in self.request('/api/operations')[1]['events']])
 def test_provider_real_http_contract_and_bad_citations(self):
  from app.llm import LocalLLM
  from app.retrieval import search
  state={'bad':False}
  class Handler(BaseHTTPRequestHandler):
   def do_POST(self):
    req=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
    schema=req['response_format']['json_schema']['schema']
    allowed=schema['properties']['citations']['items']['enum']
    answer={'reply':'Please share the order number so the team can review your return.','citations':['MADE-UP' if state['bad'] else allowed[0]]}
    data=json.dumps({'choices':[{'message':{'content':json.dumps(answer)}}],'usage':{'total_tokens':40}}).encode()
    self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
   def log_message(self,*args):pass
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   with patch.dict(os.environ,{'LLM_BASE_URL':f'http://127.0.0.1:{server.server_port}/v1'}):
    r=LocalLLM().generate('Returns','Return my item',search('return unused'))
    self.assertEqual(r['mode'],'llm')
    state['bad']=True
    with self.assertRaises(ValueError):LocalLLM().generate('Returns','Return my item',search('return unused'))
  finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main()
