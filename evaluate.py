"""Retrieval evaluation on 12 synthetic, hand-authored cases. Not a model-quality benchmark."""
import json
from pathlib import Path
from app.db import init
from app.seed import seed
from app.retrieval import search

CASES=[
 ('Return an unused product within 30 days','KB-001'),
 ('When will my return refund reach my original payment method','KB-001'),
 ('Delayed shipping tracking has not updated','KB-002'),
 ('Standard shipping delivery time','KB-002'),
 ('Product arrived damaged I need a replacement','KB-003'),
 ('My account was compromised after an unauthorized login','KB-004'),
 ('How do I reset my password and enable two-factor authentication','KB-004'),
 ('Duplicate payment charges on my order','KB-005'),
 ('Payment authorization hold on billing statement','KB-005'),
 ('Cancel my order before dispatch','KB-006'),
 ('Change my delivery address before dispatch','KB-007'),
 ('Discount code error during checkout','KB-008'),
]
def evaluate():
 rows=[]
 for query,expected in CASES:
  hits=search(query,3)
  ids=[h['id'] for h in hits]
  rows.append({'query':query,'expected':expected,'retrieved':ids,'hit_at_1':ids[:1]==[expected],'hit_at_3':expected in ids})
 return {'cases':len(rows),'hit_rate_at_1':sum(r['hit_at_1'] for r in rows)/len(rows),'recall_at_3':sum(r['hit_at_3'] for r in rows)/len(rows),'scope':'Synthetic lexical retrieval cases only; not LLM answer accuracy.','results':rows}
if __name__=='__main__':
 init();seed()
 result=evaluate()
 path=Path('docs/retrieval-evaluation.json')
 path.write_text(json.dumps(result,indent=2))
 print(json.dumps({k:v for k,v in result.items() if k!='results'},indent=2))
