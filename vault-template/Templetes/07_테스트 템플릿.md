<%*
/*
 * Dynamic Test Template
 * This script sets the file name based on user input or date.
 */

// 사용자로부터 테스트 제목을 입력받습니다.
const userTitle = await tp.system.prompt("테스트 노트의 제목을 입력해주세요:", `${tp.date.now("yyyy년 MM월 DD일")} Test`);

// 파일명이 비어있지 않으면, 입력한 제목을 사용하고, 비어있으면 현재 날짜를 사용합니다.
const title = userTitle && userTitle.trim() !== "" ? userTitle : `${tp.date.now("yyyy년 MM월 DD일")} Test`;

// 파일명을 설정합니다.
await tp.file.rename(title);
const vaultName = tp.app.vault.adapter.basePath.split(/\/|\\/).pop();

// YAML 메타데이터 설정
tR += `---
title: ${title}
date: ${tp.date.now("yyyy-MM-DD")}
project: ${vaultName}
tags: [Test]
---
## 테스트 개요
- **테스트 목적**:
- **관련 API/기획 문서**: 

## 테스트 케이스 목록

### 테스트 케이스
- **목표**:
- **사전 조건**:
- **단계**:
  1. 
  2. 
  3. 
- **예상 결과**:
- **실제 결과**:
- **수정 요청**:
- **상태**: 
- [ ] 완료

### 테스트 케이스
- **목표**:
- **사전 조건**:
- **단계**:
  1. 
  2. 
  3. 
- **예상 결과**:
- **실제 결과**:
- **수정 요청**:
- **상태**: 
- [ ] 완료

### 테스트 케이스
- **목표**:
- **사전 조건**:
- **단계**:
  1. 
  2. 
  3. 
- **예상 결과**:
- **실제 결과**:
- **수정 요청**:
- **상태**: 
- [ ] 완료

### 테스트 케이스
- **목표**:
- **사전 조건**:
- **단계**:
  1. 
  2. 
  3. 
- **예상 결과**:
- **실제 결과**:
- **수정 요청**:
- **상태**: 
- [ ] 완료
`;
%>