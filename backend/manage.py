"""Account administration for a single-owner Work OS instance.

Run with DATABASE_URL pointing at the target database, e.g. locally against Neon:
    python manage.py create-user --email you@example.com --name "Your Name"
    python manage.py claim-local --email you@example.com --name "Your Name"
    python manage.py revoke-sessions --email you@example.com

create-user      Creates an account with its own workspace (use instead of opening public registration).
claim-local      Turns the old password-less `local@workos.dev` bootstrap account into your real login,
                 so data created while authentication was off stays accessible.
revoke-sessions  Invalidates every token issued to the account.
"""
import argparse
import getpass
import sys
from sqlalchemy import select
from sqlalchemy.orm import Session
from main import Role, User, Workspace, WorkspaceMember, engine, password_hash

LEGACY_LOCAL_EMAIL = "local@workos.dev"


def read_password() -> str:
    first = getpass.getpass("Password (min 12 chars): ")
    if len(first) < 12:
        sys.exit("Password must be at least 12 characters.")
    if getpass.getpass("Repeat password: ") != first:
        sys.exit("Passwords do not match.")
    return first


def create_user(email: str, name: str) -> None:
    with Session(engine) as db:
        if db.scalar(select(User).where(User.email == email)):
            sys.exit(f"An account with {email} already exists.")
        user = User(name=name, email=email, password_hash=password_hash.hash(read_password()))
        db.add(user); db.flush()
        workspace = Workspace(name=f"{name}'s Work OS"); db.add(workspace); db.flush()
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=Role.owner.value))
        db.commit()
    print(f"Created {email} with workspace '{workspace.name}'.")


def claim_local(email: str, name: str) -> None:
    with Session(engine) as db:
        legacy = db.scalar(select(User).where(User.email == LEGACY_LOCAL_EMAIL))
        if not legacy:
            sys.exit("No legacy local@workos.dev account found; nothing to claim.")
        if db.scalar(select(User).where(User.email == email)):
            sys.exit(f"{email} already has an account. Use a different email or remove that account first.")
        legacy.email, legacy.name = email, name
        legacy.password_hash = password_hash.hash(read_password())
        legacy.token_version = (legacy.token_version or 0) + 1
        db.commit()
    print(f"The local workspace now belongs to {email}. Log in with that email.")


def revoke_sessions(email: str) -> None:
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.email == email))
        if not user:
            sys.exit(f"No account for {email}.")
        user.token_version = (user.token_version or 0) + 1
        db.commit()
    print(f"All sessions for {email} revoked.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("create-user", "claim-local"):
        cmd = sub.add_parser(command); cmd.add_argument("--email", required=True); cmd.add_argument("--name", required=True)
    sub.add_parser("revoke-sessions").add_argument("--email", required=True)
    args = parser.parse_args()
    email = args.email.strip().lower()
    if args.command == "create-user": create_user(email, args.name)
    elif args.command == "claim-local": claim_local(email, args.name)
    else: revoke_sessions(email)
