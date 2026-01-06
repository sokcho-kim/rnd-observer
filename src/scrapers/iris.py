"""
IRIS (범부처통합연구지원시스템) R&D 과제공고 스크래퍼
https://www.iris.go.kr
"""
import asyncio
import re
from datetime import datetime
from typing import List, Optional
from pathlib import Path
from playwright.async_api import async_playwright

from .base import BaseScraper
from src.models import Announcement


class IrisScraper(BaseScraper):
    """IRIS 과제공고 스크래퍼 (Playwright)"""

    BASE_URL = "https://www.iris.go.kr"
    # 과제공고 목록 페이지 - 여러 URL 패턴 시도
    ANNOUNCEMENTS_URLS = [
        f"{BASE_URL}/anmt/anmtList.do",  # 공고목록
        f"{BASE_URL}/contents/retrieveBsnsAncmList.do",
        f"{BASE_URL}/bsnsAnmt/retrieveBsnsAnmtList.do",
    ]
    ANNOUNCEMENTS_URL = ANNOUNCEMENTS_URLS[0]

    def __init__(self, output_dir: str = None):
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path("data/iris")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "screenshots").mkdir(exist_ok=True)

        self.browser = None
        self.page = None
        self.context = None
        self.playwright = None

    @property
    def source_name(self) -> str:
        return "iris"

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
        """진행중인 과제공고 목록 수집"""
        announcements = []

        try:
            # 먼저 메인 페이지 접속
            print(f"[접속] {self.BASE_URL}/main.do")
            await self.page.goto(f"{self.BASE_URL}/main.do", wait_until="networkidle", timeout=60000)
            await self.page.wait_for_timeout(2000)
            await self.take_screenshot("iris_main")

            # 과제공고 메뉴 찾기 및 클릭
            print("[탐색] 과제공고 메뉴 찾는 중...")

            # 여러 패턴으로 공고 링크 찾기
            link_selectors = [
                'a:has-text("과제공고")',
                'a:has-text("사업공고")',
                'a:has-text("공고")',
                'a[href*="anmt"]',
                'a[href*="ancm"]',
                'a[href*="Ancm"]',
            ]

            clicked = False
            for selector in link_selectors:
                try:
                    link = await self.page.query_selector(selector)
                    if link:
                        print(f"  [발견] {selector}")
                        await link.click()
                        await self.page.wait_for_timeout(3000)
                        clicked = True
                        break
                except:
                    continue

            if not clicked:
                # 직접 URL 시도
                for url in self.ANNOUNCEMENTS_URLS:
                    try:
                        print(f"[시도] {url}")
                        await self.page.goto(url, wait_until="networkidle", timeout=30000)
                        await self.page.wait_for_timeout(2000)
                        # 에러 페이지가 아닌지 확인
                        content = await self.page.content()
                        if "장애" not in content and len(content) > 5000:
                            break
                    except:
                        continue

            await self.take_screenshot("iris_list_page")

            # 페이지 구조 파악을 위해 HTML 확인
            content = await self.page.content()
            print(f"[페이지 로드] 콘텐츠 길이: {len(content)}")

            # 테이블 또는 리스트 형태의 공고 목록 찾기
            # IRIS는 보통 테이블 형태로 공고를 표시함
            rows_data = await self.page.evaluate("""
                () => {
                    const results = [];

                    // 테이블 행 찾기 (여러 패턴 시도)
                    const selectors = [
                        'table tbody tr',
                        '.board-list tbody tr',
                        '.list-table tbody tr',
                        'table.list tr',
                        '.tb_list tr',
                        'tr[onclick]',
                        '.announcement-item',
                        '.ancm-list li'
                    ];

                    let rows = [];
                    for (let selector of selectors) {
                        const found = document.querySelectorAll(selector);
                        if (found.length > 0) {
                            rows = found;
                            console.log('Found rows with selector:', selector, found.length);
                            break;
                        }
                    }

                    // 테이블이 없으면 페이지 전체 텍스트 분석
                    if (rows.length === 0) {
                        return {
                            type: 'no_table',
                            pageText: document.body.innerText.substring(0, 5000),
                            html: document.body.innerHTML.substring(0, 10000)
                        };
                    }

                    for (let row of rows) {
                        const cells = row.querySelectorAll('td');
                        if (cells.length < 2) continue;

                        const rowText = row.innerText;
                        const link = row.querySelector('a');
                        const href = link ? link.getAttribute('href') : '';
                        const onclick = row.getAttribute('onclick') || '';

                        // 각 셀의 텍스트 추출
                        const cellTexts = [];
                        for (let cell of cells) {
                            cellTexts.push(cell.innerText.trim());
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

            print(f"[분석] 결과 타입: {rows_data.get('type', 'unknown')}")

            if rows_data.get('type') == 'no_table':
                print("[경고] 테이블을 찾지 못함. 페이지 구조 확인 필요")
                print(f"페이지 텍스트 샘플:\n{rows_data.get('pageText', '')[:1000]}")
                # HTML 구조 저장
                html_path = self.output_dir / "page_structure.html"
                html_path.write_text(rows_data.get('html', ''), encoding='utf-8')
                print(f"[저장] HTML 구조 → {html_path}")
                return []

            rows = rows_data.get('rows', [])
            print(f"[수집] {len(rows)}건 발견")

            for idx, row in enumerate(rows):
                try:
                    cell_texts = row.get('cellTexts', [])
                    if len(cell_texts) < 2:
                        continue

                    # 공고 정보 추출 (IRIS 테이블 구조에 맞게 조정 필요)
                    # 일반적인 구조: [번호, 부처, 공고명, 접수기간, 상태 등]
                    title = ''
                    organization = ''
                    deadline = None
                    status = ''

                    for i, text in enumerate(cell_texts):
                        # 제목 찾기 (가장 긴 텍스트)
                        if len(text) > len(title) and not text.isdigit():
                            if not any(kw in text for kw in ['접수', '마감', '진행', '종료']):
                                title = text

                        # 부처/기관 찾기
                        if any(kw in text for kw in ['부', '청', '원', '처', '위원회', '재단', '진흥']):
                            if len(text) < 30:
                                organization = text

                        # 상태 찾기
                        if any(kw in text for kw in ['접수중', '접수예정', '마감', '진행중', '종료']):
                            status = text

                        # 날짜 찾기
                        date_match = re.search(r'(\d{4})[.-](\d{2})[.-](\d{2})', text)
                        if date_match:
                            try:
                                y, m, d = date_match.groups()
                                deadline = datetime(int(y), int(m), int(d))
                            except:
                                pass

                    if not title or len(title) < 5:
                        continue

                    # URL 생성
                    href = row.get('href', '')
                    onclick = row.get('onclick', '')

                    url = self.ANNOUNCEMENTS_URL
                    if href and href.startswith('http'):
                        url = href
                    elif href and href.startswith('/'):
                        url = f"{self.BASE_URL}{href}"
                    elif 'ancmId' in onclick:
                        # onclick에서 ancmId 추출
                        ancm_match = re.search(r"ancmId['\"]?\s*[,:=]\s*['\"]?(\w+)", onclick)
                        if ancm_match:
                            url = f"{self.BASE_URL}/contents/retrieveBsnsAncmView.do?ancmId={ancm_match.group(1)}"

                    # ID 생성
                    announcement_id = f"iris_{title[:30].replace(' ', '_')}_{idx}"

                    announcement = Announcement(
                        id=announcement_id,
                        source=self.source_name,
                        title=title.strip(),
                        url=url,
                        organization=organization or None,
                        deadline=deadline,
                        status=status or None,
                    )
                    announcements.append(announcement)
                    print(f"  [{status or '?'}] {title[:50]}")

                except Exception as e:
                    print(f"  [파싱 오류] {e}")
                    continue

        except Exception as e:
            print(f"[오류] 수집 실패: {e}")
            import traceback
            traceback.print_exc()
            await self.take_screenshot("error_page")

        return announcements

    async def fetch_detail(self, announcement_id: str) -> dict:
        """공고 상세 정보 수집 (추후 구현)"""
        return {}


# 테스트용
async def main():
    async with IrisScraper() as scraper:
        announcements = await scraper.fetch_announcements()
        print(f"\n총 {len(announcements)}건 수집")
        for a in announcements[:10]:  # 처음 10개만 출력
            print(f"[{a.status}] {a.title}")
            print(f"  기관: {a.organization}")
            print(f"  마감: {a.deadline}")
            print(f"  URL: {a.url}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
