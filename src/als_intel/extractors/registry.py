from __future__ import annotations

from typing import Callable

from als_intel.extractors.base import DataSourceExtractor, UnsupportedExtractorError


class ExtractorRegistry:
    _factories: dict[str, Callable[[], DataSourceExtractor]] = {}

    @classmethod
    def register(cls, source_name: str, factory: Callable[[], DataSourceExtractor]) -> None:
        cls._factories[source_name.strip().lower()] = factory

    @classmethod
    def create(cls, source_name: str) -> DataSourceExtractor:
        key = source_name.strip().lower()
        factory = cls._factories.get(key)
        if factory is None:
            supported = ", ".join(sorted(cls._factories))
            raise UnsupportedExtractorError(f"Unsupported source: {source_name}. Supported: {supported}")
        return factory()

    @classmethod
    def supported_sources(cls) -> list[str]:
        return sorted(cls._factories.keys())
