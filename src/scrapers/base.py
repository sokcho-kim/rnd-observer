from abc import ABC, abstractmethod
from typing import List
from src.models import Announcement


class BaseScraper(ABC):
    """스크래퍼 베이스 클래스"""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """소스 이름 (aifactory, iris 등)"""
        pass

    @abstractmethod
    async def fetch_announcements(self) -> List[Announcement]:
        """공고 목록 수집"""
        pass

    @abstractmethod
    async def fetch_detail(self, announcement_id: str) -> dict:
        """공고 상세 정보 수집"""
        pass
