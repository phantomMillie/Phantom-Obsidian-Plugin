#!/usr/bin/env python3
"""Read actual Codex usage for an explicit session/thread; never estimate savings."""
import argparse,json,os,pathlib,sys

def usage(path):
 latest=None
 with path.open(encoding='utf-8') as f:
  for line in f:
   try:row=json.loads(line)
   except ValueError:continue
   payload=row.get('payload',{})
   if payload.get('type')=='token_count':
    info=payload.get('info') or {}
    if isinstance(info.get('total_token_usage'),dict):latest=info['total_token_usage']
 if latest is None:raise ValueError('No measured token_count event in this session')
 return latest

def resolve(thread,sessions):
 matches=[]
 for path in sessions.rglob('*.jsonl'):
  if thread not in path.name:continue
  with path.open(encoding='utf-8') as f:
   for _,line in zip(range(10),f):
    try:row=json.loads(line)
    except ValueError:continue
    if row.get('type')=='session_meta' and row.get('payload',{}).get('id')==thread:matches.append(path);break
 if len(matches)!=1:raise ValueError('Cannot identify exactly one session for current thread; supply --session explicitly')
 return matches[0]

def main():
 p=argparse.ArgumentParser();p.add_argument('--session',type=pathlib.Path);p.add_argument('--thread',default=os.environ.get('CODEX_THREAD_ID'));a=p.parse_args()
 if a.session:path=a.session.expanduser()
 elif a.thread:path=resolve(a.thread,pathlib.Path(os.environ.get('CODEX_HOME',str(pathlib.Path.home()/'.codex')))/'sessions')
 else:raise ValueError('Current Codex thread id unavailable; provide the exact --session path. Do not substitute the newest session.')
 print(json.dumps({'session':str(path),'measured_token_usage':usage(path),'savings':'unavailable: no paired baseline'},ensure_ascii=False,indent=2))
if __name__=='__main__':
 try:main()
 except (OSError,ValueError) as exc:sys.exit(str(exc))
