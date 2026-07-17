# Errors

## 2026-07-17 - Python exception chaining patch typo

While refactoring `backend/app/routers/life.py`, I split `raise HTTPException(...) from exc` across two lines and created invalid syntax. Run `py_compile` immediately after manual route/service edits, especially around exception chaining.
