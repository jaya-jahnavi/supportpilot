import hashlib
import hmac
import secrets

def password_hash(value):
    salt=secrets.token_bytes(16)
    digest=hashlib.scrypt(value.encode(),salt=salt,n=16384,r=8,p=1)
    return salt.hex()+':'+digest.hex()

def verify(value,stored):
    salt,digest=stored.split(':')
    actual=hashlib.scrypt(value.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
    return hmac.compare_digest(actual,digest)
