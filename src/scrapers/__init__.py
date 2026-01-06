from .aifactory import AifactoryScraper
from .base import BaseScraper
from .ntis import NtisScraper
from .iris import IrisScraper
from .g2b import G2BScraper
from .bizinfo import BizinfoScraper
from .kstartup import KStartupScraper

__all__ = [
    "BaseScraper",
    # 작동하는 스크래퍼
    "AifactoryScraper",  # 공모전 (aifactory.space)
    "NtisScraper",       # 국가R&D (ntis.go.kr)
    "BizinfoScraper",    # 기업마당 (bizinfo.go.kr)
    "KStartupScraper",   # K-Startup (k-startup.go.kr)
    # 미작동 (참고용)
    "IrisScraper",       # IRIS - 로그인 필요
    "G2BScraper",        # 나라장터 - 접속 불가
]
