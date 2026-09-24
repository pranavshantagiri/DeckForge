"""Image providers: real photography by default, AI generation optional+off.

Every returned image carries attribution so decks can include a caption/footer
line. Local photo library support (CLIP-style index) is added in Phase 1E.
"""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path

from pydantic import BaseModel, Field

from deckforge_core.errors import ImageError
from deckforge_core.providers.base import Provider


class ImageItem(BaseModel):
    id: str
    provider: str
    url: str
    thumb_url: str = ""
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    license: str = ""
    attribution: str = ""  # "Photo by X on Unsplash"
    page_url: str = ""
    alt: str = ""
    color: str = ""  # dominant average colour of the thumb, "#rrggbb"


class ImageProvider(Provider):
    provider_type = "image"

    @abstractmethod
    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        min_width: int = 800,
        min_height: int = 600,
        orientation: str = "landscape",
    ) -> list[ImageItem]:
        """Search for real photos. Reject low-res by default."""

    @abstractmethod
    def fetch(self, item: ImageItem, dest: Path) -> Path:
        """Download the image to ``dest`` (a file path). Returns the path."""

    def fetch_thumbnail(self, item: ImageItem, dest: Path) -> Path:
        try:
            return self.fetch(
                ImageItem(
                    **item.model_dump(),
                    url=item.thumb_url or item.url,
                ),
                dest,
            )
        except Exception as exc:
            raise ImageError(f"thumbnail fetch failed for {item.id}") from exc
