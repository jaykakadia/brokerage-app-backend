import sys
from app.cli.admin import create_admin


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "create-admin":
        # Remove subcommand from sys.argv so argparse works
        sys.argv.pop(1)
        create_admin()
    else:
        print("Usage: python -m app.cli create-admin [--email EMAIL] [--name NAME] [--phone PHONE]")


if __name__ == "__main__":
    main()
