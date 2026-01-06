"""
NTIS (국가과학기술지식정보서비스) R&D 과제공고 스크래퍼
https://www.ntis.go.kr
"""
import asyncio
import re
from datetime import datetime
from typing import List, Optional
from pathlib import Path
from playwright.async_api import async_playwright

from .base import BaseScraper
from src.models import Announcement


class NtisScraper(BaseScraper):
    """NTIS 과제공고 스크래퍼 (Playwright)"""

    BASE_URL = "https://www.ntis.go.kr"
    # 국가R&D 통합공고 페이지
    ANNOUNCEMENTS_URL = f"{BASE_URL}/rndgate/eg/un/ra/mng.do"

    def __init__(self, output_dir: str = None):
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path("data/ntis")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "screenshots").mkdir(exist_ok=True)

        self.browser = None
        self.page = None
        self.context = None
        self.playwright = None

    @property
    def source_name(self) -> str:
        return "ntis"

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
        """진행중인 과제공고 목록 수집

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

            await self.take_screenshot("ntis_list_page")

            # 페이지 구조 파악
            content = await self.page.content()
            print(f"[loaded] content length: {len(content)}")

            # 테이블 또는 리스트에서 공고 데이터 추출
            rows_data = await self.page.evaluate("""
                () => {
                    const results = [];

                    // 여러 테이블 셀렉터 시도
                    const selectors = [
                        'table tbody tr',
                        '.board-list tbody tr',
                        '.list-table tbody tr',
                        'table.list tr',
                        '.tb_list tr',
                        'tr[onclick]',
                        '.data-list li',
                        '.announcement-item',
                        'ul.list li',
                        'div.list-item'
                    ];

                    let rows = [];
                    let usedSelector = '';
                    for (let selector of selectors) {
                        const found = document.querySelectorAll(selector);
                        if (found.length > 0) {
                            rows = found;
                            usedSelector = selector;
                            break;
                        }
                    }

                    if (rows.length === 0) {
                        // 테이블이 없으면 페이지 구조 반환
                        return {
                            type: 'no_table',
                            pageText: document.body.innerText.substring(0, 3000),
                            tables: document.querySelectorAll('table').length,
                            divs: document.querySelectorAll('div').length
                        };
                    }

                    for (let row of rows) {
                        const cells = row.querySelectorAll('td, div.cell');
                        const rowText = row.innerText || '';
                        const link = row.querySelector('a');
                        const href = link ? link.getAttribute('href') : '';
                        const onclick = row.getAttribute('onclick') || (link ? link.getAttribute('onclick') : '');

                        const cellTexts = [];
                        for (let cell of cells) {
                            cellTexts.push((cell.innerText || '').trim());
                        }

                        if (cellTexts.length > 0 || rowText.length > 10) {
                            results.push({
                                cellTexts,
                                href,
                                onclick,
                                rowText: rowText.substring(0, 500),
                                selector: usedSelector
                            });
                        }
                    }

                    return {
                        type: 'table',
                        rows: results,
                        selector: usedSelector
                    };
                }
            """)

            print(f"[analyze] type: {rows_data.get('type', 'unknown')}")

            if rows_data.get('type') == 'no_table':
                print(f"[warning] no table found. tables: {rows_data.get('tables')}, divs: {rows_data.get('divs')}")
                # 페이지 텍스트 일부 출력 (인코딩 안전하게)
                page_text = rows_data.get('pageText', '')
                safe_text = page_text.encode('ascii', 'replace').decode('ascii')[:500]
                print(f"page text sample: {safe_text}")
                return []

            rows = rows_data.get('rows', [])
            print(f"[found] {len(rows)} rows (selector: {rows_data.get('selector', '?')})")

            for idx, row in enumerate(rows):
                try:
                    cell_texts = row.get('cellTexts', [])
                    row_text = row.get('rowText', '')

                    # 헤더 행 스킵
                    if not cell_texts and not row_text:
                        continue
                    if any(kw in str(cell_texts) for kw in ['번호', '제목', '공고명', 'No', '순번']):
                        continue

                    # 공고 정보 추출
                    title = ''
                    organization = ''
                    deadline = None
                    status = ''
                    period = ''

                    # 셀 텍스트에서 정보 추출
                    all_text = ' '.join(cell_texts) if cell_texts else row_text

                    for text in cell_texts:
                        if not text:
                            continue

                        # 제목 (가장 긴 텍스트)
                        if len(text) > len(title) and len(text) > 10:
                            if not any(kw in text for kw in ['접수', '마감', '종료', '부', '청', '원']):
                                if not re.match(r'^\d+$', text):  # 숫자만 있는 건 스킵
                                    title = text

                        # 부처/기관
                        if any(kw in text for kw in ['부', '청', '원', '처', '위원회', '재단', '진흥', '연구']):
                            if len(text) < 50 and not title == text:
                                organization = text

                        # 상태
                        if any(kw in text for kw in ['접수중', '접수예정', '마감', '진행', '종료', '공고중']):
                            status = text

                        # 기간 (날짜 범위)
                        if '~' in text or '-' in text:
                            date_match = re.search(r'(\d{4}[.-]\d{2}[.-]\d{2})', text)
                            if date_match:
                                period = text

                    # 마감일 추출
                    if period:
                        dates = re.findall(r'(\d{4})[.-](\d{2})[.-](\d{2})', period)
                        if dates:
                            try:
                                last_date = dates[-1]
                                deadline = datetime(int(last_date[0]), int(last_date[1]), int(last_date[2]))
                            except:
                                pass

                    if not title or len(title) < 5:
                        continue

                    # 연도 필터링 - 제목에 연도가 있으면 체크
                    title_year_match = re.search(r'(20\d{2})년?', title)
                    if title_year_match:
                        title_year = int(title_year_match.group(1))
                        if title_year != year:
                            continue  # 다른 연도 공고 스킵

                    # URL 생성
                    href = row.get('href', '')
                    onclick = row.get('onclick', '')

                    url = self.ANNOUNCEMENTS_URL
                    if href and href.startswith('http'):
                        url = href
                    elif href and href.startswith('/'):
                        url = f"{self.BASE_URL}{href}"

                    # ID 생성
                    announcement_id = f"ntis_{idx}_{title[:20].replace(' ', '_')}"

                    announcement = Announcement(
                        id=announcement_id,
                        source=self.source_name,
                        title=title.strip()[:200],
                        url=url,
                        organization=organization or None,
                        deadline=deadline,
                        status=status or None,
                    )
                    announcements.append(announcement)

                    # 출력 (인코딩 안전하게)
                    safe_title = title[:40].encode('ascii', 'replace').decode('ascii')
                    print(f"  [{status or '?'}] {safe_title}")

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
    async with NtisScraper() as scraper:
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
