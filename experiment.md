# Experiment Guide — 2 Computers, 2 People

**Person A → Leader**
```
psql "host=35.254.173.105 port=5432 dbname=replication_project user=ceng465 password=ceng465pass"
```

**Person B → Follower**
```
psql "host=136.116.184.77 port=5432 dbname=replication_project user=ceng465 password=ceng465pass"
```

---

## Experiment 1 — Eventual Consistency

**Concept:** Data written to the leader appears on the follower with a delay, but eventually it does appear.

**A (Leader) writes:**
```sql
INSERT INTO customers (name, email)
VALUES ('exp1', 'exp3@test.com')
RETURNING id, name, last_updated;
```

**B (Follower) reads immediately:**
```sql
SELECT name, last_updated FROM customers WHERE email = 'exp1@test.com';
```

**Expected:** First query may return `0 rows`. Run again after 1-2 seconds — the row appears.

**Result:** Follower did not see it immediately but eventually did → Eventual Consistency proven.

---

## Experiment 2 — Monotonic Reads

**Concept:** Reading from the follower repeatedly should never return an older version than one already seen.

**A (Leader) runs 3 updates in sequence:**
```sql
UPDATE customers SET name='v2', version=2, last_updated=NOW() WHERE email='exp1@test.com';
UPDATE customers SET name='v3', version=3, last_updated=NOW() WHERE email='exp1@test.com';
UPDATE customers SET name='v4', version=4, last_updated=NOW() WHERE email='exp1@test.com';
```

**B (Follower) reads after each update:**
```sql
SELECT name, version, last_updated FROM customers WHERE email='exp1@test.com';
```

**Expected:** Version sequence is `2 → 3 → 4`. Never goes backwards like `4 → 3`.

**Result:** Monotonic Read guarantee holds.

---

## Experiment 3 — Read-After-Write Consistency

**Concept:** After a user writes something, reading it back should return the written value. Reading from the follower may violate this guarantee.

**A (Leader) writes, then reads immediately:**
```sql
INSERT INTO customers (name, email)
VALUES ('exp3', 'exp5@test.com')
RETURNING id, name, last_updated;
```

```sql
-- A reads from leader immediately
SELECT name, last_updated FROM customers WHERE email='exp3@test.com';
```

**B (Follower) reads at the same time:**
```sql
SELECT name, last_updated FROM customers WHERE email='exp3@test.com';
```

**Expected:**
- A (leader): sees the row immediately
- B (follower): may not see it yet, appears after a few seconds

**Result:** Reading from the leader guarantees RAW (Read-After-Write) consistency. Reading from the follower does not.

---

## Experiment 4 — Concurrent Writes

**Objective:** Test how concurrent writes to the leader are propagated to the follower.

**A (Leader) performs multiple writes in quick succession:**
```sql
INSERT INTO customers (name, email, version)
VALUES ('cw1', 'cw1@test.com', 1)
RETURNING id, name, version, last_updated;

INSERT INTO customers (name, email, version)
VALUES ('cw2', 'cw2@test.com', 1)
RETURNING id, name, version, last_updated;

INSERT INTO customers (name, email, version)
VALUES ('cw3', 'cw3@test.com', 1)
RETURNING id, name, version, last_updated;
```

**B (Follower) reads to check visibility and order:**
```sql
SELECT name, email, version, last_updated
FROM customers
WHERE email IN ('cw1@test.com', 'cw2@test.com', 'cw3@test.com')
ORDER BY last_updated ASC;
```

**Expected:** The follower should show the records in the same order as they were written on the leader, although some records may appear slightly later due to asynchronous replication.

**Observations:** Note whether the follower preserves write order and whether any rows are temporarily missing during early reads.

**Result:** Concurrent writes should propagate in leader order. Any difference is expected to be about visibility delay, not reordering.

---

## Bonus — Replication Lag Measurement

**A (Leader) runs:**
```sql
SELECT client_addr, write_lag, flush_lag, replay_lag
FROM pg_stat_replication;
```

`replay_lag` → how far behind the follower is (actual replication lag).
