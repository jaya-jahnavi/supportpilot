import hashlib
import json
import os
from pathlib import Path
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI,Request,Depends,HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse,JSONResponse,Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,ConfigDict,Field
from .db import connect,init,event,public
from .security import verify
from .retrieval import search

STATIC=Path(__file__).parent/'static'
COOKIE='supportpilot_session'
@asynccontextmanager
async def lifespan(app):
    init()
    yield
app=FastAPI(title='SupportPilot AI Reply Copilot',version='1.0.0',lifespan=lifespan,docs_url=None,redoc_url=None)

@app.exception_handler(RequestValidationError)
async def invalid(request,exc):
    return JSONResponse({'detail':'Invalid request. Check field types and limits.'},status_code=422)

@app.middleware('http')
async def protect(request,call_next):
    if request.method in ('POST','PUT','PATCH','DELETE'):
        if request.headers.get('x-supportpilot-request')!='1':
            return JSONResponse({'detail':'Request protection header required.'},status_code=403)
        origin=request.headers.get('origin')
        expected=os.environ.get('PORTAL_ORIGIN',str(request.base_url).rstrip('/'))
        if origin and origin!=expected:return JSONResponse({'detail':'Origin is not allowed.'},status_code=403)
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>32768:return JSONResponse({'detail':'Maximum request size is 32 KB.'},status_code=413)
        request._body=bytes(body)
    response=await call_next(request)
    response.headers.update({'X-Content-Type-Options':'nosniff','Cache-Control':'no-store',
      'Referrer-Policy':'no-referrer','X-Frame-Options':'DENY',
      'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
    return response

def operator(request:Request):
    digest=hashlib.sha256(request.cookies.get(COOKIE,'').encode()).hexdigest()
    with connect() as db:
        row=db.execute('SELECT email FROM sessions WHERE token=? AND expires>?',(digest,time.time())).fetchone()
    if not row:raise HTTPException(401,'Sign in to continue.')
    return row['email']

class Login(BaseModel):
    email:str=Field(max_length=160)
    password:str=Field(max_length=256)

@app.post('/api/login')
def login(body:Login):
    email,now=body.email.strip().lower(),time.time()
    with connect() as db:
        limit=db.execute('SELECT * FROM login_limits WHERE email=?',(email,)).fetchone()
        if limit and limit['failures']>=5 and limit['expires']>now:raise HTTPException(429,'Try again in 15 minutes.')
        row=db.execute('SELECT password FROM users WHERE email=?',(email,)).fetchone()
        valid=verify(body.password,row['password'] if row else '00'*16+':'+'00'*64)
        failed=not(row and valid)
        if failed:
            count=limit['failures']+1 if limit and limit['expires']>now else 1
            db.execute('INSERT OR REPLACE INTO login_limits VALUES(?,?,?)',(email,count,now+900))
        else:
            db.execute('DELETE FROM login_limits WHERE email=?',(email,))
            db.execute('DELETE FROM sessions WHERE expires<?',(now,))
            token=secrets.token_urlsafe(32)
            db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),email,now+28800))
    if failed:raise HTTPException(401,'Invalid email or password.')
    r=JSONResponse({'ok':True})
    r.set_cookie(COOKIE,token,httponly=True,samesite='strict',max_age=28800,secure=os.environ.get('COOKIE_SECURE','0')=='1')
    return r

@app.post('/api/logout')
def logout(request:Request,email=Depends(operator)):
    with connect() as db:db.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(request.cookies[COOKIE].encode()).hexdigest(),))
    r=JSONResponse({'ok':True});r.delete_cookie(COOKIE);return r

@app.get('/api/me')
def me(email=Depends(operator)):
    return {'email':email,'llm_enabled':os.environ.get('LLM_ENABLED','0')=='1',
      'model':os.environ.get('LLM_MODEL','qwen2.5-0.5b-instruct')}

class NewTicket(BaseModel):
    model_config=ConfigDict(extra='forbid')
    subject:str=Field(min_length=3,max_length=160)
    body:str=Field(min_length=10,max_length=6000)

class Review(BaseModel):
    model_config=ConfigDict(extra='forbid')
    action:Literal['approve','reject']
    expected_version:int=Field(ge=1)
    reply:str=Field(min_length=10,max_length=2400)

def get_ticket(db,ticket_id):
    row=db.execute('SELECT * FROM tickets WHERE id=?',(ticket_id,)).fetchone()
    if not row:raise HTTPException(404,'Ticket not found.')
    return row

