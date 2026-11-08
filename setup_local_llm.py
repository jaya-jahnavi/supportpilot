"""Checksum-pinned official assets, downloaded inside .local without OS installation."""
import hashlib
from pathlib import Path
import platform
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parent/'.local/runtime'
ASSETS=[
 ('llama.zip','https://github.com/ggml-org/llama.cpp/releases/download/b12194/llama-b12194-bin-win-cpu-x64.zip','7d9f589fc8e78564e4a8e30349f1707ff4ec8b7c899db16f5b5260f096297dd6'),
 ('qwen2.5-0.5b-instruct-q4_k_m.gguf','https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf','74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db'),
]
def digest(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def setup():
 ROOT.mkdir(parents=True,exist_ok=True)
 for name,url,expected in ASSETS:
  if name=='llama.zip' and platform.system()!='Windows':continue
  path=ROOT/name
  if not path.exists() or digest(path)!=expected:
   print('Downloading '+name,flush=True)
   with urllib.request.urlopen(url,timeout=120) as response,path.open('wb') as stream:
    while chunk:=response.read(1024*1024):stream.write(chunk)
  if digest(path)!=expected:raise RuntimeError('Checksum mismatch: '+name)
  if name.endswith('.zip'):
   target=(ROOT/'llama').resolve()
   with zipfile.ZipFile(path) as archive:
    for member in archive.infolist():
     if not (target/member.filename).resolve().is_relative_to(target):raise RuntimeError('Unsafe archive member.')
    archive.extractall(target)
 print('Model ready in .local/runtime. Windows native runtime is included on Windows.')
if __name__=='__main__':setup()
