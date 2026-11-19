-- Additive and repeatable. Version rows and camera revision rows are immutable.
CREATE TABLE IF NOT EXISTS risk_template_version (
 template_id VARCHAR(36) NOT NULL, version_no INT NOT NULL, name VARCHAR(80) NOT NULL,
 parameters TEXT NOT NULL, actor_id BIGINT NULL, published_at DATETIME(3) NOT NULL,
 PRIMARY KEY(template_id,version_no)
);
CREATE TABLE IF NOT EXISTS risk_template_default (
 singleton_id INT PRIMARY KEY, revision BIGINT NOT NULL, template_id VARCHAR(36) NULL,
 version_no INT NULL, actor_id BIGINT NULL, updated_at DATETIME(3) NOT NULL
);
CREATE TABLE IF NOT EXISTS camera_risk_revision (
 camera_id BIGINT NOT NULL, revision BIGINT NOT NULL, template_id VARCHAR(36) NULL,
 policy TEXT NOT NULL, actor_id BIGINT NULL, changed_at DATETIME(3) NOT NULL,
 PRIMARY KEY(camera_id,revision), INDEX ix_camera_template(template_id,camera_id)
);
INSERT IGNORE INTO risk_template_version VALUES
 ('livestock',1,'牲畜侵入','{"classes":[2],"confidence":0.7,"dwellSeconds":2,"graceSeconds":3,"reminderSeconds":60,"level":2,"escalateSeconds":180}',NULL,CURRENT_TIMESTAMP),
 ('rockfall',1,'落石监测','{"classes":[7],"confidence":0.65,"dwellSeconds":0,"graceSeconds":3,"reminderSeconds":60,"level":3,"escalateSeconds":60}',NULL,CURRENT_TIMESTAMP);
INSERT IGNORE INTO risk_template_default VALUES (1,0,NULL,NULL,NULL,CURRENT_TIMESTAMP);
-- Preserve the last pre-migration camera configuration without inventing its author.
INSERT IGNORE INTO camera_risk_revision(camera_id,revision,policy,changed_at)
 SELECT camera_id,revision,policy,updated_at FROM camera_risk_rule;
