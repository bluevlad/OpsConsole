# GitHub Bridge 설정 (P2)

> OpsConsole 변경요청 폼 → 각 서비스 GitHub 레포 Issue 자동 발급, PR 머지/이슈 종료 시 상태 자동 동기화.

---

## 0. 개념

```
┌──────────────┐                                ┌────────────────┐
│ 운영자(폼)    │ POST /api/change-requests      │ FastAPI        │
│              ├───────────────────────────────►│ (PAT 으로      │
└──────────────┘                                │  Issue 생성)   │
                                                └────────┬───────┘
                                                         │ POST /repos/{owner}/{repo}/issues
                                                         ▼
                                                ┌────────────────┐
                                                │ AllergyInsight │
                                                │ GitHub repo    │◄── 개발자가 PR 작성
                                                │  Issue #N      │    body: "Closes #N"
                                                └────────┬───────┘
                                                         │ webhook (HMAC)
                                                         ▼
                                                ┌────────────────┐
                                                │ FastAPI        │
                                                │ /api/github/   │
                                                │  webhook       │ → ops_change_requests.status 갱신
                                                └────────────────┘
```

---

## 1. .env 환경변수

```bash
# repo:read + issues:write 권한이 있는 PAT (또는 GitHub App)
GITHUB_PAT=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxx

# webhook 검증용 시크릿 (각 레포 webhook 등록 시 동일 값 입력)
GITHUB_WEBHOOK_SECRET=long-random-string-shared-with-github
```

비밀번호 생성 예:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 2. GitHub PAT 발급

### Fine-grained PAT (권장)

1. https://github.com/settings/tokens?type=beta
2. Resource owner: `bluevlad` (organization)
3. Repository access: 매니페스트가 등록된 레포 선택 (예: `AllergyInsight`)
4. Permissions:
   - **Issues**: Read and Write
   - **Contents**: Read-only (매니페스트 fetch 용)
   - **Metadata**: Read-only (자동)
5. 생성 후 토큰을 `.env` 의 `GITHUB_PAT` 에 붙여넣기

### Classic PAT (대안)

scope: `repo` (전체) 또는 `public_repo`. 단 권한 범위가 넓어 fine-grained 보다 비권장.

---

## 3. 각 서비스 레포에 라벨 사전 생성

OpsConsole 이 발급하는 Issue 에 자동 부여되는 라벨. 미리 만들어 두면 Issue 작성 시 즉시 색상 적용.

```bash
# AllergyInsight 예시 (gh CLI 사용)
gh label create "from:ops-console"  --repo bluevlad/AllergyInsight --color "5b8bff"
gh label create "priority:urgent"   --repo bluevlad/AllergyInsight --color "e25b5b"
gh label create "priority:high"     --repo bluevlad/AllergyInsight --color "e7a948"
gh label create "priority:normal"   --repo bluevlad/AllergyInsight --color "8a90a3"
gh label create "priority:low"      --repo bluevlad/AllergyInsight --color "3ec78d"

# 매니페스트의 11개 섹션 코드별
for sec in ai-consult ai-insight analytics insight-report allergy-report \
           newsletter wiki professional consumer admin drug-management; do
  gh label create "section:$sec" --repo bluevlad/AllergyInsight --color "1d2230"
done
```

---

## 4. Webhook 등록

각 서비스 레포 (예: `bluevlad/AllergyInsight`) 의 Settings → Webhooks → Add webhook:

| 항목 | 값 |
|------|------|
| Payload URL | `https://opsconsole.unmong.com/api/github/webhook` |
| Content type | `application/json` |
| Secret | `.env` 의 `GITHUB_WEBHOOK_SECRET` 와 동일 |
| SSL verification | Enable |
| Which events | Let me select individual events → ✅ **Issues**, ✅ **Pull requests** |

저장 후 GitHub 가 자동으로 ping 이벤트 발송. OpsConsole 이 200 + `{"status":"pong"}` 응답하면 정상.

---

## 5. 동작 흐름

### 5.1 변경요청 발급

1. 운영자가 OpsConsole `/services/{code}/sections/{section}` 페이지에서 **+ 새 변경요청** 클릭
2. 제목 / 본문 / 우선순위 입력 후 제출
3. POST `/api/change-requests`:
   - `ops_change_requests` row 생성 (status='submitted')
   - `service.repo_url` 보유 + `GITHUB_PAT` 설정 시 → GitHub Issue 자동 생성
     - Title: `[ops:{section_code}] {제목}`
     - Body: 섹션 메타 + 자산 + 본문 + Closes 안내
     - Labels: `from:ops-console`, `section:{code}`, `priority:{level}`
   - `cr.github_issue_number`, `cr.github_issue_url` 저장
   - audit log + change_request_event 기록

### 5.2 PR 작성·머지 (개발자)

개발자가 일반 GitHub workflow 로 작업 → PR 본문에 `Closes #ISSUE_NUMBER` 포함:

```markdown
## Summary
배너 문구를 친근한 어투로 변경

Closes #42
```

### 5.3 webhook 자동 동기화

- **PR opened**: 매칭된 변경요청 → `status='in_pr'`, `github_pr_number`/`github_pr_url` 저장
- **PR closed (merged=true)**: `status='merged'`, `closed_at` 기록
- **PR closed (merged=false)**: `status='submitted'` 로 되돌림 (대기)
- **Issue closed (PR 없이 직접 종료)**: `status='closed'`
- **Issue reopened**: `status='submitted'`

idempotency: `X-GitHub-Delivery` 헤더가 이미 처리된 경우 noop.

---

## 6. 트러블슈팅

| 증상 | 원인 / 조치 |
|------|------------|
| `GITHUB_PAT 미설정 — Issue 발급/조회 불가` | `.env` 에 PAT 추가 후 컨테이너 재시작 |
| Issue 생성 후에도 OpsConsole 상태가 안 바뀜 | 1) Webhook 등록 확인, 2) Webhook secret 일치 확인, 3) Recent Deliveries 의 Response 확인 (401 = HMAC 실패) |
| `401 invalid X-Hub-Signature-256` | `.env` 의 `GITHUB_WEBHOOK_SECRET` 가 GitHub 측 webhook secret 과 다름 |
| PR 머지했는데 status 가 in_pr 그대로 | PR body 에 `Closes #ISSUE_NUMBER` 키워드 없음. 수동으로 `/api/change-requests/{id}` PATCH 또는 PR body 수정 후 webhook redeliver |
| 라벨이 자동 부여되지 않음 | 라벨이 GitHub 측에 사전 생성되어 있어야 함. §3 참조 |

---

## 7. 보안 노트

- **PAT 권한 최소화**: fine-grained PAT 로 issues:write 만 필요한 레포에 한정
- **Webhook secret 회전**: 정기적으로 교체. 변경 시 `.env` + GitHub Webhook 양쪽 동시 갱신
- **idempotency**: `X-GitHub-Delivery` 가 같으면 noop. 같은 페이로드를 여러 번 redeliver 해도 안전
- **운영자 권한**: 변경요청 생성은 모든 인증 사용자 가능. status 변경 (`submitted` → `rejected` 등) 은 ops_admin 만
