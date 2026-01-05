"""aifactory 페이지 구조 디버깅 - 카드 정보 추출"""
import asyncio
from playwright.async_api import async_playwright


async def debug():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('https://aifactory.space/competition', wait_until='networkidle')
        await page.wait_for_timeout(3000)

        # 카드 셀렉터로 모든 카드 찾기
        result = await page.evaluate("""
            () => {
                const cards = [];
                // cursor-pointer가 있는 div들 (카드)
                const cardEls = document.querySelectorAll('div.cursor-pointer');

                for (let card of cardEls) {
                    const text = card.innerText || '';
                    const hasImg = card.querySelector('img') !== null;

                    // 적절한 크기의 카드만
                    if (hasImg && text.length > 20 && text.length < 500) {
                        // 텍스트를 줄 단위로 분리
                        const lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 0);

                        // 링크 찾기 (onclick 또는 data 속성)
                        const onclick = card.getAttribute('onclick') || '';
                        const dataId = card.getAttribute('data-id') || card.getAttribute('data-task-id') || '';

                        cards.push({
                            lines: lines.slice(0, 8),
                            onclick: onclick.substring(0, 100),
                            dataId: dataId,
                            className: (card.className || '').substring(0, 60)
                        });
                    }
                }

                return cards.slice(0, 5);
            }
        """)

        print(f"Cards found: {len(result)}")
        for i, item in enumerate(result):
            print(f"\n--- Card {i+1} ---")
            print(f"  Class: {item['className'][:50]}")
            print(f"  Lines: {item['lines']}")
            if item['onclick']:
                print(f"  Onclick: {item['onclick']}")
            if item['dataId']:
                print(f"  DataId: {item['dataId']}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(debug())
