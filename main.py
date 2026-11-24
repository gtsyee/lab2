from pathlib import Path
from repository_layer import JsonRepository, read_search_page, read_search_text
from service_layer import PhoneService

MENU = """
1. проверить один номер
2. найти номера в тексте
3. показать сохраненные номера
4. удалить сохраненный номер
5. найти номера в текстовом файле
6. найти номера на веб-странице
0. выйти
"""


def ask_save():
    while True:
        answer = input("сохранить в JSON? (д/н): ").strip().lower()
        if answer in ("д", "да", "y", "yes"):
            return True
        if answer in ("н", "нет", "n", "no"):
            return False
        print("введите д или н")


def main():
    try:
        service = PhoneService(JsonRepository(Path(__file__).with_name("phones.json")))
    except (OSError, ValueError, TypeError) as error:
        print(f"ошибка загрузки: {error}")
        return
    while True:
        try:
            print(MENU)
            choice = input("выберите действие: ").strip()
            if choice == "0":
                return
            if choice == "1":
                phone = input("введите номер: ")
                print("номер корректен:", service.validate_single_phone(phone))
                if ask_save():
                    item = service.save_phone(phone)
                    print(f"сохранено, id: {item.id}")
            elif choice in ("2", "5", "6"):
                if choice == "2":
                    text = input("введите текст: ")
                elif choice == "5":
                    path = input("путь к текстовому файлу: ").strip()
                    if not path:
                        raise ValueError("укажите путь к файлу")
                    text = read_search_text(path)
                else:
                    text = read_search_page(input("URL страницы: ").strip())
                if not text.strip():
                    print("найдено номеров: 0")
                    continue
                found = service.search(text)
                print(f"найдено номеров: {len(found)}")
                for item in found:
                    print(f"{item.original} -> {item.normalized}")
                if found and ask_save():
                    print("сохранено новых номеров:", service.save_found(found))
            elif choice == "3":
                phones = service.get_all_phones()
                if not phones:
                    print("сохраненных номеров нет")
                for item in phones:
                    print(f"{item.id}. {item.original} -> {item.normalized}")
            elif choice == "4":
                service.delete_phone(int(input("id номера: ")))
                print("номер удален из JSON")
            else:
                print("такого действия нет")
        except (ValueError, TypeError, OSError) as error:
            print(f"ошибка: {error}")
        except (EOFError, KeyboardInterrupt):
            print("\nвыход")
            return


if __name__ == "__main__":
    main()
