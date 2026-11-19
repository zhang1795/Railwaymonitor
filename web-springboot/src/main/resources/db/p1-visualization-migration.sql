-- Additive and repeatable. Back up before applying to the business database.
CREATE TABLE IF NOT EXISTS recording_analysis (
 clip_id VARCHAR(64) PRIMARY KEY,
 model_sha256 VARCHAR(64) NOT NULL,
 frame_count INTEGER NOT NULL,
 manifest_sha256 VARCHAR(64) NOT NULL,
 manifest_bytes BIGINT NOT NULL,
 manifest_json MEDIUMTEXT NULL
);
