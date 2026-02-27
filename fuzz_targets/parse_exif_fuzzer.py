import os
import sys
import tempfile

from app.osint.image_validator import validate_image_integrity


def fuzz(data: bytes) -> None:
    fd, path = tempfile.mkstemp(prefix="fuzz_exif_", suffix=".bin")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        try:
            validate_image_integrity(path)
        except Exception:
            # Ignore Python-level exceptions; fuzzers focus on crashes/assertions.
            pass
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


if __name__ == "__main__":
    with open(sys.argv[1], "rb") as f:
        fuzz(f.read())
