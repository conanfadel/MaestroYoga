# Render to Hetzner Migration Checklist

This checklist is designed for moving from free Render to a production VPS on Hetzner with minimal downtime.

## 1) Prepare project

- Keep all secrets in environment variables only.
- Confirm app runs with PostgreSQL (`DATABASE_URL=postgresql+psycopg2://...`).
- Copy `.env.production.example` to `.env.production` and fill real values.
- Keep `PUBLIC_REQUIRE_EMAIL_VERIFICATION` configurable by env.

## 2) Provision server

- Create Ubuntu 22.04/24.04 VPS.
- Harden SSH (disable password login, use SSH keys).
- Open only required ports (`22`, `80`, `443`).

## 3) Install runtime stack

- Install Docker and Docker Compose plugin.
- Install Nginx and Certbot (or use a reverse-proxy container).
- Install `postgresql-client` (for backup scripts and restore commands).

## 4) Deploy application

- Clone repository on server.
- Add `.env.production` on server (never commit it).
- Start services:
  - `docker compose -f docker-compose.prod.yml up -d --build`
- Verify health:
  - `curl http://127.0.0.1:8000/`

## 5) Domain and HTTPS

- Point DNS A record to VPS public IP.
- Configure Nginx reverse proxy to `127.0.0.1:8000`.
- Issue TLS certificate with Let's Encrypt.
- Set `PUBLIC_BASE_URL=https://your-domain.com`.

## 6) Database backup and restore

- Create scheduled backups:
  - `DATABASE_URL=... BACKUP_DIR=/opt/backups ./scripts/backup_postgres.sh`
- Add cron job (example daily at 03:00 UTC):
  - `0 3 * * * DATABASE_URL=... BACKUP_DIR=/opt/backups /opt/maestroyoga/scripts/backup_postgres.sh >> /var/log/maestroyoga-backup.log 2>&1`
- Test restore once before go-live:
  - `DATABASE_URL=... ./scripts/restore_postgres.sh /opt/backups/maestroyoga_YYYYMMDD_HHMMSS.dump`

## 7) Cutover

- Freeze writes briefly (maintenance mode if needed).
- Take final Render DB snapshot/export.
- Restore final data to Hetzner DB.
- Update DNS to Hetzner.
- Monitor logs and key flows (`register`, `login`, `booking`, `payment`).

## 8) Post-cutover

- Keep Render as fallback for 24-72h.
- Validate email verification and password reset flows.
- Set up uptime monitoring and alerting.
- Document rollback procedure.
