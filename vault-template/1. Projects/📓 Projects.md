---
type: dashboard
created: 2026-04-22
tags: [dashboard]
---

# 🗂 Projects Overview

> 현재 집중 중인 프로젝트는 3개 이하로 유지
> 완료된 프로젝트는 Archive로 이동

---

## 🧵 진행현황

```dataviewjs
const pages = dv.pages('"1. Projects"')
  .where(p => p.type === "project");

let rows = [];

for (let p of pages) {
  const text = await dv.io.load(p.file.path);

  // 배포월 — 프론트매터(created)에 오염되지 않게 배포 섹션 안에서만 날짜를 찾는다
  const releaseSection = text.match(/##\s*📆[^\n]*\n([\s\S]*?)(?=\n##\s|$)/);
  const dateMatch = (releaseSection ? releaseSection[1] : "").match(/(\d{4})-(\d{2})-\d{2}/);
  const releaseMonth = (dateMatch && dateMatch[1] !== "9999") ? ` (${dateMatch[2]}월)` : "";

  // 진행률 — 세부 목표 섹션 우선, 없으면 목표 섹션의 체크박스로 대체
  const pickSection = (emoji, name) => {
    const m = text.match(new RegExp(`##\\s*${emoji}\\s*${name}[^\\n]*\\n([\\s\\S]*?)(?=\\n##\\s|$)`));
    return m ? m[1] : "";
  };
  const section = pickSection("📋", "세부 목표") || pickSection("🎯", "목표");

  // 체크박스 줄을 통째로 잡아 템플릿 자리표시를 걸러낸다.
  // (`- [ ] 세부 목표` 3줄이 분모로 잡히면 진행률이 영원히 0% 다)
  const PLACEHOLDER = [
    /^세부\s*목표\s*\d*$/, /^이 프로젝트의 최종 목표는 무엇인가\?$/,
    /^목표\s*\d*$/, /^날짜\s*[:：]/, /^배포\s*버전$/, /^이력$/,
    /^오늘\/내일 해야 할 일$/, /^요청할 사람$/, /^결정해야 할 사항$/,
    /^$/,
  ];
  const lines = section.match(/^\s*- \[[ xX]\].*$/gm) || [];
  const boxes = lines.filter(ln => {
    const body = ln.replace(/^\s*- \[[ xX]\]\s*/, "").replace(/\*\*/g, "").trim();
    return !PLACEHOLDER.some(re => re.test(body));
  });
  const total = boxes.length;
  const done = boxes.filter(b => /- \[[xX]\]/.test(b)).length;

  const rate = total ? Math.round(100 * done / total) : 0;
  const lastUpdated = p.file.mtime.toFormat("yyyy-MM-dd");
  const projectLinkWithMonth = `${dv.fileLink(p.file.path, false, p.project)}${releaseMonth}`;

  // 분모가 없는(=세부 목표 미작성) 프로젝트는 0% 가 아니라 미설정으로 보여준다.
  // `/obsidian-project-scope <프로젝트>` 로 분모를 확정하면 채워진다.
  // 필수 3종 — 완료 조건 · 마일스톤(날짜) · 완료일(due). 비면 로그·회의·작업 때마다 리마인드된다 (.scripts/project_lint.py)
  const sec = (h) => { const m = text.match(new RegExp(`##\\s*${h}[^\\n]*\\n([\\s\\S]*?)(?=\\n##\\s|$)`)); return m ? m[1] : ""; };
  const hasItem = (b) => b.split("\n").some(l => { const t = l.trim(); if (!t || t.startsWith(">") || t.startsWith("---")) return false; return t.replace(/^[-*]\s*(\[[ xX]\]\s*)?/, "").replace(/\*\*/g, "").trim() !== ""; });
  const hasDated = (b) => b.split("\n").some(l => /\d{4}-\d{2}-\d{2}/.test(l) && !/9999-/.test(l));
  const need = [];
  if (!hasItem(sec("✅ 완료 조건"))) need.push("완료조건");
  if (!hasDated(sec("🏁 마일스톤"))) need.push("마일스톤");
  if (!p.due || String(p.due).startsWith("9999")) need.push("완료일");

  rows.push([
    projectLinkWithMonth,
    lastUpdated,
    total || "—",
    total ? done : "—",
    total ? rate + "%" : "⚠️ 분모 미설정",
    need.length ? "⚠️ 없음: " + need.join("·") : (p.due ? "✅ ~" + String(p.due).slice(0, 10) : "✅")
  ]);
}

rows.sort((a, b) => (a[4] === "⚠️ 분모 미설정" ? -1 : 0) - (b[4] === "⚠️ 분모 미설정" ? -1 : 0));

dv.table(["프로젝트", "수정일", "전체", "완료", "진행률", "필수 항목"], rows);
```

---

## 🚨 이슈 현황

```dataviewjs
const pages = dv.pages('"1. Projects"').where(p => p.type === "issues");
let rows = [];

for (let p of pages) {
  const text = await dv.io.load(p.file.path);

  const countUnchecked = (section) => {
    const match = text.match(new RegExp(`## ${section}([\\s\\S]*?)(?=\\n---|\n## |$)`));
    if (!match) return 0;
    return (match[1].match(/- \[ \] .+/g) || []).length;
  };

  rows.push([
    dv.fileLink(p.file.path, false, p.project),
    countUnchecked("프로젝트 이슈"),
    countUnchecked("정책 이슈"),
    countUnchecked("일정 이슈"),
  ]);
}

dv.table(["프로젝트", "프로젝트 이슈", "정책 이슈", "일정 이슈"], rows);
```

---

## 📅 회의록

### 프로젝트별
```dataview
TABLE rows.file.link AS "회의록", rows.date AS "날짜"
FROM "3. Resources/01. Meeting"
WHERE project != "" AND project != null
GROUP BY project
```

### 팀 미팅
```dataview
TABLE file.link AS "제목", date AS "날짜"
FROM "3. Resources/01. Meeting"
WHERE contains(tags, "meeting/team") OR project = "" OR project = null
SORT date DESC
```
