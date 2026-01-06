"""
기업마당 (bizinfo.go.kr) R&D/지원사업 공고 스크래퍼
중소벤처기업부·지자체·부처 전체의 공모·사업 공고 통합 포털
"""
import asyncio
import re
from datetime import datetime
from typing import List, Optional
from pathlib import Path
from playwright.async_api import async_playwright

from .base import BaseScraper
from src.models import Announcement


class BizinfoScraper(BaseScraper):
    """기업마당 공고 스크래퍼 (Playwright)"""

    BASE_URL = "https://www.bizinfo.go.kr"
    # 지원사업 공고 목록
    ANNOUNCEMENTS_URL = f"{BASE_URL}/web/lay1/bbs/S1T122C128/AS/74/list.do"

    def __init__(self, output_dir: str = None):
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path("data/bizinfo")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "screenshots").mkdir(exist_ok=True)

        self.browser = None
        self.page = None
        self.context = None
        self.playwright = None

    @property
    def source_name(self) -> str:
        return "bizinfo"

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
            print(f"  [screenshot] {screenshot_path}")
            return screenshot_path
        except Exception as e:
            print(f"  [screenshot skip] {name} - {str(e)[:50]}")
            return None

    async def fetch_announcements(self, year: int = None, max_pages: int = 3) -> List[Announcement]:
        """지원사업 공고 목록 수집

        Args:
            year: 특정 연도 공고만 필터링 (기본: 올해)
            max_pages: 최대 페이지 수 (기본: 3)
        """
        if year is None:
            year = datetime.now().year

        announcements = []

        try:
            print(f"[access] {self.ANNOUNCEMENTS_URL}")
            print(f"[filter] year = {year}, max_pages = {max_pages}")

            await self.page.goto(self.ANNOUNCEMENTS_URL, wait_until="networkidle", timeout=60000)
            await self.page.wait_for_timeout(2000)

            await self.take_screenshot("bizinfo_list_page")

            # 페이지별 수집
            for page_num in range(1, max_pages + 1):
                if page_num > 1:
                    # 페이지 이동
                    try:
                        await self.page.click(f'a:has-text("{page_num}")')
                        await self.page.wait_for_timeout(2000)
                    except:
                        print(f"[warning] page {page_num} not found")
                        break

                print(f"[page {page_num}] fetching...")

                # 테이블에서 공고 데이터 추출
                rows_data = await self.page.evaluate("""
                    () => {
                        const results = [];
                        const rows = document.querySelectorAll('table tbody tr');

                        for (let row of rows) {
                            const cells = row.querySelectorAll('td');
                            if (cells.length < 5) continue;

                            const link = row.querySelector('a');
                            const href = link ? link.getAttribute('href') : '';

                            const cellTexts = [];
                            for (let cell of cells) {
                                cellTexts.push((cell.innerText || '').trim());
                            }

                            // 테이블 구조: [번호, 지원분야, 지원사업명, 신청기간, 소관부처, 사업수행기관, 등록일, 조회수]
                            results.push({
                                no: cellTexts[0] || '',
                                category: cellTexts[1] || '',
                                title: cellTexts[2] || '',
                                period: cellTexts[3] || '',
                                department: cellTexts[4] || '',
                                agency: cellTexts[5] || '',
                                regDate: cellTexts[6] || '',
                                views: cellTexts[7] || '',
                                href: href
                            });
                        }

                        return results;
                    }
                """)

                print(f"  [found] {len(rows_data)} rows")

                for row in rows_data:
                    try:
                        title = row.get('title', '')
                        if not title or len(title) < 5:
                            continue

                        # 연도 필터링
                        title_year_match = re.search(r'(20\d{2})년?', title)
                        if title_year_match:
                            title_year = int(title_year_match.group(1))
                            if title_year != year:
                                continue

                        # 신청기간에서 마감일 추출
                        period = row.get('period', '')
                        deadline = None
                        if '~' in period:
                            dates = re.findall(r'(\d{4})-(\d{2})-(\d{2})', period)
                            if dates:
                                try:
                                    last_date = dates[-1]
                                    deadline = datetime(int(last_date[0]), int(last_date[1]), int(last_date[2]))
                                except:
                                    pass

                        # URL 생성
                        href = row.get('href', '')
                        url = self.ANNOUNCEMENTS_URL
                        if href:
                            if href.startswith('http'):
                                url = href
                            elif href.startswith('/'):
                                url = f"{self.BASE_URL}{href}"
                            elif 'pblancId' in href:
                                url = f"{self.BASE_URL}/web/lay1/bbs/S1T122C128/AS/74/{href}"

                        # 상태 판단
                        status = None
                        if deadline:
                            if deadline >= datetime.now():
                                status = "접수중"
                            else:
                                status = "마감"

                        # ID 생성
                        no = row.get('no', '')
                        announcement_id = f"bizinfo_{no}_{title[:15].replace(' ', '_')}"

                        announcement = Announcement(
                            id=announcement_id,
                            source=self.source_name,
                            title=title.strip()[:200],
                            url=url,
                            organization=row.get('department') or row.get('agency') or None,
                            deadline=deadline,
                            status=status,
                        )
                        announcements.append(announcement)

                        safe_title = title[:40].encode('ascii', 'replace').decode('ascii')
                        print(f"    [{status or '?'}] {safe_title}")

                    except Exception as e:
                        print(f"    [parse error] {e}")
                        continue

        except Exception as e:
            print(f"[error] fetch failed: {e}")
            import traceback
            traceback.print_exc()
            await self.take_screenshot("error_page")

        return announcements

    async def fetch_detail(self, announcement_id: str) -> dict:
        """공고 상세 정보 수집 (추후 구현)"""
        return {}


# 테스트용
async def main():
    async with BizinfoScraper() as scraper:
        announcements = await scraper.fetch_announcements(max_pages=2)
        print(f"\ntotal: {len(announcements)}")
        for a in announcements[:10]:
            safe_title = a.title[:50].encode('ascii', 'replace').decode('ascii')
            safe_org = (a.organization or '').encode('ascii', 'replace').decode('ascii')
            print(f"[{a.status}] {safe_title}")
            print(f"  org: {safe_org}")
            print(f"  deadline: {a.deadline}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
