-- CENG465 Replication Project — Full Relational Schema
-- Supports INSERT / UPDATE / DELETE with version + operation_id tracking on every table.
-- Safe to re-run: drops existing tables then recreates cleanly.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── Drop in reverse dependency order ──────────────────────────────────────────
DROP TABLE IF EXISTS operation_log  CASCADE;
DROP TABLE IF EXISTS order_items    CASCADE;
DROP TABLE IF EXISTS orders         CASCADE;
DROP TABLE IF EXISTS products       CASCADE;
DROP TABLE IF EXISTS categories     CASCADE;
DROP TABLE IF EXISTS customers      CASCADE;

-- ── customers ──────────────────────────────────────────────────────────────────
CREATE TABLE customers (
    id            UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT           NOT NULL,
    email         TEXT           NOT NULL UNIQUE,
    phone         TEXT,
    address       TEXT,
    version       INT            NOT NULL DEFAULT 1,
    operation_id  UUID           NOT NULL DEFAULT gen_random_uuid(),
    last_updated  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    deleted       BOOLEAN        NOT NULL DEFAULT FALSE
);

-- ── categories ─────────────────────────────────────────────────────────────────
CREATE TABLE categories (
    id            UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT           NOT NULL UNIQUE,
    description   TEXT,
    version       INT            NOT NULL DEFAULT 1,
    operation_id  UUID           NOT NULL DEFAULT gen_random_uuid(),
    last_updated  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    deleted       BOOLEAN        NOT NULL DEFAULT FALSE
);

-- ── products ───────────────────────────────────────────────────────────────────
CREATE TABLE products (
    id            UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    category_id   UUID           NOT NULL REFERENCES categories(id),
    name          TEXT           NOT NULL,
    description   TEXT,
    price         NUMERIC(10,2)  NOT NULL,
    stock         INT            NOT NULL DEFAULT 0,
    version       INT            NOT NULL DEFAULT 1,
    operation_id  UUID           NOT NULL DEFAULT gen_random_uuid(),
    last_updated  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    deleted       BOOLEAN        NOT NULL DEFAULT FALSE,
    CONSTRAINT products_price_nonneg CHECK (price >= 0),
    CONSTRAINT products_stock_nonneg CHECK (stock >= 0)
);

-- ── orders ─────────────────────────────────────────────────────────────────────
CREATE TABLE orders (
    id            UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id   UUID           NOT NULL REFERENCES customers(id),
    status        TEXT           NOT NULL DEFAULT 'pending',
    total_amount  NUMERIC(10,2)  NOT NULL DEFAULT 0,
    version       INT            NOT NULL DEFAULT 1,
    operation_id  UUID           NOT NULL DEFAULT gen_random_uuid(),
    last_updated  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    deleted       BOOLEAN        NOT NULL DEFAULT FALSE,
    CONSTRAINT orders_status_valid CHECK (
        status IN ('pending', 'paid', 'shipped', 'delivered', 'cancelled')
    ),
    CONSTRAINT orders_total_nonneg CHECK (total_amount >= 0)
);

-- ── order_items ────────────────────────────────────────────────────────────────
CREATE TABLE order_items (
    id            UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id      UUID           NOT NULL REFERENCES orders(id),
    product_id    UUID           NOT NULL REFERENCES products(id),
    quantity      INT            NOT NULL,
    unit_price    NUMERIC(10,2)  NOT NULL,
    version       INT            NOT NULL DEFAULT 1,
    operation_id  UUID           NOT NULL DEFAULT gen_random_uuid(),
    last_updated  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    deleted       BOOLEAN        NOT NULL DEFAULT FALSE,
    CONSTRAINT order_items_qty_positive CHECK (quantity > 0),
    CONSTRAINT order_items_price_nonneg CHECK (unit_price >= 0)
);

-- ── operation_log ──────────────────────────────────────────────────────────────
-- Tracks every write across all business tables for replication analysis.
CREATE TABLE operation_log (
    id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    table_name            TEXT        NOT NULL,
    record_id             UUID,
    operation_type        TEXT        NOT NULL,
    version               INT,
    leader_write_time     TIMESTAMPTZ NOT NULL,
    follower_visible_time TIMESTAMPTZ,
    replication_delay_ms  INT,
    leader_snapshot       JSONB,
    follower_snapshot     JSONB,
    notes                 TEXT,
    CONSTRAINT oplog_type_valid CHECK (
        operation_type IN ('INSERT', 'UPDATE', 'DELETE')
    ),
    CONSTRAINT oplog_table_valid CHECK (
        table_name IN ('customers', 'categories', 'products', 'orders', 'order_items')
    )
);

-- ── Indexes ────────────────────────────────────────────────────────────────────
CREATE INDEX idx_customers_email          ON customers    (email);
CREATE INDEX idx_customers_operation_id   ON customers    (operation_id);

CREATE INDEX idx_categories_operation_id  ON categories   (operation_id);

CREATE INDEX idx_products_category_id     ON products     (category_id);
CREATE INDEX idx_products_operation_id    ON products     (operation_id);

CREATE INDEX idx_orders_customer_id       ON orders       (customer_id);
CREATE INDEX idx_orders_status            ON orders       (status);
CREATE INDEX idx_orders_operation_id      ON orders       (operation_id);

CREATE INDEX idx_order_items_order_id     ON order_items  (order_id);
CREATE INDEX idx_order_items_product_id   ON order_items  (product_id);
CREATE INDEX idx_order_items_operation_id ON order_items  (operation_id);

CREATE INDEX idx_oplog_record_id          ON operation_log (record_id);
CREATE INDEX idx_oplog_table_name         ON operation_log (table_name);
CREATE INDEX idx_oplog_leader_write_time  ON operation_log (leader_write_time);
