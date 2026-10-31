"""Made-up members for development, so no real record leaves WellnessLiving.

The same seed always yields the same file. Addresses are under example.com,
which never delivers, and phone numbers use the 555-01xx range reserved for
fiction, so nothing generated here can reach a real person.
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

from sws_membership.members.import_csv import COLUMNS, OPTIONAL_COLUMNS
from sws_membership.members.models import Sport

FIRST_NAMES = (
    "Avery",
    "Blake",
    "Casey",
    "Dana",
    "Eli",
    "Finley",
    "Gray",
    "Harper",
    "Indigo",
    "Jules",
    "Kai",
    "Lane",
    "Morgan",
    "Noor",
    "Oakley",
    "Parker",
    "Quinn",
    "Reese",
    "Sage",
    "Tatum",
    "Uma",
    "Vale",
    "Wren",
    "Xen",
    "Yael",
    "Zion",
)
LAST_NAMES = (
    "Spit",
    "Gust",
    "Howe",
    "Squall",
    "Tide",
    "Kite",
    "Foil",
    "Wing",
    "Boom",
    "Luff",
    "Reach",
    "Jibe",
    "Tack",
    "Halyard",
    "Eddy",
    "Chinook",
    "Nimbus",
    "Stratus",
    "Fetch",
    "Swell",
)
MEMBER_NUMBER_LOW = 100_000
MEMBER_NUMBER_HIGH = 999_999


def generate_sample_members(path: Path, count: int, seed: int = 2026) -> None:
    generator = random.Random(seed)
    numbers = generator.sample(range(MEMBER_NUMBER_LOW, MEMBER_NUMBER_HIGH + 1), count)
    season_start = date(2026, 5, 1)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS + OPTIONAL_COLUMNS)
        writer.writeheader()
        for index, member_number in enumerate(numbers, start=1):
            first = generator.choice(FIRST_NAMES)
            last = generator.choice(LAST_NAMES)
            # Roughly one in five is a youth, so age rules have both sides to test.
            years = (
                generator.randint(12, 18) if generator.random() < 0.2 else generator.randint(19, 72)
            )
            birthday = season_start - timedelta(days=365 * years + generator.randint(0, 364))
            writer.writerow(
                {
                    "member_number": str(member_number),
                    "first_name": first,
                    "last_name": last,
                    "email": f"{first.lower()}.{last.lower()}.{index}@example.com",
                    "phone": f"604-555-{generator.randint(100, 199):04d}",
                    "date_of_birth": birthday.isoformat(),
                    "address_line_1": f"{generator.randint(1, 9999)} {generator.choice(LAST_NAMES)} Road",
                    "address_line_2": "",
                    "city": generator.choice(
                        ("Squamish", "Whistler", "Vancouver", "North Vancouver")
                    ),
                    "province": "BC",
                    "postal_code": f"V8B {generator.randint(0, 9)}A{generator.randint(0, 9)}",
                    "sports": ";".join(
                        sorted(
                            {
                                s.value
                                for s in generator.sample(list(Sport)[:-1], generator.randint(1, 2))
                            }
                        )
                    ),
                }
            )
