"""
This is a pnpm monorepo. There is no top-level Python entry point.

To run the backend:
    cd artifacts/sba-backend && python app.py

To run the frontend:
    cd artifacts/sba-web && pnpm dev

See README.md and replit.md for full setup instructions.
"""

import sys

if __name__ == "__main__":
    print(__doc__, file=sys.stderr)
    sys.exit(1)
