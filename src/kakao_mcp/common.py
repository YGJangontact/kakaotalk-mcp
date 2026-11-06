"""Platform-independent text and selection helpers."""
EMPTY_HINT = "멤버들과 공유하고 싶은 소식을 남겨보세요."


def unique(items, label):
    if len(items) > 1:
        raise RuntimeError(f"ambiguous {label}: close duplicate windows first")
    return items[0] if items else None


def normalize(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")
