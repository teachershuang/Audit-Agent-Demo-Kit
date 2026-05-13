from __future__ import annotations

from abc import ABC, abstractmethod


class BaseTool(ABC):
    name: str = "base_tool"

    @abstractmethod
    def run(self):
        raise NotImplementedError
