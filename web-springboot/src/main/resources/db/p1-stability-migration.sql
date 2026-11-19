-- Repeatable/additive; apply after p1-alarm-migration.sql. Back up first.
CREATE TABLE IF NOT EXISTS alarm_edit_version (
 alarm_id BIGINT PRIMARY KEY, version BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS monitoring_metric (
 camera_id BIGINT PRIMARY KEY, session_id VARCHAR(32) NOT NULL,
 reported_at DATETIME(3) NOT NULL, metrics TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS monitoring_health_sample (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, camera_id BIGINT NOT NULL,
 session_id VARCHAR(32) NOT NULL, enabled BOOLEAN NOT NULL,
 state VARCHAR(30) NOT NULL, observed_at DATETIME(3) NOT NULL,
 INDEX ix_health_camera_time(camera_id,observed_at), INDEX ix_health_time(observed_at)
);
CREATE TABLE IF NOT EXISTS monitoring_fault (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, camera_id BIGINT NOT NULL,
 opened_at DATETIME(3) NOT NULL, last_seen DATETIME(3) NOT NULL,
 recovered_at DATETIME(3) NULL, closed_reason VARCHAR(50) NULL, reason VARCHAR(200) NOT NULL,
 INDEX ix_fault_camera(camera_id,recovered_at)
);
CREATE TABLE IF NOT EXISTS monitoring_fault_receipt (
 user_id BIGINT NOT NULL, fault_id BIGINT NOT NULL, read_at DATETIME(3) NOT NULL,
 PRIMARY KEY(user_id,fault_id)
);
CREATE TABLE IF NOT EXISTS recording_clip (
 id VARCHAR(64) PRIMARY KEY, worker_id VARCHAR(64) NOT NULL,
 camera_id BIGINT NOT NULL, session_id VARCHAR(32) NOT NULL,
 file_name VARCHAR(160) NOT NULL, sha256 VARCHAR(64) NOT NULL, bytes BIGINT NOT NULL,
 started_at DATETIME(3) NOT NULL, ended_at DATETIME(3) NOT NULL,
 registered_at DATETIME(3) NOT NULL, expired_at DATETIME(3) NULL,
 UNIQUE KEY uq_recording_file(worker_id,file_name),
 INDEX ix_recording_camera_time(camera_id,ended_at,id), INDEX ix_recording_expiry(expired_at,ended_at)
);
CREATE TABLE IF NOT EXISTS notification_delivery (
 id VARCHAR(32) PRIMARY KEY, entity_type VARCHAR(20) NOT NULL, entity_id BIGINT NOT NULL,
 channel VARCHAR(20) NOT NULL, target VARCHAR(200) NOT NULL, payload TEXT NOT NULL,
 status VARCHAR(30) NOT NULL, phase VARCHAR(10) NOT NULL DEFAULT 'SEND', attempts INTEGER NOT NULL DEFAULT 0,
 next_at DATETIME(3) NOT NULL, lease_token VARCHAR(32) NULL, lease_until DATETIME(3) NULL,
 provider_id VARCHAR(100) NULL, sent_at DATETIME(3) NULL, error VARCHAR(160) NOT NULL DEFAULT '',
 created_at DATETIME(3) NOT NULL, updated_at DATETIME(3) NOT NULL,
 UNIQUE KEY uq_delivery(entity_type,entity_id,channel,target), INDEX ix_delivery_due(status,next_at)
);
