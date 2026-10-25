#!/usr/bin/env python3
"""Codex-native, read-only Millie reminders. Never bootstrap apps or modify a vault."""
import json,os,pathlib,subprocess,sys

def context(data):
 event=data.get('hook_event_name','')
 if event not in ('SessionStart','UserPromptSubmit'):return ''
 home=pathlib.Path(os.environ.get('MILLIE_HOME',str(pathlib.Path(__file__).resolve().parents[2]))).expanduser()
 cfg_path=home/'config.json'
 if not cfg_path.is_file():return ''
 cfg=json.loads(cfg_path.read_text());vault=pathlib.Path(cfg['vault']).expanduser()
 # Vault instructions precede reading vault contents, including linting.
 rules=vault/'AGENTS.md'
 if not rules.is_file():return ''
 rules.read_text(encoding='utf-8')
 script=home/'plugin/scripts/project_lint.py'
 if not script.is_file():return ''
 result=subprocess.run([sys.executable,str(script),'--json','--vault',str(vault)],capture_output=True,text=True,timeout=6)
 if result.returncode:return ''
 rows=json.loads(result.stdout);bad=[r for r in rows if r.get('missing')]
 if event=='UserPromptSubmit':
  prompt=data.get('prompt','')
  if not isinstance(prompt,str):return ''
  bad=[r for r in bad if r['project'] in prompt]
  if not bad:return ''
 lines=[]
 if event=='SessionStart':
  lines += ['Millie Obsidian: 기존 전역 AGENTS.md와 vault/AGENTS.md를 따른다. 완료한 작업은 vault-record로 기록한다. 이 훅은 점검만 하며 앱 설치·vault 생성·수정을 실행하지 않는다.']
 for r in bad:
  lines.append('프로젝트 '+r['project']+': '+', '.join(r['missing'])+' 미설정. 해당 프로젝트 작업 때만 한 줄로 알리고 /obsidian-project-scope를 제안한다. 날짜·완료 조건을 지어내지 않는다.')
 if bad:lines.append('목록은 훅 실행 시점의 상태다. 실제 판단 전에 원문을 다시 확인한다.')
 return '\n'.join(lines)[:6000]

def main():
 try:
  data=json.load(sys.stdin)
  if not isinstance(data,dict):raise ValueError('input must be an object')
  text=context(data)
  out={'hookSpecificOutput':{'hookEventName':data['hook_event_name'],'additionalContext':text}} if text else {}
  print(json.dumps(out,ensure_ascii=False))
 except Exception as exc:
  print('Millie Codex hook skipped: '+type(exc).__name__,file=sys.stderr)
  print('{}')
if __name__=='__main__':main()
