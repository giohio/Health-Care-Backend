from abc import ABC, abstractmethod


class IFileStorage(ABC):
    @abstractmethod
    def save(self, data: bytes, original_filename: str, subfolder: str = "") -> tuple[str, int]:
        raise NotImplementedError