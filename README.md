# Artआलय: build milestone M0 + M1 (backend)

Implemented in this drop (matches Parts 3-5 of the blueprint):
- PostgreSQL schema + seed (10 categories, tags, settings incl. chat button ON) in `backend/schema.sql`
- FastAPI: public catalog (Price on request label, tag expiry), enquiry form endpoint (+91 validation, consent, honeypot, rate limit,
  AES-GCM encrypted number), admin login (argon2, lockout, DB sessions, CSRF), admin enquiry inbox (list, summary, status/notes, delete),
  image upload to WebP variants stored in PostgreSQL chunks, media delivery with immutable caching, product creation.

## Run
```
cd backend && cp .env.example .env     # fill ENQUIRY_KEY (see comment inside)
cd .. && docker compose up --build -d
docker compose exec api python create_admin.py smileforever5@gmail.com 'choose-a-strong-password'
# API docs: http://localhost:8000/docs
```

## Frontend (Next.js, in `frontend/`)
Home, Shop (category chips, search), product page with gallery and enquiry form, Custom page, admin sign-in and enquiry inbox (reply on WhatsApp, status, delete).
Open http://localhost:3000 (site) and http://localhost:3000/admin (admin). Chat button follows the `enquiry_mode` setting.
Admin tabs: Enquiries, Products (publish/unpublish, edit price, delete), Add product (photos, tags, draft or publish), Categories (show/hide).
Not yet: video, email alerts, 6-month erasure job, product text/photo editing after creation, category covers, tests.
