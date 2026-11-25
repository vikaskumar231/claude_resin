"""Artaalay API: public catalog, enquiries (encrypted), admin auth + inbox, media stored in PostgreSQL."""
import base64, hashlib, hmac, io, os, re, secrets, time
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Cookie, Depends, FastAPI, File, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import Response as Raw
from PIL import Image, ImageOps
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

pool = ConnectionPool(os.environ["DATABASE_URL"], kwargs={"row_factory": dict_row}, open=True)
KEY = base64.b64decode(os.environ["ENQUIRY_KEY"])           # 32 bytes
SECURE = os.environ.get("COOKIE_SECURE", "false") == "true"
ph = PasswordHasher()
app = FastAPI(title="Artaalay API")
CONSENT_VERSION = "v1"

def q(sql, args=(), one=False, commit=False):
    with pool.connection() as c:
        cur = c.execute(sql, args)
        rows = cur.fetchall() if cur.description else []
        return (rows[0] if rows else None) if one else rows

def enc(s: str) -> bytes:
    n = os.urandom(12); return n + AESGCM(KEY).encrypt(n, s.encode(), None)
def dec(b: bytes) -> str:
    b = bytes(b); return AESGCM(KEY).decrypt(b[:12], b[12:], None).decode()
def num_hash(s: str) -> bytes: return hmac.new(KEY, s.encode(), hashlib.sha256).digest()

# ---------- public ----------
@app.get("/api/public/settings")
def settings():
    keys = ("whatsapp_number", "instagram_url", "enquiry_mode", "shipping_note")
    return {r["key"]: r["value"] for r in q("SELECT key,value FROM site_setting WHERE key = ANY(%s)", (list(keys),))}

@app.get("/api/public/categories")
def categories():
    return q("SELECT slug,name,description,cover_media_id FROM category WHERE is_active ORDER BY sort_order")

PRODUCT_COLS = """p.id,p.slug,p.name,p.short_description,p.starting_price_inr,p.cover_media_id,c.slug AS category_slug,
  COALESCE((SELECT json_agg(json_build_object('slug',t.slug,'label',t.label,'style',t.style)) FROM product_tag pt JOIN tag t ON t.id=pt.tag_id
   WHERE pt.product_id=p.id AND (pt.expires_at IS NULL OR pt.expires_at>now())),'[]') AS tags"""

@app.get("/api/public/products")
def products(category: Optional[str] = None, tag: Optional[str] = None, q_: Optional[str] = None, limit: int = 24, offset: int = 0):
    where, args = ["p.status='published'", "c.is_active"], []
    if category: where.append("c.slug=%s"); args.append(category)
    if tag: where.append("EXISTS(SELECT 1 FROM product_tag pt JOIN tag t ON t.id=pt.tag_id WHERE pt.product_id=p.id AND t.slug=%s)"); args.append(tag)
    if q_: where.append("(p.name %% %s OR p.name ILIKE %s)"); args += [q_, f"%{q_}%"]
    rows = q(f"SELECT {PRODUCT_COLS} FROM product p JOIN category c ON c.id=p.category_id WHERE {' AND '.join(where)} "
             "ORDER BY p.published_at DESC NULLS LAST LIMIT %s OFFSET %s", (*args, min(limit, 60), offset))
    for r in rows: r["price_label"] = f"From ₹{r['starting_price_inr']:,.0f}" if r["starting_price_inr"] is not None else "Price on request"
    return rows

@app.get("/api/public/products/{slug}")
def product(slug: str):
    p = q(f"SELECT {PRODUCT_COLS}, p.description FROM product p JOIN category c ON c.id=p.category_id WHERE p.slug=%s AND p.status='published'", (slug,), one=True)
    if not p: raise HTTPException(404, "Not found")
    p["price_label"] = f"From ₹{p['starting_price_inr']:,.0f}" if p["starting_price_inr"] is not None else "Price on request"
    p["media"] = q("SELECT asset_id,alt_text,is_cover FROM product_media WHERE product_id=%s ORDER BY sort_order", (p["id"],))
    return p

