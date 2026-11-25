CREATE EXTENSION IF NOT EXISTS pgcrypto; CREATE EXTENSION IF NOT EXISTS citext; CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE TYPE product_status AS ENUM ('draft','published','archived');
CREATE TYPE enquiry_status AS ENUM ('new','contacted','in_discussion','won','closed','spam');
CREATE SEQUENCE enquiry_seq START 1;

CREATE TABLE admin_user (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), email citext UNIQUE NOT NULL, password_hash text NOT NULL,
  failed_attempts int NOT NULL DEFAULT 0, locked_until timestamptz, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE admin_session (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES admin_user ON DELETE CASCADE,
  token_hash bytea UNIQUE NOT NULL, csrf text NOT NULL, last_seen_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL);

CREATE TABLE media_asset (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), kind text NOT NULL DEFAULT 'image', created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE media_blob (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), asset_id uuid NOT NULL REFERENCES media_asset ON DELETE CASCADE,
  variant text NOT NULL, mime_type text NOT NULL, byte_size int NOT NULL, etag text NOT NULL, UNIQUE (asset_id, variant));
CREATE TABLE media_chunk (blob_id uuid NOT NULL REFERENCES media_blob ON DELETE CASCADE, seq int NOT NULL, data bytea NOT NULL, PRIMARY KEY (blob_id, seq));

CREATE TABLE category (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), slug text UNIQUE NOT NULL, name text NOT NULL, description text,
  cover_media_id uuid REFERENCES media_asset, sort_order int NOT NULL DEFAULT 0, is_active boolean NOT NULL DEFAULT true);
CREATE TABLE product (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), category_id uuid NOT NULL REFERENCES category, slug text UNIQUE NOT NULL,
  name text NOT NULL, short_description text, description text, starting_price_inr numeric(10,2) CHECK (starting_price_inr >= 0),
  status product_status NOT NULL DEFAULT 'draft', sort_order int NOT NULL DEFAULT 0, cover_media_id uuid REFERENCES media_asset,
  created_at timestamptz NOT NULL DEFAULT now(), published_at timestamptz);
CREATE INDEX ON product (status, category_id, sort_order);
CREATE INDEX ON product USING gin (name gin_trgm_ops);
CREATE TABLE tag (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), slug text UNIQUE NOT NULL, label text NOT NULL, style text NOT NULL DEFAULT 'neutral', is_system boolean NOT NULL DEFAULT false);
CREATE TABLE product_tag (product_id uuid REFERENCES product ON DELETE CASCADE, tag_id uuid REFERENCES tag ON DELETE CASCADE, expires_at timestamptz, PRIMARY KEY (product_id, tag_id));
CREATE TABLE product_media (product_id uuid REFERENCES product ON DELETE CASCADE, asset_id uuid REFERENCES media_asset, sort_order int NOT NULL DEFAULT 0,
  is_cover boolean NOT NULL DEFAULT false, alt_text text, PRIMARY KEY (product_id, asset_id));
CREATE TABLE site_setting (key text PRIMARY KEY, value jsonb NOT NULL);

CREATE TABLE customer_enquiry (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), reference_code text UNIQUE NOT NULL,
  product_id uuid REFERENCES product ON DELETE SET NULL, product_name_snapshot text, customer_name text,
  whatsapp_number_enc bytea NOT NULL, whatsapp_number_hash bytea NOT NULL, requirements text NOT NULL, needed_by date, reason text,
  status enquiry_status NOT NULL DEFAULT 'new', admin_notes text, consent_text_version text NOT NULL, consented_at timestamptz NOT NULL DEFAULT now(),
  closed_at timestamptz, created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX ON customer_enquiry (status, created_at DESC);

INSERT INTO tag (slug,label,style,is_system) VALUES ('best-seller','Best Seller','coral',true),('new-arrival','New Arrival','yellow',true);
INSERT INTO site_setting VALUES ('whatsapp_number','"919373567492"'),('instagram_url','"https://www.instagram.com/meenakshiagrawal2025"'),
 ('enquiry_mode','"form_and_chat"'),('enquiry_alert_email','"smileforever5@gmail.com"'),('retention_months','6'),
 ('shipping_note','"Final price depends on your design. Shipping charged at actuals. Delivery date confirmed on WhatsApp."');
INSERT INTO category (slug,name,sort_order) VALUES ('keyrings','Keyrings',1),('bookmarks','Bookmarks',2),('name-plates','Name plates',3),('wall-clocks','Wall clocks',4),
 ('earrings','Earrings',5),('bangles','Bangles',6),('bag-tags','Bag tags',7),('shubh-labh','Shubh Labh',8),('toran','Toran',9),('car-dashboard-idols','Car dashboard idols',10);
