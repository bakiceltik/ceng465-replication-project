CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY,
    customer_name TEXT NOT NULL,
    product_name TEXT NOT NULL,
    quantity INT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    version INT NOT NULL DEFAULT 1,
    operation_id UUID NOT NULL,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT orders_quantity_positive CHECK (quantity > 0),
    CONSTRAINT orders_status_valid CHECK (
        status IN ('pending', 'paid', 'shipped', 'delivered', 'cancelled')
    )
);

CREATE TABLE IF NOT EXISTS operation_log (
    id UUID PRIMARY KEY,
    order_id UUID,
    operation_type TEXT NOT NULL,
    version INT,
    leader_write_time TIMESTAMPTZ NOT NULL,
    follower_visible_time TIMESTAMPTZ,
    replication_delay_ms INT,
    leader_snapshot JSONB,
    follower_snapshot JSONB,
    notes TEXT,
    CONSTRAINT operation_log_operation_type_valid CHECK (
        operation_type IN ('INSERT', 'UPDATE', 'DELETE')
    )
);

CREATE INDEX IF NOT EXISTS idx_orders_operation_id ON orders (operation_id);
CREATE INDEX IF NOT EXISTS idx_operation_log_order_id ON operation_log (order_id);
CREATE INDEX IF NOT EXISTS idx_operation_log_leader_write_time
    ON operation_log (leader_write_time);
