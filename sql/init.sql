SET FOREIGN_KEY_CHECKS = 0;
SET NAMES utf8mb4;
-- ai_model_configs DDL
DROP TABLE IF EXISTS `ai_model_configs`;
CREATE TABLE `ai_model_configs` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`name` VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`api_url` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`api_key` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`model_name` VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`is_default` TINYINT(1) NULL,
`enabled` TINYINT(1) NULL,
UNIQUE INDEX `name`(`name` ASC) USING BTREE,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 2 ROW_FORMAT = Dynamic;
-- api_keys DDL
DROP TABLE IF EXISTS `api_keys`;
CREATE TABLE `api_keys` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`user_id` INT NOT NULL,
`token` VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`status` VARCHAR(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
UNIQUE INDEX `token`(`token` ASC) USING BTREE,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 5 ROW_FORMAT = Dynamic;
-- audit_logs DDL
DROP TABLE IF EXISTS `audit_logs`;
CREATE TABLE `audit_logs` (`id` BIGINT NOT NULL AUTO_INCREMENT,
`user_id` BIGINT NULL,
`action` VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`target_type` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`target_id` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`detail_json` JSON NULL,
`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP(0),
INDEX `fk_audit_user`(`user_id` ASC) USING BTREE,
INDEX `idx_audit_logs_time`(`created_at` ASC) USING BTREE,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 517 ROW_FORMAT = Dynamic;
-- backup_agents DDL
DROP TABLE IF EXISTS `backup_agents`;
CREATE TABLE `backup_agents` (`id` INT NOT NULL AUTO_INCREMENT,
`name` VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`url` VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL Comment "Agent URL, e.g., http://192.168.1.100:5001",
`description` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`enabled` TINYINT(1) NOT NULL DEFAULT 1,
`is_default` TINYINT(1) NOT NULL DEFAULT 0,
`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP(0),
`api_key` VARCHAR(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
INDEX `idx_backup_agents_enabled`(`enabled` ASC) USING BTREE,
UNIQUE INDEX `uk_backup_agent_name`(`name` ASC) USING BTREE,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 2 ROW_FORMAT = Dynamic;
-- backup_keys DDL
DROP TABLE IF EXISTS `backup_keys`;
CREATE TABLE `backup_keys` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`name` VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`description` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`public_key` TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`private_key` TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
UNIQUE INDEX `name`(`name` ASC) USING BTREE,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 3 ROW_FORMAT = Dynamic;
-- backup_logs DDL
DROP TABLE IF EXISTS `backup_logs`;
CREATE TABLE `backup_logs` (`id` BIGINT NOT NULL AUTO_INCREMENT,
`policy_id` BIGINT NOT NULL,
`started_at` DATETIME NOT NULL,
`finished_at` DATETIME NULL,
`file_path` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`size_bytes` BIGINT NULL,
`status` ENUM("running","success","failed") CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`error_message` TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`extra_json` JSON NULL,
`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP(0),
INDEX `idx_backup_logs_policy_time`(`policy_id` ASC,`created_at` ASC) USING BTREE,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 3702 ROW_FORMAT = Dynamic;
-- backup_notify_targets DDL
DROP TABLE IF EXISTS `backup_notify_targets`;
CREATE TABLE `backup_notify_targets` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`name` VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`channel` VARCHAR(5) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`address` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`enabled` TINYINT(1) NOT NULL,
`extra_json` JSON NULL,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 4 ROW_FORMAT = Dynamic;
-- backup_policies DDL
DROP TABLE IF EXISTS `backup_policies`;
CREATE TABLE `backup_policies` (`id` BIGINT NOT NULL AUTO_INCREMENT,
`name` VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`target_type` ENUM("instance","cluster") CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`target_id` BIGINT NOT NULL,
`db_type` ENUM("mysql","mongodb") CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`backup_type` ENUM("full","incremental") CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'full',
`tool_name` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`backup_tool_config_id` INT NULL,
`cron_expr` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`storage_path` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`retain_days` INT NOT NULL DEFAULT 7,
`compress` TINYINT(1) NOT NULL DEFAULT 1,
`enabled` TINYINT(1) NOT NULL DEFAULT 1,
`s3_storage_config_id` INT NULL,
`backup_agent_id` INT NULL,
`extra_json` JSON NULL,
`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP(0),
INDEX `fk_backup_policy_s3_config`(`s3_storage_config_id` ASC) USING BTREE,
INDEX `fk_backup_policy_tool_config`(`backup_tool_config_id` ASC) USING BTREE,
INDEX `idx_backup_policies_agent_id`(`backup_agent_id` ASC) USING BTREE,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 4 ROW_FORMAT = Dynamic;
-- backup_tool_configs DDL
DROP TABLE IF EXISTS `backup_tool_configs`;
CREATE TABLE `backup_tool_configs` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`name` VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`db_type` VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`tool_path` VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`description` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`enabled` TINYINT(1) NOT NULL,
`backup_agent_id` INT NULL,
INDEX `idx_backup_tool_configs_agent`(`backup_agent_id` ASC) USING BTREE,
UNIQUE INDEX `name`(`name` ASC) USING BTREE,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 5 ROW_FORMAT = Dynamic;
-- db_clusters DDL
DROP TABLE IF EXISTS `db_clusters`;
CREATE TABLE `db_clusters` (`id` BIGINT NOT NULL AUTO_INCREMENT,
`name` VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`db_type` ENUM("mysql","redis","doris","mongodb") CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`description` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP(0),
`namespace` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`ha_domain` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`ha_status_json` JSON NULL,
`business_line` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`environment` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`ha_switch_enabled` TINYINT(1) NOT NULL DEFAULT 0,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 6 ROW_FORMAT = Dynamic;
-- db_instances DDL
DROP TABLE IF EXISTS `db_instances`;
CREATE TABLE `db_instances` (`id` BIGINT NOT NULL AUTO_INCREMENT,
`name` VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`db_type` ENUM("mysql","redis","doris","mongodb") CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`host_input` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`resolved_ip` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`port` INT NOT NULL,
`username` VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`password_encrypted` TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`cluster_id` BIGINT NULL,
`role_label` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`is_read_only` TINYINT(1) NOT NULL DEFAULT 0,
`enabled` TINYINT(1) NOT NULL DEFAULT 1,
`extra_json` JSON NULL,
`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP(0),
`running_status` VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'unknown',
INDEX `fk_instance_cluster`(`cluster_id` ASC) USING BTREE,
INDEX `idx_instances_type`(`db_type` ASC) USING BTREE,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 17 ROW_FORMAT = Dynamic;
-- ha_configs DDL
DROP TABLE IF EXISTS `ha_configs`;
CREATE TABLE `ha_configs` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`name` VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`script_path` VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`description` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`enabled` TINYINT(1) NOT NULL,
`is_default` TINYINT(1) NOT NULL,
`notify_target_ids` JSON NULL,
`command_template` TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
UNIQUE INDEX `name`(`name` ASC) USING BTREE,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 2 ROW_FORMAT = Dynamic;
-- inspection_alerts DDL
DROP TABLE IF EXISTS `inspection_alerts`;
CREATE TABLE `inspection_alerts` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`instance_id` INT NOT NULL,
`cluster_id` INT NULL,
`db_type` VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`issue_key` VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`issue_name` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`severity` VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`status` VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`message` VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`first_seen_at` DATETIME NULL,
`last_seen_at` DATETIME NULL,
`recovered_at` DATETIME NULL,
`last_payload_json` JSON NULL,
`notify_count` INT NOT NULL,
`last_notified_at` DATETIME NULL,
`recovery_notified_at` DATETIME NULL,
INDEX `ix_inspection_alerts_cluster_id`(`cluster_id` ASC) USING BTREE,
INDEX `ix_inspection_alerts_db_type`(`db_type` ASC) USING BTREE,
INDEX `ix_inspection_alerts_instance_id`(`instance_id` ASC) USING BTREE,
UNIQUE INDEX `uq_inspection_alert_instance_issue`(`instance_id` ASC,`issue_key` ASC) USING BTREE,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 18 ROW_FORMAT = Dynamic;
-- inspection_configs DDL
DROP TABLE IF EXISTS `inspection_configs`;
CREATE TABLE `inspection_configs` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`enabled` TINYINT(1) NOT NULL,
`interval_seconds` INT NOT NULL,
`collect_timeout_seconds` INT NOT NULL,
`notify_enabled` TINYINT(1) NOT NULL,
`notify_recovery` TINYINT(1) NOT NULL,
`notify_target_ids_json` JSON NULL,
`muted_cluster_ids_json` JSON NULL,
`last_run_at` DATETIME NULL,
`last_run_summary_json` JSON NULL,
`extra_json` JSON NULL,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 2 ROW_FORMAT = Dynamic;
-- instance_status_configs DDL
DROP TABLE IF EXISTS `instance_status_configs`;
CREATE TABLE `instance_status_configs` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`metric_refresh_timeout_seconds` INT NOT NULL,
`probe_poll_interval_seconds` INT NOT NULL,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 2 ROW_FORMAT = Dynamic;
-- monitor_snapshots_doris DDL
DROP TABLE IF EXISTS `monitor_snapshots_doris`;
CREATE TABLE `monitor_snapshots_doris` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`instance_id` INT NOT NULL,
`metric_type` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`payload_json` JSON NOT NULL,
`collected_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
INDEX `ix_monitor_snapshots_doris_collected_at`(`collected_at` ASC) USING BTREE,
INDEX `ix_monitor_snapshots_doris_instance_id`(`instance_id` ASC) USING BTREE,
INDEX `ix_monitor_snapshots_doris_metric_type`(`metric_type` ASC) USING BTREE,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 1 ROW_FORMAT = Dynamic;
-- monitor_snapshots_mongodb DDL
DROP TABLE IF EXISTS `monitor_snapshots_mongodb`;
CREATE TABLE `monitor_snapshots_mongodb` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`instance_id` INT NOT NULL,
`metric_type` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`payload_json` JSON NOT NULL,
`collected_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
INDEX `ix_monitor_snapshots_mongodb_collected_at`(`collected_at` ASC) USING BTREE,
INDEX `ix_monitor_snapshots_mongodb_instance_id`(`instance_id` ASC) USING BTREE,
INDEX `ix_monitor_snapshots_mongodb_metric_type`(`metric_type` ASC) USING BTREE,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 35751 ROW_FORMAT = Dynamic;
-- monitor_snapshots_mysql DDL
DROP TABLE IF EXISTS `monitor_snapshots_mysql`;
CREATE TABLE `monitor_snapshots_mysql` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`instance_id` INT NOT NULL,
`metric_type` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`payload_json` JSON NOT NULL,
`collected_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
INDEX `ix_monitor_snapshots_mysql_collected_at`(`collected_at` ASC) USING BTREE,
INDEX `ix_monitor_snapshots_mysql_instance_id`(`instance_id` ASC) USING BTREE,
INDEX `ix_monitor_snapshots_mysql_metric_type`(`metric_type` ASC) USING BTREE,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 18770 ROW_FORMAT = Dynamic;
-- monitor_snapshots_redis DDL
DROP TABLE IF EXISTS `monitor_snapshots_redis`;
CREATE TABLE `monitor_snapshots_redis` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`instance_id` INT NOT NULL,
`metric_type` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`payload_json` JSON NOT NULL,
`collected_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
INDEX `ix_monitor_snapshots_redis_collected_at`(`collected_at` ASC) USING BTREE,
INDEX `ix_monitor_snapshots_redis_instance_id`(`instance_id` ASC) USING BTREE,
INDEX `ix_monitor_snapshots_redis_metric_type`(`metric_type` ASC) USING BTREE,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 48562 ROW_FORMAT = Dynamic;
-- role_group_cluster_permissions DDL
DROP TABLE IF EXISTS `role_group_cluster_permissions`;
CREATE TABLE `role_group_cluster_permissions` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`role_group_id` INT NOT NULL,
`cluster_id` INT NOT NULL,
`can_query` TINYINT(1) NOT NULL,
`can_change` TINYINT(1) NOT NULL,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 6 ROW_FORMAT = Dynamic;
-- role_group_menu_permissions DDL
DROP TABLE IF EXISTS `role_group_menu_permissions`;
CREATE TABLE `role_group_menu_permissions` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`role_group_id` INT NOT NULL,
`menu_key` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
INDEX `role_group_id`(`role_group_id` ASC) USING BTREE,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 24 ROW_FORMAT = Dynamic;
-- role_groups DDL
DROP TABLE IF EXISTS `role_groups`;
CREATE TABLE `role_groups` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`name` VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`description` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
UNIQUE INDEX `name`(`name` ASC) USING BTREE,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 2 ROW_FORMAT = Dynamic;
-- s3_storage_configs DDL
DROP TABLE IF EXISTS `s3_storage_configs`;
CREATE TABLE `s3_storage_configs` (`id` INT NOT NULL AUTO_INCREMENT,
`name` VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`description` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`bucket` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`prefix` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`region` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`endpoint_url` VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`access_key` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`secret_key` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`enabled` TINYINT(1) NOT NULL DEFAULT 1,
`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP(0),
UNIQUE INDEX `uk_s3_config_name`(`name` ASC) USING BTREE,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 2 ROW_FORMAT = Dynamic;
-- sso_configs DDL
DROP TABLE IF EXISTS `sso_configs`;
CREATE TABLE `sso_configs` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`enabled` TINYINT(1) NOT NULL,
`provider_name` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`client_id` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`client_secret` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`authorize_url` VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`token_url` VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`userinfo_url` VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`scope` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`redirect_uri` VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`username_field` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`email_field` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`display_name_field` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 2 ROW_FORMAT = Dynamic;
-- user_cluster_permissions DDL
DROP TABLE IF EXISTS `user_cluster_permissions`;
CREATE TABLE `user_cluster_permissions` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`user_id` INT NOT NULL,
`cluster_id` INT NOT NULL,
`can_query` TINYINT(1) NOT NULL,
`can_change` TINYINT(1) NOT NULL,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 106 ROW_FORMAT = Dynamic;
-- user_menu_permissions DDL
DROP TABLE IF EXISTS `user_menu_permissions`;
CREATE TABLE `user_menu_permissions` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`user_id` INT NOT NULL,
`menu_key` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 128 ROW_FORMAT = Dynamic;
-- user_role_groups DDL
DROP TABLE IF EXISTS `user_role_groups`;
CREATE TABLE `user_role_groups` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`user_id` INT NOT NULL,
`role_group_id` INT NOT NULL,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 2 ROW_FORMAT = Dynamic;
-- users DDL
DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (`id` BIGINT NOT NULL AUTO_INCREMENT,
`username` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
`password_hash` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`role` ENUM("admin","user") CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'user',
`status` ENUM("active","disabled") CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'active',
`auth_source` ENUM("local","ldap","sso") CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'local',
`ldap_dn` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP(0),
`sso_subject` VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`sso_provider` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`email` VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`display_name` VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
`last_login_at` DATETIME NULL,
UNIQUE INDEX `uk_users_sso_subject`(`sso_subject` ASC) USING BTREE,
UNIQUE INDEX `username`(`username` ASC) USING BTREE,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 9 ROW_FORMAT = Dynamic;
-- audit_logs Constraints
ALTER TABLE `audit_logs` 
 ADD CONSTRAINT `fk_audit_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL ON UPDATE NO ACTION;
-- backup_logs Constraints
ALTER TABLE `backup_logs` 
 ADD CONSTRAINT `fk_backup_log_policy` FOREIGN KEY (`policy_id`) REFERENCES `backup_policies` (`id`) ON DELETE NO ACTION ON UPDATE NO ACTION;
-- backup_policies Constraints
ALTER TABLE `backup_policies` 
 ADD CONSTRAINT `fk_backup_policy_agent` FOREIGN KEY (`backup_agent_id`) REFERENCES `backup_agents` (`id`) ON DELETE SET NULL ON UPDATE NO ACTION,
ADD CONSTRAINT `fk_backup_policy_s3_config` FOREIGN KEY (`s3_storage_config_id`) REFERENCES `s3_storage_configs` (`id`) ON DELETE SET NULL ON UPDATE NO ACTION,
ADD CONSTRAINT `fk_backup_policy_tool_config` FOREIGN KEY (`backup_tool_config_id`) REFERENCES `backup_tool_configs` (`id`) ON DELETE SET NULL ON UPDATE NO ACTION;
-- db_instances Constraints
ALTER TABLE `db_instances` 
 ADD CONSTRAINT `fk_instance_cluster` FOREIGN KEY (`cluster_id`) REFERENCES `db_clusters` (`id`) ON DELETE NO ACTION ON UPDATE NO ACTION;
-- role_group_menu_permissions Constraints
ALTER TABLE `role_group_menu_permissions` 
 ADD CONSTRAINT `role_group_menu_permissions_ibfk_1` FOREIGN KEY (`role_group_id`) REFERENCES `role_groups` (`id`) ON DELETE NO ACTION ON UPDATE NO ACTION;
SET FOREIGN_KEY_CHECKS = 1;
