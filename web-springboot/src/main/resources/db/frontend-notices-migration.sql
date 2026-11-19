-- Additive and repeatable. Apply after p0-migration.sql, before this release.
-- Reading a notice never changes abnormal_event.status or detection metadata.
CREATE TABLE IF NOT EXISTS alarm_notice_read (
  user_id BIGINT NOT NULL,
  alarm_id BIGINT NOT NULL,
  read_at DATETIME(3) NOT NULL,
  PRIMARY KEY(user_id,alarm_id)
);
