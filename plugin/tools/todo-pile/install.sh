#!/bin/bash
# TODO Pile 빌드 + 로그인 시 자동 실행(LaunchAgent). 되돌리기: ./install.sh --uninstall
set -e
cd "$(dirname "$0")"
LABEL=com.millie.todo-pile
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
if [ "$1" = "--uninstall" ]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"; echo "제거 완료"; exit 0
fi
mkdir -p bin && swiftc -O Pile.swift -o bin/todo-pile -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist -Xlinker Info.plist   # Info.plist = 마이크 사용 설명
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$PWD/bin/todo-pile</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null && sleep 2 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "설치 완료 — 바탕화면에 깔림. 메뉴바 'TODO' 에서 할 일 목록 · 추가 · 보이기 켜고 끄기"
