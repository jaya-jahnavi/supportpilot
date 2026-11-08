"""Synthetic policies and explicit local demo credentials."""
import json
import secrets
from .db import DATA,connect,init
from .security import password_hash

ARTICLES=[
('KB-001','Returns and refunds','Unused products may be returned within 30 days of delivery. Request a return authorization using the order number. Refunds go to the original payment method within 5 to 10 business days after the return inspection.'),
('KB-002','Delayed shipping and tracking','Standard shipping takes 3 to 5 business days. Tracking updates may take 24 hours to appear. If a shipment is delayed, verify the delivery address and carrier tracking number, then ask the support team to investigate. Do not promise a delivery date.'),
('KB-003','Damaged or defective products','For a damaged or defective item, request the order number and a photograph of the damage. The support team reviews replacement or refund eligibility. Do not guarantee a refund or a replacement before review.'),
('KB-004','Account security and password reset','If an account is compromised or has an unauthorized login, use the password reset page and enable two-factor authentication. Escalate to the security team. Never request passwords, authentication codes, or payment card numbers.'),
('KB-005','Duplicate charges and billing','For a duplicate payment charge, request the order number and the dates of the charges. Authorization holds may appear temporarily. The billing team verifies posted charges before any reversal. Never request full credit card details.'),
('KB-006','Order cancellation','Order cancellation is available before dispatch. Ask for the order number and check the shipment status. Dispatched orders follow the returns process. Never confirm a cancellation until the order system verifies it.'),
('KB-007','Change delivery address','Address changes are available before dispatch. Ask for the order number and the updated delivery address through the approved secure channel. Once dispatched, ask the carrier about rerouting; availability is not guaranteed.'),
('KB-008','Promotions and discount codes','Discount codes must be valid and applied during checkout. A code cannot be combined with another promotion unless the promotion explicitly allows it. Ask for the code and any checkout error message. Do not invent discounts.'),
]
def seed():
    init()
    with connect() as db:
        for article in ARTICLES:
            if not db.execute('SELECT 1 FROM articles WHERE id=?',(article[0],)).fetchone():
                db.execute('INSERT INTO articles VALUES(?,?,?)',article)
                db.execute('INSERT INTO knowledge_fts VALUES(?,?,?)',article)
        if not db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            account={'email':'operator@example.test','password':secrets.token_urlsafe(18)}
            db.execute('INSERT INTO users VALUES(?,?)',(account['email'],password_hash(account['password'])))
            (DATA/'demo-credentials.json').write_text(json.dumps(account,indent=2))
            print('Demo credentials saved in .local/demo-credentials.json')
        else:print('Existing account kept. Policies are available.')
if __name__=='__main__':seed()