@app.post('/api/tickets',status_code=201)
def submit(body:NewTicket,request:Request,email=Depends(operator)):
    key=request.headers.get('idempotency-key')
    if key and len(key)>100:raise HTTPException(422,'Idempotency key too long.')
    digest=hashlib.sha256(json.dumps(body.model_dump(),sort_keys=True).encode()).hexdigest()
    now,ticket_id=time.time(),str(uuid.uuid4())
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if key:
            previous=db.execute('SELECT * FROM tickets WHERE idempotency_key=?',(key,)).fetchone()
            if previous:
                if previous['payload_sha']!=digest:raise HTTPException(409,'Idempotency key already used for a different request.')
                return public(previous)
        count=db.execute("SELECT COUNT(*) FROM tickets WHERE status IN ('queued','running')").fetchone()[0]
        if count>=20:raise HTTPException(429,'Queue is full. Wait for processing.')
        db.execute("""INSERT INTO tickets(id,subject,body,status,created,updated,idempotency_key,payload_sha)
            VALUES(?,?,?,'queued',?,?,?,?)""",(ticket_id,body.subject,body.body,now,now,key,digest))
        event(db,'ticket.queued',ticket_id)
        return public(get_ticket(db,ticket_id))

@app.get('/api/tickets')
def tickets(email=Depends(operator)):
    with connect() as db:return [public(r) for r in db.execute('SELECT * FROM tickets ORDER BY created DESC LIMIT 200')]

@app.get('/api/tickets/{ticket_id}')
def ticket(ticket_id:str,email=Depends(operator)):
    with connect() as db:return public(get_ticket(db,ticket_id))

@app.post('/api/tickets/{ticket_id}/review')
def review(ticket_id:str,body:Review,email=Depends(operator)):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=get_ticket(db,ticket_id)
        if row['status']!='ready' or row['version']!=body.expected_version:
            raise HTTPException(409,'This draft changed or was already reviewed. Reload it.')
        value=json.loads(row['draft'])
        value['reply']=body.reply
        value['review_required']=False
        db.execute('UPDATE tickets SET status=?,draft=?,version=version+1,updated=? WHERE id=?',
          ('approved' if body.action=='approve' else 'rejected',json.dumps(value),time.time(),ticket_id))
        event(db,'draft.'+body.action,ticket_id)
        return public(get_ticket(db,ticket_id))

@app.post('/api/tickets/{ticket_id}/retry')
def retry(ticket_id:str,email=Depends(operator)):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=get_ticket(db,ticket_id)
        if row['status']!='failed':raise HTTPException(409,'Only failed tickets can be retried.')
        db.execute("UPDATE tickets SET status='queued',attempts=0,error=NULL,updated=? WHERE id=?",(time.time(),ticket_id))
        event(db,'ticket.manually_retried',ticket_id)
    return {'ok':True}

@app.get('/api/knowledge')
def knowledge(q:str='',email=Depends(operator)):
    if len(q)>500:raise HTTPException(422,'Search is too long.')
    if q:return search(q)
    with connect() as db:return [dict(r) for r in db.execute('SELECT * FROM articles ORDER BY id')]

@app.get('/api/operations')
def operations(email=Depends(operator)):
    with connect() as db:
        counts={r['status']:r['n'] for r in db.execute('SELECT status,COUNT(*) AS n FROM tickets GROUP BY status')}
        workers=db.execute('SELECT COUNT(*) FROM workers WHERE seen>?',(time.time()-90,)).fetchone()[0]
        events=[dict(r) for r in db.execute('SELECT * FROM events ORDER BY created DESC LIMIT 50')]
    return {'counts':counts,'workers':workers,'events':events}

@app.get('/metrics')
def metrics(email=Depends(operator)):
    with connect() as db:rows=db.execute('SELECT status,COUNT(*) AS n FROM tickets GROUP BY status').fetchall()
    return Response('# TYPE supportpilot_tickets gauge\n'+'\n'.join(f'supportpilot_tickets{{status="{r["status"]}"}} {r["n"]}' for r in rows)+'\n',media_type='text/plain')

@app.get('/health/live')
def live():return {'status':'ok'}

@app.get('/health/ready')
def ready():
    with connect() as db:db.execute('SELECT 1')
    return {'status':'ready'}

@app.get('/')
def index():return FileResponse(STATIC/'index.html')
app.mount('/static',StaticFiles(directory=STATIC),name='static')
