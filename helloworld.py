def create_greeting(name: str) -> str:
    """Create a friendly greeting."""
    clean_name = name.strip() or "World"
    return f"Hello, {clean_name}!"


def main() -> None:
    name = input("What is your name? ")
    print(create_greeting(name))


if __name__ == "__main__":
    main()
