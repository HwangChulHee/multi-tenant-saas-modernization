CREATE TABLE menus (
    id text PRIMARY KEY,
    name text NOT NULL,
    price_cents integer NOT NULL CHECK (price_cents >= 0)
);

CREATE TABLE orders (
    id uuid PRIMARY KEY,
    idempotency_key varchar(128) UNIQUE NOT NULL,
    menu_id text NOT NULL REFERENCES menus,
    quantity integer NOT NULL CHECK (quantity BETWEEN 1 AND 100),
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'FULFILLED')),
    request_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE outbox_events (
    event_id uuid PRIMARY KEY,
    order_id uuid UNIQUE NOT NULL REFERENCES orders,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    attempts integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE processed_events (
    event_id uuid PRIMARY KEY,
    order_id uuid UNIQUE NOT NULL REFERENCES orders,
    processed_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO menus (id, name, price_cents) VALUES ('menu-1', :'brand' || ' combo', 1200);
