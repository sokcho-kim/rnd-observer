"""
K-Startup 창업/R&D 공고 스크래퍼
https://www.k-startup.go.kr
"""
import asyncio
import re
from datetime import datetime, timedelta
from typing import List, Optional
from pathlib import Path
from playwright.async_api import async_playwright

from .base import BaseScraper
from src.models import Announcement


class KStartupScraper(BaseScraper):
    """K-Startup 공고 스크래퍼 (Playwright)"""

    BASE_URL = "https://www.k-startup.go.kr"
    # 진행중인 사업공고 페이지
    ANNOUNCEMENTS_URL = f"{BASE_URL}/web/contents/bizpbanc-ongoing.do"

    def __init__(self, output_dir: str = None):
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path("data/kstartup")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "screenshots").mkdir(exist_ok=True)

        self.browser = None
        self.page = None
        self.context = None
        self.playwright = None

    @property
    def source_name(self) -> str:
        return "kstartup"

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

    async def fetch_announcements(self, year: int = None) -> List[Announcement]:
        """진행중인 사업공고 수집

        Args:
            year: 특정 연도 공고만 필터링 (기본: 올해)
        """
        if year is None:
            year = datetime.now().year

        announcements = []

        try:
            print(f"[access] {self.ANNOUNCEMENTS_URL}")
            print(f"[filter] year = {year}")

            await self.page.goto(self.ANNOUNCEMENTS_URL, wait_until="networkidle", timeout=60000)
            await self.page.wait_for_timeout(3000)

            # 스크롤해서 더 많은 데이터 로드 (Lazy Loading 대응)
            for _ in range(3):
                await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await self.page.wait_for_timeout(1500)

            await self.take_screenshot("kstartup_list_page")

            # 리스트에서 공고 데이터 추출
            items_data = await self.page.evaluate("""
                () => {
                    const results = [];

                    // 여러 셀렉터 시도
                    const selectors = [
                        'ul.list li',
                        '.board-list li',
                        '.pbanc-list li',
                        'li[onclick]',
                        '.list-item',
                        'div.item',
                        'ul li a[href*="go_view"]',
                        'li'
                    ];

                    let items = [];
                    let usedSelector = '';

                    for (let selector of selectors) {
                        const found = document.querySelectorAll(selector);
                        // 공고처럼 보이는 항목만 필터링
                        const validItems = Array.from(found).filter(el => {
                            const text = el.innerText || '';
                            return text.length > 30 && (
                                text.includes('공고') ||
                                text.includes('모집') ||
                                text.includes('D-') ||
                                text.includes('마감')
                            );
                        });

                        if (validItems.length > 0) {
                            items = validItems;
                            usedSelector = selector;
                            break;
                        }
                    }

                    if (items.length === 0) {
                        return {
                            type: 'no_items',
                            pageText: document.body.innerText.substring(0, 3000)
                        };
                    }

                    for (let item of items) {
                        const text = item.innerText || '';
                        const link = item.querySelector('a');
                        const href = link ? link.getAttribute('href') : '';
                        const onclick = item.getAttribute('onclick') || (link ? link.getAttribute('onclick') : '');

                        // pbancSn 추출
                        let pbancSn = '';
                        const snMatch = (onclick + href).match(/go_view\((\d+)\)/);
                        if (snMatch) {
                            pbancSn = snMatch[1];
                        }

                        results.push({
                            text: text.substring(0, 500),
                            href,
                            onclick,
                            pbancSn
                        });
                    }

                    return {
                        type: 'items',
                        items: results,
                        selector: usedSelector
                    };
                }
            """)

            print(f"[analyze] type: {items_data.get('type', 'unknown')}")

            if items_data.get('type') == 'no_items':
                print("[warning] no items found")
                safe_text = items_data.get('pageText', '')[:500].encode('ascii', 'replace').decode('ascii')
                print(f"page text: {safe_text}")
                return []

            items = items_data.get('items', [])
            print(f"[found] {len(items)} items (selector: {items_data.get('selector', '?')})")

            for idx, item in enumerate(items):
                try:
                    text = item.get('text', '')
                    lines = [l.strip() for l in text.split('\n') if l.strip()]

                    if len(lines) < 2:
                        continue

                    # 공고 정보 추출
                    title = ''
                    organization = ''
                    deadline = None
                    d_day = ''

                    for line in lines:
                        # D-day 찾기
                        d_match = re.search(r'D-(\d+)', line)
                        if d_match:
                            d_day = f"D-{d_match.group(1)}"
                            days = int(d_match.group(1))
                            deadline = datetime.now() + timedelta(days=days)

                        # 제목 (가장 긴 라인)
                        if len(line) > len(title) and len(line) > 10:
                            if not re.match(r'^D-\d+$', line) and not line.isdigit():
                                if '조회' not in line and '스크랩' not in line:
                                    title = line

                        # 기관명 (짧은 텍스트 중 기관 키워드 포함)
                        if any(kw in line for kw in ['부', '청', '원', '처', '진흥', '재단', '센터']):
                            if len(line) < 30 and line != title:
                                organization = line

                    if not title or len(title) < 5:
                        continue

                    # 연도 필터링
                    title_year_match = re.search(r'(20\d{2})년?', title)
                    if title_year_match:
                        title_year = int(title_year_match.group(1))
                        if title_year != year:
                            continue

                    # URL 생성
                    pbancSn = item.get('pbancSn', '')
                    url = self.ANNOUNCEMENTS_URL
                    if pbancSn:
                        url = f"{self.BASE_URL}/web/contents/bizpbanc-detail.do?pbancSn={pbancSn}"

                    # ID 생성
                    announcement_id = f"kstartup_{pbancSn or idx}_{title[:15].replace(' ', '_')}"

                    announcement = Announcement(
                        id=announcement_id,
                        source=self.source_name,
                        title=title.strip()[:200],
                        url=url,
                        organization=organization or None,
                        deadline=deadline,
                        status=d_day or "진행중",
                    )
                    announcements.append(announcement)

                    safe_title = title[:40].encode('ascii', 'replace').decode('ascii')
                    print(f"  [{d_day or '?'}] {safe_title}")

                except Exception as e:
                    print(f"  [parse error] {e}")
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
    async with KStartupScraper() as scraper:
        announcements = await scraper.fetch_announcements()
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
