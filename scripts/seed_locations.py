"""
Adds India's districts and towns to the locations table, state by state, from
scripts/data/india_locations.json (Local Government Directory data: every district plus the
municipal corporations, municipalities and town panchayats, with council words like
"Municipal Council" stripped from the names).

Safe to run more than once: a city already saved for a state (any capitalisation) is skipped,
and Haryana is left out entirely because its cities were added by hand. Nothing is written
unless --apply is given.

    python -m scripts.seed_locations                  # preview what would be added
    python -m scripts.seed_locations --apply          # add the missing cities
    python -m scripts.seed_locations --districts-only --apply
    python -m scripts.seed_locations --state Punjab --state Rajasthan --apply
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from app.db.session import SessionLocal
from app.db.models.location import Location

DATA_FILE = Path(__file__).parent / "data" / "india_locations.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Add Indian districts and towns to the locations table.")
    parser.add_argument("--apply", action="store_true", help="Write to the database (default is a preview).")
    parser.add_argument("--districts-only", action="store_true", help="Only add districts and large cities, not towns.")
    parser.add_argument("--state", action="append", default=[], help="Only these states (repeatable).")
    parser.add_argument("--skip-state", action="append", default=[], help="Also leave out these states (repeatable).")
    args = parser.parse_args()

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    skip = {s.lower() for s in data.get("excluded_states", []) + args.skip_state}
    only = {s.lower() for s in args.state}

    db = SessionLocal()
    try:
        existing = {
            ((state or "").strip().lower(), (city or "").strip().lower())
            for state, city in db.query(Location.state, Location.city_name).all()
        }
        to_add: list[Location] = []
        per_state: Counter[str] = Counter()
        already = 0
        for state, rows in data["states"].items():
            if state.lower() in skip or (only and state.lower() not in only):
                continue
            for row in rows:
                if args.districts_only and row["category"] != "city":
                    continue
                key = (state.lower(), row["city"].lower())
                if key in existing:
                    already += 1
                    continue
                existing.add(key)
                to_add.append(Location(city_name=row["city"], state=state, category=row["category"]))
                per_state[state] += 1

        for state in sorted(per_state):
            print(f"  {state}: {per_state[state]}")
        print(f"{len(to_add)} cities to add, {already} already present"
              f" (skipped states: {', '.join(sorted(skip)) or 'none'})")

        if not args.apply:
            print("Preview only - run again with --apply to add them.")
            return 0
        if to_add:
            db.add_all(to_add)
            db.commit()
        print(f"Added {len(to_add)} cities.")
        return 0
    except Exception as exc:  # noqa: BLE001 - report and roll back any database error
        db.rollback()
        print(f"Failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
