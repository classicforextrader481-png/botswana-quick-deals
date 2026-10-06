# Botswana Quick Deals — Real MVP

This is a real full-stack Flask marketplace starter, not the earlier HTML-only prototype.

Included:
- seller registration/login
- persistent listings (SQLite locally; use DATABASE_URL/Postgres for production)
- seller dashboard
- listing categories and Botswana locations
- image upload
- paid listing plans
- payment record + payment-reference workflow
- payment webhook endpoint for a real gateway
- admin login/dashboard
- publish/hide/delete controls
- mobile-first UI

## Run on a computer
1. Install Python 3.11+
2. `pip install -r requirements.txt`
3. Set `ADMIN_EMAIL` and `ADMIN_PASSWORD`
4. Run: `python app.py`
5. Open http://127.0.0.1:5000

## Important payment note
The app has the payment architecture, but no fake payment credentials are included.
For real automatic payments, obtain a merchant account/API credentials from a Botswana payment provider (for example Pata or BTC Smega) and put their approved checkout/webhook details into environment variables. Never put your PIN, CVV, wallet password or secret key in the HTML.

## Production note
Do not use local SQLite/uploads as your permanent production storage on a free ephemeral host. Use a managed Postgres database and object storage for images. Render's free web services are useful for testing but local files are lost on restart/redeploy.
