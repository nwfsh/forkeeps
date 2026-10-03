"""Print the six measurements and the detected mode for saved photos.

Usage: python measure.py PHOTO [PHOTO ...]
"""
import sys
from pathlib import Path

import vision


def main(paths: list[str]) -> None:
    for path in paths:
        result = vision.analyze(vision.decode_image(Path(path).read_bytes()))
        print(Path(path).name)
        for i, person in enumerate(result["people"]):
            print(f"  body {i + 1}")
            for name, value in person.items():
                if name != "points":
                    print(f"  {name:13} {value}")
            print()
        if not result["faces"]:
            print("  no face found\n")
            continue
        for i, face in enumerate(result["faces"]):
            if len(result["faces"]) > 1:
                print(f"  face {i + 1}")
            for name, value in face.get("measurements", {}).items():
                print(f"  {name:13} {value}")
            print(f"  {'mode':13} {face.get('mode')}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
