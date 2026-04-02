# Pre-Migration Prep (While Still Developing)

Use this checklist now, before final release, so migration later is quick.

## During development (Render free)

- Keep feature work on current flow.
- Keep `PUBLIC_REQUIRE_EMAIL_VERIFICATION=0` if email delivery is unstable.
- Keep all secrets in Render Environment (not in git).
- Avoid using SQLite for final production planning.

## Before launch to clients

1. Freeze env keys:
   - `JWT_SECRET`
   - `PUBLIC_JWT_SECRET`
   - `SEED_DEMO_KEY`
2. Switch production DB to PostgreSQL.
3. Turn verification back on:
   - `PUBLIC_REQUIRE_EMAIL_VERIFICATION=1`
4. Verify email provider works in production.
5. Run smoke tests:
   - `python -m pytest -q tests`
6. Final backup and migration dry run.

## Suggested release gates

- Gate 1: Admin dashboard stable.
- Gate 2: Public booking and payment stable.
- Gate 3: Email verification + password reset stable.
- Gate 4: Performance check under expected user load.