_hits: dict = {}
def rate_limit(ip: str, limit=5, window=3600):
    now = time.time(); h = [t for t in _hits.get(ip, []) if now - t < window]
    if len(h) >= limit: raise HTTPException(429, "Too many enquiries, please try again later")
    _hits[ip] = h + [now]   # in-memory: replace with a shared limiter if you run several workers

class EnquiryIn(BaseModel):
    whatsapp_number: str
    requirements: str = Field(min_length=10, max_length=2000)
    product_slug: Optional[str] = None            # None = custom idea
    customer_name: Optional[str] = Field(None, max_length=60)
    needed_by: Optional[date] = None
    reason: Optional[str] = Field(None, max_length=1000)
    consent: bool
    website: str = ""                             # honeypot, must stay empty

@app.post("/api/public/enquiries", status_code=201)
def create_enquiry(body: EnquiryIn, request: Request):
    if body.website: return {"reference_code": "AA-00-00000"}    # silently drop bots
    if not body.consent: raise HTTPException(422, "Consent is required")
    m = re.fullmatch(r"(?:\+?91)?([6-9]\d{9})", re.sub(r"[\s-]", "", body.whatsapp_number))
    if not m: raise HTTPException(422, "Enter a valid 10-digit Indian mobile number")
    if body.needed_by and not (date.today() <= body.needed_by <= date.today() + timedelta(days=366)):
        raise HTTPException(422, "Needed-by date must be within the next year")
    rate_limit(request.client.host if request.client else "?")
    e164 = "+91" + m.group(1)
    prod = q("SELECT id,name FROM product WHERE slug=%s AND status='published'", (body.product_slug,), one=True) if body.product_slug else None
    seq = q("SELECT nextval('enquiry_seq') AS n", one=True)["n"]
    ref = f"AA-{datetime.now().strftime('%y')}-{seq:05d}"
    q("""INSERT INTO customer_enquiry(reference_code,product_id,product_name_snapshot,customer_name,whatsapp_number_enc,whatsapp_number_hash,
         requirements,needed_by,reason,consent_text_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
      (ref, prod and prod["id"], prod and prod["name"], body.customer_name, enc(e164), num_hash(e164),
       body.requirements, body.needed_by, body.reason, CONSENT_VERSION))
    return {"reference_code": ref}

@app.get("/media/{asset_id}/{variant}")
def media(asset_id: str, variant: str):
    b = q("SELECT id,mime_type,etag FROM media_blob WHERE asset_id=%s AND variant=%s", (asset_id, variant), one=True)
    if not b: raise HTTPException(404)
    data = b"".join(bytes(r["data"]) for r in q("SELECT data FROM media_chunk WHERE blob_id=%s ORDER BY seq", (b["id"],)))
    return Raw(data, media_type=b["mime_type"], headers={"ETag": b["etag"], "Cache-Control": "public, max-age=31536000, immutable"})

# ---------- admin ----------
class LoginIn(BaseModel): email: str; password: str

@app.post("/admin/auth/login")
def login(body: LoginIn, response: Response):
    u = q("SELECT * FROM admin_user WHERE email=%s", (body.email,), one=True)
    if not u or (u["locked_until"] and u["locked_until"] > datetime.now(timezone.utc)): raise HTTPException(401, "Invalid credentials or account locked")
    try: ph.verify(u["password_hash"], body.password)
    except VerifyMismatchError:
        fails = u["failed_attempts"] + 1
        q("UPDATE admin_user SET failed_attempts=%s, locked_until=%s WHERE id=%s", (fails, datetime.now(timezone.utc) + timedelta(minutes=15) if fails >= 5 else None, u["id"]))
        raise HTTPException(401, "Invalid credentials or account locked")
    q("UPDATE admin_user SET failed_attempts=0, locked_until=NULL WHERE id=%s", (u["id"],))
    tok, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    q("INSERT INTO admin_session(user_id,token_hash,csrf,expires_at) VALUES (%s,%s,%s,now()+interval '12 hours')", (u["id"], hashlib.sha256(tok.encode()).digest(), csrf))
    response.set_cookie("aa_session", tok, httponly=True, secure=SECURE, samesite="lax", max_age=43200, path="/")
    return {"csrf": csrf}

def admin(request: Request, aa_session: Optional[str] = Cookie(None), x_csrf_token: Optional[str] = Header(None)):
    if not aa_session: raise HTTPException(401)
    s = q("""UPDATE admin_session SET last_seen_at=now() WHERE token_hash=%s AND expires_at>now() AND last_seen_at>now()-interval '2 hours'
             RETURNING user_id,csrf""", (hashlib.sha256(aa_session.encode()).digest(),), one=True)
    if not s: raise HTTPException(401)
    if request.method not in ("GET", "HEAD") and not (x_csrf_token and hmac.compare_digest(x_csrf_token, s["csrf"])): raise HTTPException(403, "CSRF")
    return s["user_id"]

@app.post("/admin/auth/logout")
def logout(response: Response, aa_session: Optional[str] = Cookie(None)):
    if aa_session: q("DELETE FROM admin_session WHERE token_hash=%s", (hashlib.sha256(aa_session.encode()).digest(),))
    response.delete_cookie("aa_session"); return {"ok": True}

@app.get("/admin/enquiries/summary")
def enq_summary(_=Depends(admin)):
    return {r["status"]: r["n"] for r in q("SELECT status::text, count(*) n FROM customer_enquiry GROUP BY 1")}

@app.get("/admin/enquiries")
def enq_list(status: Optional[str] = None, limit: int = 50, offset: int = 0, _=Depends(admin)):
    rows = q("""SELECT id,reference_code,product_name_snapshot,customer_name,whatsapp_number_enc,requirements,needed_by,reason,status::text,created_at
                FROM customer_enquiry WHERE (%s::text IS NULL OR status::text=%s) ORDER BY created_at DESC LIMIT %s OFFSET %s""",
             (status, status, min(limit, 100), offset))
    for r in rows: r["whatsapp_number"] = dec(r.pop("whatsapp_number_enc"))
    return rows

class EnqPatch(BaseModel): status: Optional[str] = None; admin_notes: Optional[str] = None

@app.patch("/admin/enquiries/{eid}")
def enq_patch(eid: str, body: EnqPatch, _=Depends(admin)):
    if body.status not in (None, "new", "contacted", "in_discussion", "won", "closed", "spam"): raise HTTPException(422, "Bad status")
    q("""UPDATE customer_enquiry SET status=COALESCE(%s::enquiry_status,status), admin_notes=COALESCE(%s,admin_notes),
         closed_at=CASE WHEN %s='closed' THEN now() ELSE closed_at END WHERE id=%s""", (body.status, body.admin_notes, body.status, eid))
    return {"ok": True}

@app.delete("/admin/enquiries/{eid}")
def enq_delete(eid: str, _=Depends(admin)):
    q("DELETE FROM customer_enquiry WHERE id=%s", (eid,)); return {"ok": True}

# Media: images are re-encoded to WebP variants (strips EXIF/GPS) and stored as chunked bytea in PostgreSQL.
VARIANTS = {"thumb": (400, True), "card": (800, True), "full": (1600, False)}
@app.post("/admin/media", status_code=201)
def upload_media(file: UploadFile = File(...), _=Depends(admin)):
    raw = file.file.read(15 * 1024 * 1024 + 1)
    if len(raw) > 15 * 1024 * 1024: raise HTTPException(413, "Max 15 MB")
    try: img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    except Exception: raise HTTPException(415, "Not a supported image")
    asset = q("INSERT INTO media_asset DEFAULT VALUES RETURNING id", one=True)["id"]
    for name, (size, square) in VARIANTS.items():
        v = ImageOps.fit(img, (size, size), Image.LANCZOS) if square else ImageOps.contain(img, (size, size), Image.LANCZOS)
        buf = io.BytesIO(); v.save(buf, "WEBP", quality=82); data = buf.getvalue()
        blob = q("INSERT INTO media_blob(asset_id,variant,mime_type,byte_size,etag) VALUES (%s,%s,'image/webp',%s,%s) RETURNING id",
                 (asset, name, len(data), '"' + hashlib.sha256(data).hexdigest()[:24] + '"'), one=True)["id"]
        for i in range(0, len(data), 1 << 20): q("INSERT INTO media_chunk VALUES (%s,%s,%s)", (blob, i >> 20, data[i:i + (1 << 20)]))
    return {"asset_id": str(asset)}

class ProductIn(BaseModel):
    category_slug: str; slug: str; name: str; short_description: Optional[str] = None; description: Optional[str] = None
    starting_price_inr: Optional[float] = None; publish: bool = False; asset_ids: list[str] = []; tag_slugs: list[str] = []

@app.post("/admin/products", status_code=201)
def create_product(b: ProductIn, _=Depends(admin)):
    c = q("SELECT id FROM category WHERE slug=%s", (b.category_slug,), one=True)
    if not c: raise HTTPException(422, "Unknown category")
    if b.publish and not b.asset_ids: raise HTTPException(422, "Add at least one photo before publishing")
    pid = q("""INSERT INTO product(category_id,slug,name,short_description,description,starting_price_inr,status,cover_media_id,published_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (c["id"], b.slug, b.name, b.short_description, b.description, b.starting_price_inr,
             "published" if b.publish else "draft", b.asset_ids[0] if b.asset_ids else None, datetime.now(timezone.utc) if b.publish else None), one=True)["id"]
    for i, a in enumerate(b.asset_ids): q("INSERT INTO product_media(product_id,asset_id,sort_order,is_cover) VALUES (%s,%s,%s,%s)", (pid, a, i, i == 0))
    for t in b.tag_slugs: q("INSERT INTO product_tag SELECT %s,id,CASE WHEN slug='new-arrival' THEN now()+interval '30 days' END FROM tag WHERE slug=%s", (pid, t))
    return {"id": str(pid)}

# ---------- admin: session restore, categories, products, tags ----------
@app.get("/admin/me")
def me(aa_session: Optional[str] = Cookie(None), _=Depends(admin)):
    return q("SELECT csrf FROM admin_session WHERE token_hash=%s", (hashlib.sha256(aa_session.encode()).digest(),), one=True)

@app.get("/admin/tags")
def admin_tags(_=Depends(admin)): return q("SELECT slug,label FROM tag ORDER BY is_system DESC,label")

@app.get("/admin/categories")
def admin_categories(_=Depends(admin)): return q("SELECT slug,name,is_active FROM category ORDER BY sort_order")

class CatPatch(BaseModel): name: Optional[str] = None; is_active: Optional[bool] = None

@app.patch("/admin/categories/{slug}")
def patch_category(slug: str, b: CatPatch, _=Depends(admin)):
    q("UPDATE category SET name=COALESCE(%s,name), is_active=COALESCE(%s,is_active) WHERE slug=%s", (b.name, b.is_active, slug)); return {"ok": True}

@app.get("/admin/products")
def admin_products(_=Depends(admin)):
    return q("""SELECT p.id,p.slug,p.name,p.status::text,p.starting_price_inr,p.cover_media_id,c.name AS category
                FROM product p JOIN category c ON c.id=p.category_id ORDER BY p.created_at DESC""")

class ProductPatch(BaseModel):
    name: Optional[str] = None; short_description: Optional[str] = None; description: Optional[str] = None
    starting_price_inr: Optional[float] = None; clear_price: bool = False; status: Optional[str] = None

@app.patch("/admin/products/{pid}")
def patch_product(pid: str, b: ProductPatch, _=Depends(admin)):
    if b.status not in (None, "draft", "published", "archived"): raise HTTPException(422, "Bad status")
    if b.status == "published" and not q("SELECT 1 FROM product WHERE id=%s AND cover_media_id IS NOT NULL", (pid,), one=True):
        raise HTTPException(422, "Add a photo before publishing")
    q("""UPDATE product SET name=COALESCE(%s,name), short_description=COALESCE(%s,short_description), description=COALESCE(%s,description),
         starting_price_inr=CASE WHEN %s THEN NULL ELSE COALESCE(%s,starting_price_inr) END, status=COALESCE(%s::product_status,status),
         published_at=CASE WHEN %s='published' AND published_at IS NULL THEN now() ELSE published_at END WHERE id=%s""",
      (b.name, b.short_description, b.description, b.clear_price, b.starting_price_inr, b.status, b.status, pid))
    return {"ok": True}

@app.delete("/admin/products/{pid}")
def delete_product(pid: str, _=Depends(admin)):
    q("DELETE FROM product WHERE id=%s", (pid,)); return {"ok": True}
