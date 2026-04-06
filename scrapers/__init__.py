from .bo_scraper import BOScraper
from .cndp_scraper import CNDPScraper
from .dgssi_scraper import DGSSIScraper
from .anrt_scraper import ANRTScraper
from .sgg_scraper import SGGScraper
from .cour_cassation_scraper import CourCassationScraper

ALL_SCRAPERS = [
    BOScraper,
    CNDPScraper,
    DGSSIScraper,
    ANRTScraper,
    SGGScraper,
    CourCassationScraper,
]
