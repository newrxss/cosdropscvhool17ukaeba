from pathlib import Path
import ast
root=Path(__file__).resolve().parent
for name in ("bot.py", "webapp_api.py"):
    ast.parse((root/name).read_text(encoding="utf-8"), filename=name)
html=(root/"web"/"index.html").read_text(encoding="utf-8")
for marker in ("function home()", "function showCases()", "function showCasino()", "function showCollection()", "function showProfile()", "/api/dashboard"):
    assert marker in html, f"Missing frontend marker: {marker}"
api=(root/"webapp_api.py").read_text(encoding="utf-8")
for marker in ("/api/cases/open", "/api/daily", "/api/inventory/sell", "/api/promo", "/api/rating", "/api/tasks/claim"):
    assert marker in api, f"Missing API route: {marker}"
print("OK: Python syntax and frontend/API markers passed. No database was opened or changed.")
