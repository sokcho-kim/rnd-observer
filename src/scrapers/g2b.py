"""
나라장터 (G2B) R&D 입찰공고 스크래퍼
https://www.g2b.go.kr
"""
import asyncio
import re
from datetime import datetime
from typing import List, Optional
from pathlib import Path
from playwright.async_api import async_playwright

from .base import BaseScraper
from src.models import Announcement


class G2BScraper(BaseScraper):
    """나라장터 입찰공고 스크래퍼 (Playwright)"""

    BASE_URL = "https://www.g2b.go.kr"
    # 입찰공고 검색 페이지 - 용역 (R&D 포함)
    ANNOUNCEMENTS_URL = f"{BASE_URL}/pt/menu/selectSubFrame.do?framesrc=/pt/menu/frameTgong.do?url=https://www.g2b.go.kr:8101/ep/tbid/tbidList.do?taskClCds=5"

    def __init__(self, output_dir: str = None):
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path("data/g2b")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "screenshots").mkdir(exist_ok=True)

        self.browser = None
        self.page = None
        self.context = None
        self.playwright = None

    @property
    def source_name(self) -> str:
        return "g2b"

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

    async def fetch_announcements(self) -> List[Announcement]:
        """입찰공고 목록 수집"""
        announcements = []

        try:
            # 나라장터 메인 페이지 먼저 접속
            print(f"[access] {self.BASE_URL}")
            await self.page.goto(self.BASE_URL, wait_until="networkidle", timeout=60000)
            await self.page.wait_for_timeout(2000)

            # 입찰정보 > 입찰공고 메뉴 찾기
            print("[navigate] finding bid announcement menu...")

            # 여러 방법으로 입찰공고 페이지 접근 시도
            navigated = False

            # 방법 1: 직접 URL 접근
            bid_urls = [
                "https://www.g2b.go.kr:8101/ep/tbid/tbidList.do?taskClCds=5",  # 용역
                "https://www.g2b.go.kr:8101/ep/tbid/tbidList.do",  # 전체
            ]

            for url in bid_urls:
                try:
                    print(f"[try] {url}")
                    await self.page.goto(url, wait_until="networkidle", timeout=30000)
                    await self.page.wait_for_timeout(3000)
                    content = await self.page.content()
                    if len(content) > 10000 and 'tbid' in content.lower():
                        navigated = True
                        break
                except Exception as e:
                    print(f"  [failed] {str(e)[:50]}")
                    continue

            if not navigated:
                # 방법 2: 메뉴 클릭
                try:
                    menu_selectors = [
                        'a:has-text("입찰공고")',
                        'a:has-text("입찰정보")',
                        'a[href*="tbid"]',
                    ]
                    for selector in menu_selectors:
                        link = await self.page.query_selector(selector)
                        if link:
                            await link.click()
                            await self.page.wait_for_timeout(3000)
                            navigated = True
                            break
                except:
                    pass

            await self.take_screenshot("g2b_list_page")

            # 페이지 구조 파악
            content = await self.page.content()
            print(f"[loaded] content length: {len(content)}")

            # iframe 내부 콘텐츠 확인
            frames = self.page.frames
            print(f"[frames] found {len(frames)} frames")

            target_frame = self.page
            for frame in frames:
                frame_content = await frame.content()
                if 'tbid' in frame_content.lower() or 'bidNm' in frame_content:
                    target_frame = frame
                    print(f"[frame] using frame: {frame.url[:50]}")
                    break

            # 테이블에서 공고 데이터 추출
            rows_data = await target_frame.evaluate("""
                () => {
                    const results = [];

                    // 테이블 찾기
                    const tables = document.querySelectorAll('table');
                    let dataTable = null;

                    for (let table of tables) {
                        const text = table.innerText || '';
                        if (text.includes('공고') || text.includes('입찰') || text.includes('마감')) {
                            dataTable = table;
                            break;
                        }
                    }

                    if (!dataTable) {
                        return {
                            type: 'no_table',
                            pageText: document.body.innerText.substring(0, 3000),
                            tableCount: tables.length
                        };
                    }

                    const rows = dataTable.querySelectorAll('tbody tr, tr');

                    for (let row of rows) {
                        const cells = row.querySelectorAll('td');
                        if (cells.length < 3) continue;

                        const rowText = row.innerText || '';
                        const link = row.querySelector('a');
                        const href = link ? link.getAttribute('href') : '';
                        const onclick = link ? link.getAttribute('onclick') : '';

                        const cellTexts = [];
                        for (let cell of cells) {
                            cellTexts.push((cell.innerText || '').trim());
                        }

                        results.push({
                            cellTexts,
                            href,
                            onclick,
                            rowText: rowText.substring(0, 500)
                        });
                    }

                    return {
                        type: 'table',
                        rows: results
                    };
                }
            """)

            print(f"[analyze] type: {rows_data.get('type', 'unknown')}")

            if rows_data.get('type') == 'no_table':
                print(f"[warning] no table found. tables: {rows_data.get('tableCount')}")
                safe_text = rows_data.get('pageText', '')[:500].encode('ascii', 'replace').decode('ascii')
                print(f"page text: {safe_text}")
                return []

            rows = rows_data.get('rows', [])
            print(f"[found] {len(rows)} rows")

            for idx, row in enumerate(rows):
                try:
                    cell_texts = row.get('cellTexts', [])

                    if len(cell_texts) < 3:
                        continue

                    # 헤더 행 스킵
                    if any(kw in str(cell_texts) for kw in ['업종', '공고번호', '번호', '순번']):
                        continue

                    # 공고 정보 추출
                    # 나라장터 구조: [업종, 공고번호-차수, 공고명, 공고기관, 수요기관, 계약방법, 입력일시, 입찰마감일시]
                    title = ''
                    organization = ''
                    deadline = None
                    bid_no = ''

                    for i, text in enumerate(cell_texts):
                        if not text:
                            continue

                        # 공고번호 (숫자-숫자 패턴)
                        if re.match(r'^\d+-\d+', text):
                            bid_no = text

                        # 공고명 (가장 긴 텍스트)
                        if len(text) > len(title) and len(text) > 10:
                            if not re.match(r'^\d', text) and '기관' not in text:
                                title = text

                        # 기관명
                        if any(kw in text for kw in ['청', '부', '원', '처', '시', '군', '구', '대학', '공사', '공단']):
                            if len(text) < 30 and text != title:
                                organization = text

                        # 마감일시 (YYYY/MM/DD 또는 YYYY-MM-DD)
                        date_match = re.search(r'(\d{4})[/-](\d{2})[/-](\d{2})', text)
                        if date_match:
                            try:
                                y, m, d = date_match.groups()
                                parsed_date = datetime(int(y), int(m), int(d))
                                if deadline is None or parsed_date > deadline:
                                    deadline = parsed_date
                            except:
                                pass

                    if not title or len(title) < 5:
                        continue

                    # URL 생성
                    onclick = row.get('onclick', '')
                    url = self.BASE_URL

                    if onclick and 'bidNm' in onclick:
                        # onclick에서 공고번호 추출
                        url = f"{self.BASE_URL}/ep/tbid/tbidDetail.do"

                    # ID 생성
                    announcement_id = f"g2b_{bid_no or idx}_{title[:15].replace(' ', '_')}"

                    announcement = Announcement(
                        id=announcement_id,
                        source=self.source_name,
                        title=title.strip()[:200],
                        url=url,
                        organization=organization or None,
                        deadline=deadline,
                        status="입찰중" if deadline and deadline > datetime.now() else None,
                    )
                    announcements.append(announcement)

                    safe_title = title[:40].encode('ascii', 'replace').decode('ascii')
                    print(f"  [{bid_no or idx}] {safe_title}")

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
    async with G2BScraper() as scraper:
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
