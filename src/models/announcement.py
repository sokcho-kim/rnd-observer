from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Announcement:
    """공고 기본 정보"""
    id: str
    source: str  # aifactory, iris, ntis 등
    title: str
    url: str
    organization: Optional[str] = None
    deadline: Optional[datetime] = None
    status: Optional[str] = None  # 모집중, 마감 등
    prize: Optional[str] = None  # 상금/지원금
    scraped_at: datetime = None

    def __post_init__(self):
        if self.scraped_at is None:
            self.scraped_at = datetime.now()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "organization": self.organization,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "status": self.status,
            "prize": self.prize,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
        }
