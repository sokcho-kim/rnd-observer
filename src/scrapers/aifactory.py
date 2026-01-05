"""
aifactory.space 공모전 스크래퍼
"""
import asyncio
import re
from datetime import datetime
from typing import List, Optional
from pathlib import Path
from playwright.async_api import async_playwright

from .base import BaseScraper
from src.models import Announcement


class AifactoryScraper(BaseScraper):
    """aifactory.space 스크래퍼 (Playwright)"""

    BASE_URL = "https://aifactory.space"
    COMPETITIONS_URL = f"{BASE_URL}/competition"

    def __init__(self, output_dir: str = None):
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path("data/aifactory")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "screenshots").mkdir(exist_ok=True)

        self.browser = None
        self.page = None
        self.context = None
        self.playwright = None

    @property
    def source_name(self) -> str:
        return "aifactory"

    async def __aenter__(self):
        """컨텍스트 매니저 진입"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            slow_mo=50
        )
        self.context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        self.page = await self.context.new_page()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def take_screenshot(self, name: str):
        """스크린샷 저장"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            screenshot_path = self.output_dir / "screenshots" / f"{name}_{timestamp}.png"
            await self.page.screenshot(path=screenshot_path, full_page=True, timeout=10000)
            print(f"  [스크린샷] {screenshot_path}")
            return screenshot_path
        except Exception as e:
            print(f"  [스크린샷 스킵] {name} - {str(e)[:50]}")
            return None

    async def fetch_announcements(self) -> List[Announcement]:
        """진행중인 공모전 목록 수집"""
        announcements = []

        try:
            print(f"[접속] {self.COMPETITIONS_URL}")
            await self.page.goto(self.COMPETITIONS_URL, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_timeout(3000)

            await self.take_screenshot("competitions_page")

            # cursor-pointer 클래스가 있는 카드들에서 데이터 추출
            cards_data = await self.page.evaluate("""
                () => {
                    const results = [];
                    const cards = document.querySelectorAll('div.cursor-pointer');

                    for (let card of cards) {
                        const text = card.innerText || '';
                        const hasImg = card.querySelector('img') !== null;

                        // 이미지가 있고 적절한 길이의 텍스트를 가진 카드만
                        if (!hasImg || text.length < 20 || text.length > 500) continue;

                        // 텍스트를 줄 단위로 분리
                        const lines = text.split('\\n')
                            .map(l => l.trim())
                            .filter(l => l.length > 0);

                        if (lines.length < 3) continue;

                        // 구조 파악:
                        // lines[0]: 상태 (모집 대기중, 진행중, 종료 등)
                        // lines[1] or [2]: 제목
                        // lines[n]: 주최
                        // lines[n+1]: 상금
                        // 마지막: 날짜 (있으면)

                        let status = '';
                        let title = '';
                        let organization = '';
                        let prize = '';
                        let dateText = '';

                        // 상태 추출 (모집, 진행, 종료 키워드 포함)
                        for (let i = 0; i < Math.min(2, lines.length); i++) {
                            if (lines[i].includes('모집') || lines[i].includes('진행') || lines[i].includes('종료')) {
                                status = lines[i];
                                break;
                            }
                        }

                        // 제목 추출 (가장 긴 라인 중 하나)
                        let maxLen = 0;
                        for (let i = 0; i < lines.length; i++) {
                            const line = lines[i];
                            // 상태나 날짜가 아닌 긴 텍스트가 제목
                            if (line.length > maxLen &&
                                !line.includes('모집') &&
                                !line.includes('진행') &&
                                !line.includes('종료') &&
                                !line.match(/\\d{4}[.-]\\d{2}[.-]\\d{2}/)) {
                                title = line;
                                maxLen = line.length;
                            }
                        }

                        // 날짜 추출 (YYYY-MM-DD 또는 YYYY.MM.DD 패턴)
                        for (let line of lines) {
                            if (line.match(/\\d{4}[.-]\\d{2}[.-]\\d{2}/)) {
                                dateText = line;
                                break;
                            }
                        }

                        // 상금 추출 (원, 만원, $ 포함)
                        for (let line of lines) {
                            if (line.includes('원') || line.includes('$') || line.includes('만원')) {
                                if (line !== title) {
                                    prize = line;
                                    break;
                                }
                            }
                        }

                        // 주최 추출 (제목, 상태, 날짜, 상금이 아닌 것)
                        for (let line of lines) {
                            if (line !== title && line !== status && line !== dateText && line !== prize) {
                                if (!line.match(/\\d{4}[.-]\\d{2}[.-]\\d{2}/) &&
                                    !line.includes('원') && !line.includes('$')) {
                                    organization = line;
                                    break;
                                }
                            }
                        }

                        if (title) {
                            results.push({
                                title,
                                status,
                                organization,
                                prize,
                                dateText,
                                allLines: lines.slice(0, 5)
                            });
                        }
                    }

                    return results;
                }
            """)

            print(f"[수집] {len(cards_data)}건 발견")

            for idx, data in enumerate(cards_data):
                try:
                    title = data.get('title', '')
                    if not title:
                        continue

                    # ID 생성 (제목 기반 해시)
                    competition_id = title[:30].replace(' ', '_')

                    # 마감일 파싱
                    deadline = self._parse_date(data.get('dateText', ''))

                    announcement = Announcement(
                        id=f"aifactory_{competition_id}",
                        source=self.source_name,
                        title=title,
                        url=self.COMPETITIONS_URL,  # 개별 URL은 클릭해야 알 수 있음
                        organization=data.get('organization'),
                        deadline=deadline,
                        status=data.get('status'),
                        prize=data.get('prize'),
                    )
                    announcements.append(announcement)

                    print(f"  [{data.get('status', '?')}] {title[:50]}")

                except Exception as e:
                    print(f"  [파싱 오류] {e}")
                    continue

        except Exception as e:
            print(f"[오류] 수집 실패: {e}")
            import traceback
            traceback.print_exc()

        return announcements

    def _parse_date(self, date_text: str) -> Optional[datetime]:
        """날짜 문자열 파싱 - 마지막 날짜(마감일) 추출"""
        if not date_text:
            return None

        # 모든 날짜 패턴 찾기
        patterns = [
            r"(\d{4})-(\d{2})-(\d{2})",
            r"(\d{4})\.(\d{2})\.(\d{2})",
        ]

        dates = []
        for pattern in patterns:
            for match in re.finditer(pattern, date_text):
                try:
                    y, m, d = match.groups()
                    dates.append(datetime(int(y), int(m), int(d)))
                except ValueError:
                    continue

        # 마지막 날짜 반환 (보통 마감일)
        if dates:
            return max(dates)

        return None

    async def fetch_detail(self, announcement_id: str) -> dict:
        """공고 상세 정보 수집 (추후 구현)"""
        return {}


# 테스트용
async def main():
    async with AifactoryScraper() as scraper:
        announcements = await scraper.fetch_announcements()
        print(f"\n총 {len(announcements)}건 수집")
        for a in announcements:
            print(f"[{a.status}] {a.title}")
            print(f"  주최: {a.organization}")
            print(f"  상금: {a.prize}")
            print(f"  마감: {a.deadline}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
