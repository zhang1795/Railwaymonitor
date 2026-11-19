ALTER TABLE camera ADD COLUMN active_name VARCHAR(100) GENERATED ALWAYS AS (CASE WHEN deleted=0 THEN LOWER(TRIM(name)) ELSE NULL END);
CREATE UNIQUE INDEX uq_camera_active_name ON camera(active_name);
CREATE INDEX ix_p1_event_time ON abnormal_event(deleted,event_time,id);
CREATE INDEX ix_p1_camera_time ON abnormal_event(camera_id,deleted,event_time,id);
CREATE INDEX ix_p1_status_time ON abnormal_event(deleted,status,event_time,id);
CREATE INDEX ix_p1_created ON abnormal_event(deleted,create_time);
CREATE INDEX ix_risk_track_alarm ON risk_track(alarm_id,state);
CREATE INDEX ix_risk_session ON risk_incident(session_id,state);
