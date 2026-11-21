import os
from typing import Dict, Any
from ..services.douyin_client import DouyinScraper

class IngestionAgent:
    """
    Agent 1: Handles video ingestion from Douyin, TikTok, YouTube, or direct links.
    """
    def __init__(self):
        self.scraper = DouyinScraper()

    def run(self, url: str, output_path: str) -> Dict[str, Any]:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        saved_file = self.scraper.download_video(url, output_path)
        file_size = os.path.getsize(saved_file)
        return {
            "success": True,
            "video_path": saved_file,
            "file_size": file_size
        }
