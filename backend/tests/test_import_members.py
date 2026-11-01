import csv
from pathlib import Path

import pytest

from sws_membership.members.import_csv import COLUMNS, import_members
from sws_membership.members.member_numbers import allocate_member_number
from sws_membership.members.models import Member
from sws_membership.members.sample_data import generate_sample_members

pytestmark = pytest.mark.django_db


def _write(path: Path, rows: list[dict]) -> Path:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


ROW = {
    "member_number": "000456",
    "first_name": "Sam",
    "last_name": "Rider",
    "email": "Sam.Rider@Example.com",
    "phone": "604-555-0101",
    "date_of_birth": "1990-05-01",
}


def test_import_creates_members_and_moves_the_sequence_past_them(tmp_path):
    report = import_members(
        _write(tmp_path / "m.csv", [ROW, {**ROW, "member_number": "900", "email": "b@example.com"}])
    )
    assert (report.created, report.updated, report.rejected) == (2, 0, [])
    member = Member.objects.get(member_number=456)
    assert member.email == "sam.rider@example.com"
    assert member.has_password is False
    assert allocate_member_number() > 900


def test_reimporting_the_same_file_changes_nothing(tmp_path):
    path = _write(tmp_path / "m.csv", [ROW])
    import_members(path)
    report = import_members(path)
    assert (report.created, report.updated, report.unchanged) == (0, 0, 1)


def test_a_corrected_file_updates_the_changed_rows_only(tmp_path):
    import_members(_write(tmp_path / "a.csv", [ROW]))
    report = import_members(_write(tmp_path / "b.csv", [{**ROW, "phone": "604-555-0199"}]))
    assert (report.created, report.updated, report.unchanged) == (0, 1, 0)
    assert Member.objects.get(member_number=456).phone == "604-555-0199"


def test_bad_rows_are_rejected_with_their_line_and_the_rest_imported(tmp_path):
    rows = [
        ROW,
        {**ROW, "member_number": "abc", "email": "x@example.com"},
        {**ROW, "member_number": "77", "email": ""},
        {**ROW, "member_number": "456", "email": "dup@example.com"},
    ]
    report = import_members(_write(tmp_path / "m.csv", rows))
    assert report.created == 1
    assert [line for line, _ in report.rejected] == [3, 4, 5]
    assert "twice" in report.rejected[2][1]


def test_sample_data_is_deterministic_unique_and_fictional(tmp_path):
    first, second = tmp_path / "one.csv", tmp_path / "two.csv"
    generate_sample_members(first, 150, seed=7)
    generate_sample_members(second, 150, seed=7)
    assert first.read_bytes() == second.read_bytes()

    report = import_members(first)
    assert (report.created, report.rejected) == (150, [])
    assert Member.objects.count() == 150
    for member in Member.objects.all():
        assert member.email.endswith("@example.com")
        assert member.phone.startswith("604-555-01")
        assert member.sports.exists()
