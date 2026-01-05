"""
rndo - R&D Observer
배치로 공고를 수집하고 Teams에 알림을 보내는 메인 모듈
"""
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Set

from src.scrapers import AifactoryScraper
from src.notifier import TeamsNotifier
from src.models import Announcement


# 이미 알린 공고 ID를 저장하는 파일
SEEN_FILE = Path(__file__).parent.parent / "data" / "seen_announcements.json"


def load_seen_ids() -> Set[str]:
    """이미 알린 공고 ID 목록 로드"""
    if not SEEN_FILE.exists():
        return set()
    with open(SEEN_FILE, "r", encoding="utf-8") as f:
        return set(json.load(f))


def save_seen_ids(seen_ids: Set[str]):
    """알린 공고 ID 목록 저장"""
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen_ids), f, ensure_ascii=False, indent=2)


def filter_new_announcements(
    announcements: List[Announcement], seen_ids: Set[str]
) -> List[Announcement]:
    """새로운 공고만 필터링"""
    return [a for a in announcements if a.id not in seen_ids]


async def run_observer():
    """메인 실행 함수"""
    # 환경변수에서 Webhook URL 가져오기
    webhook_url = os.environ.get("TEAMS_WEBHOOK_URL")
    if not webhook_url:
        print("TEAMS_WEBHOOK_URL 환경변수가 설정되지 않았습니다.")
        return

    print(f"[{datetime.now()}] rndo 시작...")

    # 이미 알린 공고 목록 로드
    seen_ids = load_seen_ids()
    print(f"이미 알린 공고: {len(seen_ids)}건")

    all_announcements = []

    # aifactory 수집
    try:
        print("aifactory 수집 중...")
        async with AifactoryScraper() as scraper:
            announcements = await scraper.fetch_announcements()
            all_announcements.extend(announcements)
            print(f"  → {len(announcements)}건 수집")
    except Exception as e:
        print(f"  → 오류: {e}")

    # TODO: IRIS 스크래퍼 추가
    # async with IrisScraper() as scraper:
    #     ...

    # 새 공고만 필터링
    new_announcements = filter_new_announcements(all_announcements, seen_ids)
    print(f"새 공고: {len(new_announcements)}건")

    if new_announcements:
        # Teams 알림 발송
        notifier = TeamsNotifier(webhook_url)
        success = await notifier.send_new_announcements(new_announcements)

        if success:
            print("Teams 알림 발송 완료!")
            # 알린 공고 ID 저장
            new_ids = {a.id for a in new_announcements}
            save_seen_ids(seen_ids | new_ids)
        else:
            print("Teams 알림 발송 실패!")
    else:
        print("새 공고가 없습니다.")

    print(f"[{datetime.now()}] rndo 종료")


def main():
    """엔트리포인트"""
    asyncio.run(run_observer())


if __name__ == "__main__":
    main()
