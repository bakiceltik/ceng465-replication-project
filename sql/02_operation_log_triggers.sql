-- CENG465 — operation_log triggers
-- Fires after every INSERT / UPDATE / DELETE on business tables.
-- Captures table_name, operation_type, version, and leader_write_time automatically.

CREATE OR REPLACE FUNCTION fn_log_operation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_op   TEXT;
    v_rec  JSONB;
BEGIN
    IF    TG_OP = 'DELETE' THEN
        v_op  := 'DELETE';
        v_rec := to_jsonb(OLD);
    ELSIF TG_OP = 'UPDATE' THEN
        v_op  := 'UPDATE';
        v_rec := to_jsonb(NEW);
    ELSE
        v_op  := 'INSERT';
        v_rec := to_jsonb(NEW);
    END IF;

    INSERT INTO operation_log (
        table_name,
        record_id,
        operation_type,
        version,
        leader_write_time,
        leader_snapshot
    ) VALUES (
        TG_TABLE_NAME,
        (v_rec->>'id')::UUID,
        v_op,
        (v_rec->>'version')::INT,
        NOW(),
        v_rec
    );

    RETURN NEW;
END;
$$;

-- customers
DROP TRIGGER IF EXISTS trg_oplog_customers ON customers;
CREATE TRIGGER trg_oplog_customers
    AFTER INSERT OR UPDATE OR DELETE ON customers
    FOR EACH ROW EXECUTE FUNCTION fn_log_operation();

-- categories
DROP TRIGGER IF EXISTS trg_oplog_categories ON categories;
CREATE TRIGGER trg_oplog_categories
    AFTER INSERT OR UPDATE OR DELETE ON categories
    FOR EACH ROW EXECUTE FUNCTION fn_log_operation();

-- products
DROP TRIGGER IF EXISTS trg_oplog_products ON products;
CREATE TRIGGER trg_oplog_products
    AFTER INSERT OR UPDATE OR DELETE ON products
    FOR EACH ROW EXECUTE FUNCTION fn_log_operation();

-- orders
DROP TRIGGER IF EXISTS trg_oplog_orders ON orders;
CREATE TRIGGER trg_oplog_orders
    AFTER INSERT OR UPDATE OR DELETE ON orders
    FOR EACH ROW EXECUTE FUNCTION fn_log_operation();

-- order_items
DROP TRIGGER IF EXISTS trg_oplog_order_items ON order_items;
CREATE TRIGGER trg_oplog_order_items
    AFTER INSERT OR UPDATE OR DELETE ON order_items
    FOR EACH ROW EXECUTE FUNCTION fn_log_operation();
