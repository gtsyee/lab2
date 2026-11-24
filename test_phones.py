import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, patch

from repository_layer import (
    JsonRepository, MemoryRepository, read_search_page, read_search_text,
)
from service_layer import PhoneService


class PhonePatternTests(unittest.TestCase):
    def setUp(self):
        self.service = PhoneService(MemoryRepository())

    def test_regex_accepts_supported_separators(self):
        for value in ("+1 (202) 555-0123", "8 (999) 123-45-67",
                      "0033.1.23.45.67.89", "+7\u00a0(999)\u202f123–45–67"):
            with self.subTest(value=value):
                self.assertIsNotNone(self.service.PHONE_PATTERN.fullmatch(value))

    def test_regex_rejects_invalid_syntax(self):
        for value in ("+7 (999 123-45-67", "+7 999) 123-45-67",
                      "+7\n9991234567", "номер +79991234567",
                      "+79991234567x", "+٧٩٩٩١٢٣٤٥٦٧"):
            with self.subTest(value=value):
                self.assertIsNone(self.service.PHONE_PATTERN.fullmatch(value))

    def test_normalization(self):
        cases = {
            "+44 (0)300 222 0000": "+443002220000",
            "0044 300 222 0000": "+443002220000",
            "+39 (06) 6982 1234": "+390669821234",
            "8 (999) 123-45-67": "+79991234567",
            "+370 612 34567": "+37061234567",
            "+355 69 123 4567": "+355691234567",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(self.service.validate_single_phone(value), expected)

    def test_rejects_wrong_code_length_and_national_pattern(self):
        for value in ("+99912345678", "+370 500 400 1111",
                      "+3559066991606", "+7 000 123-45-67"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.service.validate_single_phone(value)

    def test_rejects_repeated_punctuation(self):
        for value in ("+7 (999) 123--45-67", "+33.1..23.45.67.89",
                      "+7 (999) 123- .45-67"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.service.validate_single_phone(value)
                self.assertEqual(self.service.search("Номер " + value), [])

    def test_search_deduplicates_normalized_numbers(self):
        result = self.service.search("+44 (0)300 222 0000 и 00443002220000")
        self.assertEqual([phone.normalized for phone in result], ["+443002220000"])
        self.assertEqual(self.service.get_all_phones(), [])

    def test_search_skips_invalid_candidates_and_keeps_later_numbers(self):
        result = self.service.search(
            "Ошибочный +3559066991606 89121234567. Другой +79991234567 2026 год"
        )
        self.assertEqual(
            [phone.normalized for phone in result], ["+79121234567", "+79991234567"]
        )

    def test_search_does_not_extract_embedded_or_oversized_numbers(self):
        result = self.service.search("abc+79991234567xyz и +7999123456789")
        self.assertEqual(result, [])


class TextFileTests(unittest.TestCase):
    def test_reads_utf8_with_bom_and_finds_numbers_on_separate_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Контакты.txt"
            path.write_text("США: +12025550123\nЛитва: +370 612 34567", encoding="utf-8-sig")
            service = PhoneService(MemoryRepository())
            result = service.search(read_search_text(path))
            self.assertEqual(
                [phone.normalized for phone in result], ["+12025550123", "+37061234567"]
            )

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError):
                read_search_text(Path(folder) / "missing.txt")

    def test_invalid_encoding(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "contacts.txt"
            path.write_bytes(b"\xff\xfe\xff")
            with self.assertRaisesRegex(ValueError, "UTF-8"):
                read_search_text(path)


class JsonStorageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "phones.json"
        self.repo = JsonRepository(self.path)
        self.service = PhoneService(self.repo)

    def test_save_reload_delete(self):
        found = self.service.search("+12025550123, +44 (0)300 222 0000")
        self.assertFalse(self.path.exists())
        self.assertEqual(self.service.save_found(found), 2)
        reloaded = PhoneService(JsonRepository(self.path))
        self.assertEqual(reloaded.save_found(found), 0)
        reloaded.delete_phone(1)
        saved = JsonRepository(self.path).get_all()
        self.assertEqual([(p.id, p.normalized) for p in saved], [(2, "+443002220000")])

    def test_can_delete_number_saved_with_older_rules(self):
        rows = [{"id": 1, "original": "+7 000 123-45-67", "normalized": "+70001234567"}]
        self.path.write_text(json.dumps(rows), encoding="utf-8")
        reloaded = PhoneService(JsonRepository(self.path))
        self.assertEqual(reloaded.get_all_phones()[0].id, 1)
        reloaded.delete_phone(1)
        self.assertEqual(JsonRepository(self.path).get_all(), [])

    def test_corrupt_json_is_preserved(self):
        self.path.write_bytes(b"{broken")
        with self.assertRaises(ValueError):
            JsonRepository(self.path)
        self.assertEqual(self.path.read_bytes(), b"{broken")

    def test_write_error_rolls_back_add_and_delete(self):
        item = self.service.save_phone("+12025550123")
        before = self.path.read_bytes()
        with patch.object(self.repo, "_write", side_effect=OSError("write failed")):
            with self.assertRaises(OSError):
                self.service.save_phone("+37061234567")
            with self.assertRaises(OSError):
                self.service.delete_phone(item.id)
        self.assertEqual(self.service.get_all_phones(), [item])
        self.assertEqual(self.path.read_bytes(), before)


class WebPageTests(unittest.TestCase):
    def response(self, content, content_type):
        response = MagicMock()
        response.__enter__.return_value = response
        response.headers = Message()
        response.headers["Content-Type"] = content_type
        response.read.return_value = content
        return response

    def test_html_text_tel_links_and_hidden_scripts(self):
        html = """
        <p>Англия: +44&nbsp;<b>(0)300</b> 222 0000</p>
        <a href="tel:%2B12025550123">Позвонить</a>
        <script>let unused = "+37061234567";</script>
        """
        response = self.response(html.encode("utf-8"), "text/html; charset=utf-8")
        with patch("repository_layer.urlopen", return_value=response) as request:
            text = read_search_page("https://example.org/contacts")
        request.assert_called_once_with("https://example.org/contacts", timeout=10)
        service = PhoneService(MemoryRepository())
        self.assertEqual(
            [p.normalized for p in service.search(text)],
            ["+443002220000", "+12025550123"],
        )

    def test_invalid_url_is_rejected_before_request(self):
        with patch("repository_layer.urlopen") as request:
            for url in ("file:///contacts.txt", "https:///contacts", "http://bad host"):
                with self.subTest(url=url):
                    with self.assertRaises(ValueError):
                        read_search_page(url)
        request.assert_not_called()

    def test_rejects_page_over_limit(self):
        response = self.response(b"x" * 1_000_001, "text/html")
        with patch("repository_layer.urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "1 МБ"):
                read_search_page("https://example.org/contacts")

    def test_rejects_binary_content(self):
        response = self.response(b"%PDF-1.7", "application/pdf")
        with patch("repository_layer.urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "HTML"):
                read_search_page("https://example.org/contacts")


if __name__ == "__main__":
    unittest.main()
