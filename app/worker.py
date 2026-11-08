import json
import logging
import signal
import time
import uuid
from .db import connect,event,init
from .retrieval import search,classify
from .llm import draft

LEASE=60
MAX_ATTEMPTS=2
STOP=False
WORKER=str(uuid.uuid4())
log=logging.getLogger('supportpilot.worker')

def once():
    now=time.time()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT OR REPLACE INTO workers VALUES(?,?)',(WORKER,now))
        expired=db.execute("SELECT id,attempts FROM tickets WHERE status='running' AND lease_until<?",(now,)).fetchall()
        for row in expired:
            status='failed' if row['attempts']>=MAX_ATTEMPTS else 'queued'
            db.execute('UPDATE tickets SET status=?,error=?,updated=? WHERE id=?',(status,'Previous worker lease expired.',now,row['id']))
            event(db,'ticket.recovered',row['id'])
        row=db.execute("SELECT * FROM tickets WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
        if not row:return False
        ticket=dict(row)
        token=str(uuid.uuid4())
        db.execute("UPDATE tickets SET status='running',attempts=attempts+1,worker=?,lease_until=?,updated=? WHERE id=?",(token,now+LEASE,now,ticket['id']))
        event(db,'ticket.started',ticket['id'])
    start=time.monotonic()
    try:
        classification=classify(ticket['subject'],ticket['body'])
        sources=search(ticket['subject']+' '+ticket['body'])
        generated=draft(ticket['subject'],ticket['body'],sources)
        result={**classification,**generated,'sources':sources,'review_required':True}
        trace=[{'step':'classify_ticket','method':'rules','category':classification['category']},
          {'step':'search_knowledge','method':'FTS5/BM25','source_ids':[s['id'] for s in sources]},
          {'step':'generate_draft','mode':generated['mode'],'model':generated['model'],'prompt_version':generated['prompt_version'],'seconds':round(time.monotonic()-start,3)}]
        now=time.time()
        with connect() as db:
            changed=db.execute("""UPDATE tickets SET status='ready',draft=?,trace=?,updated=?,
                version=version+1,error=NULL WHERE id=? AND worker=? AND status='running' AND lease_until>?""",
                (json.dumps(result,allow_nan=False),json.dumps(trace),now,ticket['id'],token,now)).rowcount
            if changed:event(db,'draft.ready',ticket['id'])
    except Exception as exc:
        log.exception('generation_failed ticket=%s',ticket['id'])
        with connect() as db:
            now=time.time()
            status='failed' if ticket['attempts']+1>=MAX_ATTEMPTS else 'queued'
            changed=db.execute("""UPDATE tickets SET status=?,error=?,updated=? WHERE id=?
                AND worker=? AND status='running' AND lease_until>?""",
                (status,'Generation failed. Check provider availability and worker logs.',now,ticket['id'],token,now)).rowcount
            if changed:event(db,'draft.'+status,ticket['id'])
    return True

def stop(*_):
    global STOP
    STOP=True
if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    init()
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    while not STOP:
        try:
            if not once():time.sleep(.5)
        except Exception:
            log.exception('worker_poll_failed')
            time.sleep(1)
