import json
import re
from pathlib import Path
from data_layer import PhoneNumber
from repository_layer import Repository


def check_text(text, field):
    if not isinstance(text, str):
        raise TypeError(f"{field} должно быть строкой")
    if not text.strip():
        raise ValueError(f"{field} не должно быть пустым")


class PhoneService:
    SPACES = r"[ \t\u00a0\u202f\u2009]"
    PUNCTUATION = r"[.\-\u2010-\u2014]"
    SEPARATORS = rf"(?:{SPACES}|{PUNCTUATION})"
    REPEATED_PUNCTUATION = re.compile(rf"{PUNCTUATION}{SPACES}*{PUNCTUATION}")
    PHONE_PATTERN = re.compile(
        r'(?<![\w+])(?:\+[1-9][0-9]*|00[1-9][0-9]*|8[0-9]*)'
        rf'(?:{SEPARATORS}+[0-9]+|{SPACES}*\('
        rf'{SPACES}*[0-9]{{1,6}}{SPACES}*\)|(?<=\))[0-9]+)*'
        r'(?![\w+])'
    )

    def __init__(self, phones: Repository, codes_path=None):
        self.phones = phones
        path = codes_path or Path(__file__).with_name("country_codes.json")
        self.codes = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(self.codes, dict) or not self.codes:
            raise ValueError("неверный справочник кодов стран")
        for code, rule in self.codes.items():
            if (not re.fullmatch(r"[1-9][0-9]{0,2}", code)
                    or not isinstance(rule, dict)
                    or not isinstance(rule.get("lengths"), list)
                    or not rule["lengths"]
                    or rule.get("optional_trunk_prefix", "0") != "0"
                    or any(type(n) is not int or not 1 <= n <= 15 - len(code)
                           for n in rule["lengths"])):
                raise ValueError("неверное правило кода страны")
            patterns = rule.get("patterns", [])
            if not isinstance(patterns, list) or any(
                not isinstance(pattern, str) for pattern in patterns
            ):
                raise ValueError("неверные шаблоны кода страны")
            for pattern in patterns:
                try:
                    re.compile(pattern)
                except re.error as error:
                    raise ValueError("ошибка шаблона кода страны") from error

    def normalize(self, phone_text):
        digits = re.sub(r"[^0-9]", "", phone_text)
        if phone_text.strip().startswith("00"):
            digits = digits[2:]
        elif not phone_text.strip().startswith("+") and digits.startswith("8"):
            digits = "7" + digits[1:]
        for code, rule in self.codes.items():
            if rule.get("optional_trunk_prefix") == "0" and re.match(
                rf"^(?:\+|00){code}{self.SPACES}*\({self.SPACES}*0"
                rf"{self.SPACES}*\)", phone_text.strip()
            ):
                digits = code + digits[len(code) + 1:]
                break
        return "+" + digits

    def validate_single_phone(self, phone_text):
        check_text(phone_text, "номер телефона")
        phone_text = phone_text.strip()
        if (not self.PHONE_PATTERN.fullmatch(phone_text)
                or self.REPEATED_PUNCTUATION.search(phone_text)):
            raise ValueError("некорректный формат номера телефона")
        normalized = self.normalize(phone_text)
        digits = normalized[1:]
        for code in sorted(self.codes, key=len, reverse=True):
            if digits.startswith(code):
                if len(digits) - len(code) in self.codes[code]["lengths"]:
                    patterns = self.codes[code].get("patterns", [])
                    if patterns and not any(
                        re.fullmatch(pattern, digits[len(code):])
                        for pattern in patterns
                    ):
                        raise ValueError(f"номер не соответствует формату кода +{code}")
                    return normalized
                lengths = ", ".join(map(str, self.codes[code]["lengths"]))
                raise ValueError(
                    f"для кода +{code} ожидается цифр после кода: {lengths}; "
                    f"введено: {len(digits) - len(code)}"
                )
        raise ValueError(
            "неизвестный код страны или неверная длина номера; "
            "международный номер вводится с + или 00"
        )

    def search(self, text):
        check_text(text, "текст для поиска")
        found = {}
        position = 0
        while match := self.PHONE_PATTERN.search(text, position):
            candidate = match.group()
            ends = [m.start() for m in re.finditer(self.SPACES + "+", candidate)]
            ends.append(len(candidate))
            position = match.start() + 1
            for end in reversed(ends):
                original = candidate[:end]
                try:
                    normalized = self.validate_single_phone(original)
                except ValueError:
                    continue
                found.setdefault(normalized, original)
                position = match.start() + end
                break
        return [PhoneNumber(original, normalized)
                for normalized, original in found.items()]

    def save_phone(self, phone_text):
        normalized = self.validate_single_phone(phone_text)
        if any(p.normalized == normalized for p in self.phones.get_all()):
            raise ValueError("номер уже сохранен")
        return self.phones.add(PhoneNumber(phone_text.strip(), normalized))

    def search_and_save(self, text):
        return self.save_found(self.search(text))

    def save_found(self, phones):
        existing = {p.normalized for p in self.phones.get_all()}
        count = 0
        for phone in phones:
            if phone.normalized not in existing:
                self.save_phone(phone.original)
                existing.add(phone.normalized)
                count += 1
        return count

    def delete_phone(self, phone_id):
        if type(phone_id) is not int or phone_id < 1:
            raise ValueError("id должен быть положительным целым числом")
        self.phones.delete(phone_id)

    def get_all_phones(self):
        return self.phones.get_all()
