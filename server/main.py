import os
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.app import create_app


def main():
    db_path = os.environ.get("CARD_DB_PATH", str(Path(__file__).resolve().parent / "data" / "cards.db"))
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    jwt_secret = os.environ.get("CARD_JWT_SECRET", "dev-secret-change-me")
    admin_password = os.environ.get("CARD_ADMIN_PASSWORD", "admin123")
    app = create_app(db_path, jwt_secret, admin_password)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
