-- Additive/repeatable, after P0 and frontend-notices migrations. Back up first.
CREATE TABLE IF NOT EXISTS camera_risk_rule (
 camera_id BIGINT PRIMARY KEY, revision BIGINT NOT NULL, enabled BOOLEAN NOT NULL,
 policy TEXT NOT NULL, updated_at DATETIME(3) NOT NULL
);
CREATE TABLE IF NOT EXISTS risk_track (
 source_key VARCHAR(64) PRIMARY KEY, session_id VARCHAR(32) NOT NULL,
 sequence_no BIGINT NOT NULL, state VARCHAR(20) NOT NULL, snapshot TEXT NOT NULL,
 alarm_id BIGINT NULL, qualifying_since DATETIME(3) NULL, outside_since DATETIME(3) NULL
);
CREATE TABLE IF NOT EXISTS session_risk_policy (session_id VARCHAR(32) PRIMARY KEY, policy TEXT NOT NULL);
INSERT IGNORE INTO session_risk_policy(session_id,policy)
 SELECT session_id,'{"enabled":false,"classes":[],"roi":[0,0,1,1],"confidence":0.5,"dwellSeconds":2,"graceSeconds":3,"reminderSeconds":60,"level":1,"escalateSeconds":180,"revision":0}'
 FROM monitoring_session;
CREATE TABLE IF NOT EXISTS risk_incident (
 alarm_id BIGINT PRIMARY KEY, camera_id BIGINT NOT NULL, session_id VARCHAR(32) NOT NULL,
 kind VARCHAR(20) NOT NULL, state VARCHAR(20) NOT NULL, risk_level INTEGER NOT NULL,
 risk_since DATETIME(3) NOT NULL, last_inside DATETIME(3) NULL, last_observed DATETIME(3) NOT NULL,
 missing_since DATETIME(3) NULL, policy TEXT NOT NULL, association VARCHAR(40) NOT NULL,
 class_id INTEGER NOT NULL, bbox TEXT NOT NULL, frame_width INTEGER NOT NULL, frame_height INTEGER NOT NULL, last_detection DATETIME(3) NOT NULL,
 INDEX ix_risk_scene(camera_id,session_id,state)
);
CREATE TABLE IF NOT EXISTS alarm_source_link (
 alarm_id BIGINT NOT NULL, source_key VARCHAR(64) NOT NULL, first_sequence BIGINT NOT NULL,
 last_sequence BIGINT NULL, PRIMARY KEY(alarm_id,source_key,first_sequence), INDEX ix_link_source(source_key)
);
CREATE TABLE IF NOT EXISTS alarm_transition (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, alarm_id BIGINT NOT NULL, from_state VARCHAR(20) NULL,
 to_state VARCHAR(20) NOT NULL, reason VARCHAR(200) NOT NULL, observed_at DATETIME(3) NOT NULL,
 INDEX ix_transition_alarm(alarm_id,id)
);
CREATE TABLE IF NOT EXISTS alarm_handling_audit (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, alarm_id BIGINT NOT NULL, user_id BIGINT NOT NULL,
 action VARCHAR(30) NOT NULL, before_status INTEGER NOT NULL, after_status INTEGER NOT NULL,
 result TEXT NULL, created_at DATETIME(3) NOT NULL, INDEX ix_handling_alarm(alarm_id,id)
);
CREATE TABLE IF NOT EXISTS alarm_notice (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, alarm_id BIGINT NOT NULL, kind VARCHAR(20) NOT NULL,
 bucket BIGINT NOT NULL, created_at DATETIME(3) NOT NULL,
 UNIQUE KEY uq_notice(alarm_id,kind,bucket), INDEX ix_notice_alarm(alarm_id,id)
);
CREATE TABLE IF NOT EXISTS alarm_notice_receipt (
 user_id BIGINT NOT NULL, notice_id BIGINT NOT NULL, read_at DATETIME(3) NOT NULL,
 PRIMARY KEY(user_id,notice_id)
);
CREATE TABLE IF NOT EXISTS alarm_evidence (
 id VARCHAR(64) PRIMARY KEY, alarm_id BIGINT NOT NULL, worker_id VARCHAR(64) NOT NULL,
 event_id VARCHAR(32) NOT NULL, file_name VARCHAR(80) NOT NULL, sha256 VARCHAR(64) NOT NULL,
 bytes BIGINT NOT NULL, captured_at DATETIME(3) NOT NULL, created_at DATETIME(3) NOT NULL,
 UNIQUE KEY uq_evidence_event(worker_id,event_id), INDEX ix_evidence_alarm(alarm_id)
);
CREATE TABLE IF NOT EXISTS evidence_storage_lock (id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS worker_evidence_status (
 worker_id VARCHAR(64) PRIMARY KEY, pending_events BIGINT NOT NULL, skipped BIGINT NOT NULL,
 error VARCHAR(200) NOT NULL, reported_at DATETIME(3) NOT NULL
);
INSERT IGNORE INTO evidence_storage_lock VALUES(1);
INSERT IGNORE INTO risk_track(source_key,session_id,sequence_no,state,snapshot,alarm_id)
 SELECT source_key,session_id,sequence_no,state,snapshot,alarm_id FROM detection_track;
-- Existing records keep their original identity and first-notice read receipts.
INSERT IGNORE INTO alarm_notice(alarm_id,kind,bucket,created_at)
 SELECT id,'FIRST',0,COALESCE(create_time,event_time) FROM abnormal_event;
INSERT IGNORE INTO alarm_notice_receipt(user_id,notice_id,read_at)
 SELECT r.user_id,n.id,r.read_at FROM alarm_notice_read r
 JOIN alarm_notice n ON n.alarm_id=r.alarm_id AND n.kind='FIRST' AND n.bucket=0;
