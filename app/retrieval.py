"""Lexical retrieval with SQLite FTS5/BM25. No embedding or vector-search claims."""
import re
from .db import connect

STOPWORDS={'a','an','the','i','my','me','to','of','and','is','it','in','for','this','that','can','you','please','with','have','has','was','do','on','want','need','help'}
def search(query,limit=3):
    tokens=[t for t in re.findall(r'[a-z0-9]+',query.lower()) if t not in STOPWORDS and len(t)>1][:40]
    if not tokens:return []
    expression=' OR '.join('"'+t+'"' for t in dict.fromkeys(tokens))
    with connect() as db:
        rows=db.execute("""SELECT a.*,bm25(knowledge_fts,0,3,1) AS score
            FROM knowledge_fts JOIN articles a ON a.id=knowledge_fts.id
            WHERE knowledge_fts MATCH ? ORDER BY score,a.id LIMIT ?""",(expression,limit)).fetchall()
    return [{'id':r['id'],'title':r['title'],'body':r['body'],'score':r['score']} for r in rows]

def classify(subject,body):
    text=(subject+' '+body).lower()
    categories=[
      ('security',('unauthorized','compromised','hacked','password')),
      ('billing',('charge','billing','payment','refund')),
      ('returns',('return','damaged','defective')),
      ('shipping',('shipping','delivery','tracking','address')),
      ('orders',('cancel','order')),
    ]
    category=next((c for c,words in categories if any(w in text for w in words)),'general')
    return {'category':category,'priority':'high' if category=='security' else 'normal','classifier':'deterministic_rules'}
