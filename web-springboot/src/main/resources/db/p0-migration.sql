-- Apply ONCE to an existing baseline database after backup. No DROP statements.
-- Test schema uses the same additions. Historical events receive no synthetic key.
ALTER TABLE abnormal_event ADD COLUMN source_key VARCHAR(64) NULL;
ALTER TABLE abnormal_event ADD COLUMN first_seen DATETIME(3) NULL;
ALTER TABLE abnormal_event ADD COLUMN last_seen DATETIME(3) NULL;
ALTER TABLE abnormal_event ADD COLUMN detection_state VARCHAR(20) NULL;
ALTER TABLE abnormal_event ADD COLUMN detected_type VARCHAR(50) NULL;
ALTER TABLE abnormal_event ADD COLUMN confidence DOUBLE NULL;
ALTER TABLE abnormal_event ADD COLUMN manual_override BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE abnormal_event ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0;
-- Keep source identity for events delivered after device retirement.
ALTER TABLE camera ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0;
CREATE UNIQUE INDEX uq_abnormal_source ON abnormal_event(source_key);
CREATE INDEX ix_abnormal_time ON abnormal_event(event_time,id);
CREATE INDEX ix_abnormal_camera_time ON abnormal_event(camera_id,event_time);
ALTER TABLE `user` ADD COLUMN security_version BIGINT NOT NULL DEFAULT 0;
ALTER TABLE `user` ADD COLUMN password_change_required BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE monitoring_task (
  camera_id BIGINT PRIMARY KEY, worker_id VARCHAR(64) NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT FALSE, generation BIGINT NOT NULL DEFAULT 1,
  session_id VARCHAR(32) NOT NULL, state VARCHAR(20) NOT NULL DEFAULT 'STOPPED',
  revision BIGINT NOT NULL DEFAULT -1, error VARCHAR(500) NULL,
  last_status_at DATETIME(3) NULL, updated_at DATETIME(3) NOT NULL,
  pending_events BIGINT NOT NULL DEFAULT 0,
  retry_count INTEGER NOT NULL DEFAULT 0, next_retry_at DATETIME(3) NULL
);
CREATE TABLE monitoring_session (
  session_id VARCHAR(32) PRIMARY KEY, camera_id BIGINT NOT NULL,
  worker_id VARCHAR(64) NOT NULL, generation BIGINT NOT NULL,
  created_at DATETIME(3) NOT NULL, ended_at DATETIME(3) NULL, end_reason VARCHAR(100) NULL
);
CREATE TABLE detection_receipt (
  worker_id VARCHAR(64) NOT NULL, event_id VARCHAR(64) NOT NULL,
  payload_hash VARCHAR(64) NOT NULL, payload TEXT NOT NULL,
  status VARCHAR(20) NOT NULL, reason VARCHAR(500) NULL,
  received_at DATETIME(3) NOT NULL, PRIMARY KEY(worker_id,event_id)
);
CREATE INDEX ix_receipt_received ON detection_receipt(received_at);
CREATE TABLE detection_rejection (
  payload_hash VARCHAR(64) PRIMARY KEY, worker_id VARCHAR(64) NOT NULL,
  event_id VARCHAR(64) NULL, reason VARCHAR(500) NOT NULL, payload TEXT NOT NULL,
  received_at DATETIME(3) NOT NULL
);
CREATE TABLE detection_track (
  source_key VARCHAR(64) PRIMARY KEY, session_id VARCHAR(32) NOT NULL,
  sequence_no BIGINT NOT NULL, state VARCHAR(20) NOT NULL,
  snapshot TEXT NOT NULL, alarm_id BIGINT NOT NULL
);
CREATE TABLE preview_grant (
  token_hash VARCHAR(64) PRIMARY KEY, user_id BIGINT NOT NULL,
  session_id VARCHAR(128) NOT NULL, security_version BIGINT NOT NULL,
  expires_at DATETIME(3) NOT NULL
);
