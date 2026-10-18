

from typing import Protocol

from fastapi import UploadFile


class FileSystem(Protocol):
    def upload_file(self, file: UploadFile, path: str) -> str:
        ...


class LocalFileSystem:
    def upload_file(self, file: UploadFile, path: str) -> str:
        with open(path, "wb") as f:
            f.write(file.file.read())
        return path
