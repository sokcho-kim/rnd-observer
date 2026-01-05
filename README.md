# rndo (린도) - R&D Observer

> 미어캣처럼 R&D 공모전을 감시하고 알려주는 봇

## 개요

- 공모전 사이트(aifactory, IRIS 등)를 주기적으로 스크래핑
- 새 공고 발견 시 Teams 채널에 자동 알림
- Azure Functions로 서버리스 배포

## 구조

```
rnd-observer/
├── src/
│   ├── scrapers/       # 사이트별 스크래퍼
│   ├── notifier/       # Teams 알림
│   ├── models/         # 데이터 모델
│   └── main.py         # 메인 로직
├── function_app.py     # Azure Functions 엔트리
├── requirements.txt
└── host.json
```

## 설정

### 1. Teams Webhook 설정

1. Teams 채널 > ... > 커넥터
2. Incoming Webhook 추가
3. 이름: `rndo`, 아이콘: 미어캣
4. URL 복사

### 2. 환경변수

```bash
# local.settings.json 또는 Azure 설정
TEAMS_WEBHOOK_URL=https://your-tenant.webhook.office.com/...
```

### 3. 로컬 실행

```bash
pip install -r requirements.txt
python -m src.main
```

### 4. Azure 배포

```bash
func azure functionapp publish <앱이름>
```

## 스케줄

- 기본: 매일 9시, 18시 (KST)
- 수정: `function_app.py`의 schedule 파라미터

## 향후 계획

- [ ] IRIS 스크래퍼 추가
- [ ] @rndo 호출 시 상세 분석 보고서
- [ ] 주제 추천 기능
