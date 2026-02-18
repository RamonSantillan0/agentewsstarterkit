from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

# NOTE:
# This bootstrap DDL is intentionally kept in-code (idempotent) so the starter-kit
# can run on a fresh MySQL instance without migrations.
# It MUST stay aligned with the MySQL stores:
# - app/core/session_store_mysql.py
# - app/core/dedupe_mysql.py
# - app/core/audit_writer_mysql.py
# - app/agent/confirmations_db.py
# - app/plugins/customer_registration_tools.py (optional but shipped)

DDL = [
    # ------------------------------------------------------------
    # sessions (used by MySQLSessionStore)
    # ------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS sessions (
      session_id VARCHAR(128) NOT NULL PRIMARY KEY,
      history_json JSON NULL,
      facts_json JSON NULL,
      expires_at TIMESTAMP NULL,
      updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      INDEX idx_sessions_expires (expires_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    # ------------------------------------------------------------
    # audit_events (append-only) (used by MySQLAuditWriter)
    # ------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS audit_events (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
      request_id VARCHAR(64) NOT NULL,
      session_id VARCHAR(128) NOT NULL,
      type VARCHAR(32) NOT NULL,
      channel VARCHAR(32) NULL,
      intent VARCHAR(80) NULL,
      tool_name VARCHAR(120) NULL,
      confirmed TINYINT(1) NULL,
      payload_json JSON NOT NULL,
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      INDEX idx_audit_session_created (session_id, created_at),
      INDEX idx_audit_request (request_id),
      INDEX idx_audit_type_created (type, created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    # ------------------------------------------------------------
    # dedupe_messages (used by MySQLDedupeStore)
    # ------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS dedupe_messages (
      provider VARCHAR(64) NOT NULL,
      message_id VARCHAR(200) NOT NULL,
      payload_hash CHAR(64) NULL,
      first_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      expires_at TIMESTAMP NULL,
      PRIMARY KEY (provider, message_id),
      INDEX idx_dedupe_expires (expires_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    # ------------------------------------------------------------
    # pending_confirmations (used by confirmations_store)
    # ------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS pending_confirmations (
      token VARCHAR(128) PRIMARY KEY,
      session_id VARCHAR(128) NOT NULL,
      tool_name VARCHAR(80) NOT NULL,
      tool_args_json JSON NOT NULL,
      status ENUM('pending','consumed','expired') NOT NULL DEFAULT 'pending',
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      expires_at TIMESTAMP NULL,
      consumed_at TIMESTAMP NULL,
      INDEX idx_conf_session_status (session_id, status),
      INDEX idx_conf_expires (expires_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    # ------------------------------------------------------------
    # customers + email_verifications (used by customer registration tools)
    # ------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS customers (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
      display_name VARCHAR(200) NOT NULL,
      email VARCHAR(255) NOT NULL,
      phone VARCHAR(50) NULL,
      status ENUM('pending','verified') NOT NULL DEFAULT 'pending',
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      UNIQUE KEY uq_customers_email (email)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS email_verifications (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
      customer_id BIGINT UNSIGNED NOT NULL,
      code_hash CHAR(64) NOT NULL,
      expires_at TIMESTAMP NOT NULL,
      attempts INT NOT NULL DEFAULT 0,
      used_at TIMESTAMP NULL,
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      INDEX idx_ev_customer_used (customer_id, used_at),
      INDEX idx_ev_expires (expires_at),
      CONSTRAINT fk_ev_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
        ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
]


def ensure_tables(engine: Engine) -> None:
    """Run idempotent DDL statements."""
    with engine.begin() as conn:
        for stmt in DDL:
            conn.execute(text(stmt))
