# Render deployment

The root `render.yaml` provisions one Python web service and a PostgreSQL 17 database in Frankfurt. FastAPI serves the website, static assets and API on the same public URL.

## Deploy

1. Push the project, including `render.yaml`, `.python-version` and `scripts/start-render.sh`, to GitHub.
2. In the [Render dashboard](https://dashboard.render.com/), choose **New → Blueprint** and connect the `WillowBooking` repository.
3. Select the branch containing these files and use `render.yaml` as the Blueprint path. Keep the service's **Root Directory empty** so both `backend/` and `frontend/` are included.
4. Review the two resources and deploy the Blueprint. Render supplies the internal database URL and generates the JWT signing key automatically. Do not upload the local `.env` file.
5. Once the web service is live, open its `https://…onrender.com` URL. Register an account and make a test reservation. `/api/health` checks the database connection; `/docs` opens the API reference.

The startup script applies migrations, creates the room catalog if needed, then starts Uvicorn on Render's assigned `PORT`. A failed migration stops startup. Restarting the service preserves existing accounts and bookings. This startup flow supports the included single-instance configuration.

The cloud database starts empty. Local Docker accounts and bookings are not uploaded. The web service connects to PostgreSQL over Render's internal network; public database access is disabled.

## Free plan limits

This Blueprint explicitly selects **Free** for both resources:

- The web service sleeps after 15 minutes without traffic. Opening the link wakes it up, so the first request can take longer.
- Free PostgreSQL databases expire after 30 days and have no backups. Upgrade the database before expiration if you want to retain the data and keep the site usable.
- Only one free PostgreSQL database can be active per workspace.

For an ongoing public demo, choose paid database and web-service plans and update the corresponding `plan` fields in `render.yaml` to match. Review current pricing in Render before confirming a change.

## Existing databases

If you connect an existing database instead of the new Blueprint database, resolve overlapping confirmed bookings for each account before applying migrations. The migration deliberately fails on conflicting records; it does not cancel guests' reservations.

Sources: [Blueprints](https://render.com/docs/infrastructure-as-code), [FastAPI deployment](https://render.com/docs/deploy-fastapi), [free plan limits](https://render.com/docs/free).
