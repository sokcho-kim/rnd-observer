import httpx
from typing import List
from src.models import Announcement


class TeamsNotifier:
    """Teams Incoming Webhook을 통한 알림 발송"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send_new_announcements(self, announcements: List[Announcement]) -> bool:
        """새 공고 목록을 Teams에 전송"""
        if not announcements:
            return True

        card = self._build_card(announcements)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.webhook_url,
                json=card,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            return response.status_code in (200, 202)

    def _build_card(self, announcements: List[Announcement]) -> dict:
        """Adaptive Card 형식으로 메시지 생성"""

        # 공고별 섹션 생성
        announcement_items = []
        for a in announcements:
            item = {
                "type": "Container",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": f"**{a.title}**",
                        "wrap": True,
                        "size": "Medium",
                    },
                    {
                        "type": "FactSet",
                        "facts": self._build_facts(a),
                    },
                    {
                        "type": "ActionSet",
                        "actions": [
                            {
                                "type": "Action.OpenUrl",
                                "title": "상세보기",
                                "url": a.url,
                            }
                        ],
                    },
                ],
                "separator": True,
                "spacing": "Medium",
            }
            announcement_items.append(item)

        # Adaptive Card 구조
        card = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": f"🦦 rndo가 새 공고 {len(announcements)}건을 발견했어요!",
                                "weight": "Bolder",
                                "size": "Large",
                                "wrap": True,
                            },
                            *announcement_items,
                        ],
                    },
                }
            ],
        }

        return card

    def _build_facts(self, a: Announcement) -> list:
        """공고 정보를 FactSet 형식으로 변환"""
        facts = [{"title": "출처", "value": a.source}]

        if a.organization:
            facts.append({"title": "주최", "value": a.organization})

        if a.deadline:
            deadline_str = a.deadline.strftime("%Y-%m-%d")
            facts.append({"title": "마감", "value": deadline_str})

        if a.status:
            facts.append({"title": "상태", "value": a.status})

        if a.prize:
            facts.append({"title": "상금", "value": a.prize})

        return facts

    async def send_simple_message(self, message: str) -> bool:
        """단순 텍스트 메시지 전송"""
        payload = {"text": message}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            return response.status_code in (200, 202)
