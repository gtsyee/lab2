from repository_layer import MemoryRepository
from service_layer import PhoneService
MENU = """
1. проверить один номер
2. найти номера в тексте и сохранить
3. показать все сохраненные номера
0. выйти из программы
"""
def main():
    service = PhoneService(MemoryRepository())
    while True:
        try:
            print(MENU)
            choice = input("выберите действие: ").strip()
            if choice == "0":
                print("программа завершена")
                break
            elif choice == "1":
                phone = input("введите номер: ")
                normalized = service.validate_single_phone(phone)
                print(f"номер корректен! нормализованный вид: {normalized}")
            elif choice == "2":
                text = input("введите текст для поиска: ")
                count = service.search_and_save(text)
                if count == 0:
                    print("в тексте не найдено новых номеров")
                else:
                    print(f"найдено и сохранено новых номеров: {count}")
            elif choice == "3":
                phones = service.get_all_phones()
                if not phones:
                    print("база номеров пуста")
                for p in phones:
                    print(f"{p.id}. {p.original} -> {p.normalized}")
            else:
                print("такого действия нет, выберите пункт меню")
        except (ValueError, TypeError) as error:
            print(f"ошибка: {error}")
        except (EOFError, KeyboardInterrupt):
            print("\nпрограмма завершена")
            break
if __name__ == "__main__":
    main()