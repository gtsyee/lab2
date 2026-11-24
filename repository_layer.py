from abc import ABC, abstractmethod
from html.parser import HTMLParser
from http.client import HTTPException
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen


MAX_PAGE_BYTES = 1_000_000


class PhonePageParser(HTMLParser):
    BLOCK_TAGS = {
        "address", "article", "aside", "br", "div", "footer", "h1", "h2",
        "h3", "header", "li", "main", "p", "section", "table", "td", "tr",
    }

    def __init__(self):
        super().__init__()
        self.parts = []
        self.links = []
        self.hidden = None

    def handle_starttag(self, tag, attrs):
        if self.hidden:
            return
        if tag in ("script", "style"):
            self.hidden = tag
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "a":
            href = dict(attrs).get("href") or ""
            if href.lower().startswith("tel:"):
                self.links.append(unquote(href[4:]))

    def handle_endtag(self, tag):
        if self.hidden == tag:
            self.hidden = None
        if not self.hidden and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

    def get_text(self):
        return "\n".join(["".join(self.parts), *self.links])


def read_search_text(path):
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("текстовый файл должен быть в кодировке UTF-8") from error


def read_search_page(url):
    if any(char.isspace() for char in url):
        raise ValueError("URL не должен содержать пробелы")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("укажите полный URL с http:// или https://")
    try:
        with urlopen(url, timeout=10) as response:
            content_type = response.headers.get_content_type()
            encoding = response.headers.get_content_charset() or "utf-8-sig"
            content = response.read(MAX_PAGE_BYTES + 1)
    except HTTPException as error:
        raise ValueError(f"ошибка HTTP: {error}") from error
    if len(content) > MAX_PAGE_BYTES:
        raise ValueError("размер страницы превышает 1 МБ")
    is_html = content_type in ("text/html", "application/xhtml+xml")
    if not is_html and not content_type.startswith("text/"):
        raise ValueError("ожидается HTML-страница или текст")
    try:
        text = content.decode(encoding, errors="replace")
    except LookupError as error:
        raise ValueError(f"неизвестная кодировка страницы: {encoding}") from error
    if is_html:
        parser = PhonePageParser()
        parser.feed(text)
        parser.close()
        return parser.get_text()
    return text


class Repository(ABC):
    @abstractmethod
    def add(self, item):
        pass
    @abstractmethod
    def get(self, item_id):
        pass
    @abstractmethod
    def get_all(self):
        pass
    @abstractmethod
    def update(self, item):
        pass
    @abstractmethod
    def delete(self, item_id):
        pass
class MemoryRepository(Repository):
    def __init__(self):
        self._items = {}
        self._next_id = 1
    def add(self, item):
        if item.id is not None:
            raise ValueError("объект уже был сохранен")    
        item.id = self._next_id
        self._items[item.id] = item
        self._next_id += 1
        return item
    def get(self, item_id):
        if item_id not in self._items:
            raise ValueError(f"объект с id {item_id} не найден")
        return self._items[item_id]
    def get_all(self):
        return list(self._items.values())
    def update(self, item):
        self.get(item.id)
        self._items[item.id] = item
        return item
    def delete(self, item_id):
        self.get(item_id)
        del self._items[item_id]

class JsonRepository(MemoryRepository):
    def __init__(self, path):
        super().__init__()
        import json
        from data_layer import PhoneNumber
        import re
        self.path = Path(path)
        if not self.path.exists():
            return
        rows = json.loads(self.path.read_text(encoding="utf-8-sig"))
        if not isinstance(rows, list):
            raise ValueError("в JSON ожидается список номеров")
        normalized = set()
        for row in rows:
            if (not isinstance(row, dict)
                    or set(row) != {"id", "original", "normalized"}
                    or type(row["id"]) is not int or row["id"] < 1
                    or row["id"] in self._items
                    or not isinstance(row["original"], str)
                    or not isinstance(row["normalized"], str)
                    or not re.fullmatch(r"\+[1-9][0-9]{1,14}", row["normalized"])
                    or row["normalized"] in normalized):
                raise ValueError("неверная запись в JSON")
            phone = PhoneNumber(row["original"], row["normalized"])
            phone.id = row["id"]
            self._items[phone.id] = phone
            normalized.add(phone.normalized)
        self._next_id = max(self._items, default=0) + 1

    def _write(self):
        import json
        import os
        from tempfile import NamedTemporaryFile
        temp_path = None
        try:
            with NamedTemporaryFile(mode="w", encoding="utf-8",
                                    dir=self.path.parent, delete=False) as file:
                temp_path = file.name
                json.dump([vars(p) for p in self.get_all()], file,
                          ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(temp_path, self.path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    def add(self, item):
        old_id = self._next_id
        super().add(item)
        try:
            self._write()
        except OSError:
            del self._items[item.id]
            item.id = None
            self._next_id = old_id
            raise
        return item

    def delete(self, item_id):
        item = self.get(item_id)
        super().delete(item_id)
        try:
            self._write()
        except OSError:
            self._items[item_id] = item
            raise

    def update(self, item):
        old = self.get(item.id)
        super().update(item)
        try:
            self._write()
        except OSError:
            self._items[item.id] = old
            raise
        return item
