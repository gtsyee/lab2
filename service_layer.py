import re
from data_layer import PhoneNumber
from repository_layer import Repository
def check_text(text, field):
    if not isinstance(text, str):
        raise TypeError(f"{field} должно быть строкой")
    if not text.strip():
        raise ValueError(f"{field} не должно быть пустым")
class PhoneService:
    PHONE_PATTERN = re.compile(r'(?:\+7|8)[\s\-]*\(?[0-9]{3}\)?[\s\-]*[0-9]{3}[\s\-]*[0-9]{2}[\s\-]*[0-9]{2}')
    def __init__(self, phones: Repository):
        self.phones = phones
    def normalize(self, phone_text):
        digits = re.sub(r'\D', '', phone_text)
        if digits.startswith('8'):
            digits = '7' + digits[1:]
        if len(digits) == 11 and digits.startswith('7'):
            return f"+{digits}"
        return phone_text
    def validate_single_phone(self, phone_text):
        check_text(phone_text, "номер телефона")
        if not re.fullmatch(self.PHONE_PATTERN, phone_text.strip()):
            raise ValueError("некорректный формат номера телефона")
        return self.normalize(phone_text)
    def search_and_save(self, text):
        check_text(text, "текст для поиска")
        matches = self.PHONE_PATTERN.findall(text)
        existing_normalized = {p.normalized for p in self.phones.get_all()}
        added_count = 0
        for match in matches:
            norm = self.normalize(match)
            if norm not in existing_normalized:
                self.phones.add(PhoneNumber(original=match, normalized=norm))
                existing_normalized.add(norm)
                added_count += 1
        return added_count
    def get_all_phones(self):
        return self.phones.get_all()