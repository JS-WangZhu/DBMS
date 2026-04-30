-- dbms_meta.backup_agents definition

CREATE TABLE `backup_agents` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(128) NOT NULL,
  `url` varchar(512) NOT NULL COMMENT 'Agent URL, e.g., http://192.168.1.100:5001',
  `description` varchar(255) DEFAULT NULL,
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `is_default` tinyint(1) NOT NULL DEFAULT '0',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `api_key` varchar(256) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_backup_agent_name` (`name`),
  KEY `idx_backup_agents_enabled` (`enabled`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- dbms_meta.backup_keys definition

CREATE TABLE `backup_keys` (
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(128) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  `public_key` text NOT NULL,
  `private_key` text,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- dbms_meta.backup_notify_targets definition

CREATE TABLE `backup_notify_targets` (
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(128) NOT NULL,
  `channel` varchar(5) NOT NULL,
  `address` varchar(255) NOT NULL,
  `enabled` tinyint(1) NOT NULL,
  `extra_json` json DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- dbms_meta.backup_tool_configs definition

CREATE TABLE `backup_tool_configs` (
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(128) NOT NULL,
  `db_type` varchar(32) NOT NULL,
  `tool_path` varchar(512) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  `enabled` tinyint(1) NOT NULL,
  `backup_agent_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  KEY `idx_backup_tool_configs_agent` (`backup_agent_id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- dbms_meta.db_clusters definition

CREATE TABLE `db_clusters` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(128) NOT NULL,
  `db_type` enum('mysql','redis','doris','mongodb') NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `namespace` varchar(64) NOT NULL DEFAULT 'default',
  `ha_domain` varchar(255) DEFAULT NULL,
  `ha_status_json` json DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- dbms_meta.monitor_snapshots_doris definition

CREATE TABLE `monitor_snapshots_doris` (
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `id` int NOT NULL AUTO_INCREMENT,
  `instance_id` int NOT NULL,
  `metric_type` varchar(64) NOT NULL,
  `payload_json` json NOT NULL,
  `collected_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_monitor_snapshots_doris_instance_id` (`instance_id`),
  KEY `ix_monitor_snapshots_doris_metric_type` (`metric_type`),
  KEY `ix_monitor_snapshots_doris_collected_at` (`collected_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- dbms_meta.monitor_snapshots_mongodb definition

CREATE TABLE `monitor_snapshots_mongodb` (
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `id` int NOT NULL AUTO_INCREMENT,
  `instance_id` int NOT NULL,
  `metric_type` varchar(64) NOT NULL,
  `payload_json` json NOT NULL,
  `collected_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_monitor_snapshots_mongodb_metric_type` (`metric_type`),
  KEY `ix_monitor_snapshots_mongodb_instance_id` (`instance_id`),
  KEY `ix_monitor_snapshots_mongodb_collected_at` (`collected_at`)
) ENGINE=InnoDB AUTO_INCREMENT=25 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- dbms_meta.monitor_snapshots_mysql definition

CREATE TABLE `monitor_snapshots_mysql` (
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `id` int NOT NULL AUTO_INCREMENT,
  `instance_id` int NOT NULL,
  `metric_type` varchar(64) NOT NULL,
  `payload_json` json NOT NULL,
  `collected_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_monitor_snapshots_mysql_metric_type` (`metric_type`),
  KEY `ix_monitor_snapshots_mysql_collected_at` (`collected_at`),
  KEY `ix_monitor_snapshots_mysql_instance_id` (`instance_id`)
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- dbms_meta.monitor_snapshots_redis definition

CREATE TABLE `monitor_snapshots_redis` (
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `id` int NOT NULL AUTO_INCREMENT,
  `instance_id` int NOT NULL,
  `metric_type` varchar(64) NOT NULL,
  `payload_json` json NOT NULL,
  `collected_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_monitor_snapshots_redis_metric_type` (`metric_type`),
  KEY `ix_monitor_snapshots_redis_collected_at` (`collected_at`),
  KEY `ix_monitor_snapshots_redis_instance_id` (`instance_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- dbms_meta.s3_storage_configs definition

CREATE TABLE `s3_storage_configs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(128) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  `bucket` varchar(255) NOT NULL,
  `prefix` varchar(255) DEFAULT NULL,
  `region` varchar(64) DEFAULT NULL,
  `endpoint_url` varchar(512) DEFAULT NULL,
  `access_key` varchar(255) NOT NULL,
  `secret_key` varchar(255) NOT NULL,
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_s3_config_name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- dbms_meta.users definition

CREATE TABLE `users` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `username` varchar(64) NOT NULL,
  `password_hash` varchar(255) DEFAULT NULL,
  `role` enum('admin','user') NOT NULL DEFAULT 'user',
  `status` enum('active','disabled') NOT NULL DEFAULT 'active',
  `auth_source` enum('local','ldap') NOT NULL DEFAULT 'local',
  `ldap_dn` varchar(255) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- dbms_meta.audit_logs definition

CREATE TABLE `audit_logs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint DEFAULT NULL,
  `action` varchar(128) NOT NULL,
  `target_type` varchar(64) DEFAULT NULL,
  `target_id` varchar(64) DEFAULT NULL,
  `detail_json` json DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_audit_logs_time` (`created_at`),
  KEY `fk_audit_user` (`user_id`),
  CONSTRAINT `fk_audit_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=236 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- dbms_meta.backup_policies definition

CREATE TABLE `backup_policies` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(128) NOT NULL,
  `target_type` enum('instance','cluster') NOT NULL,
  `target_id` bigint NOT NULL,
  `db_type` enum('mysql','mongodb') NOT NULL,
  `backup_type` enum('full','incremental') NOT NULL DEFAULT 'full',
  `tool_name` varchar(64) NOT NULL,
  `backup_tool_config_id` int DEFAULT NULL,
  `cron_expr` varchar(64) NOT NULL,
  `storage_path` varchar(255) NOT NULL,
  `retain_days` int NOT NULL DEFAULT '7',
  `compress` tinyint(1) NOT NULL DEFAULT '1',
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `s3_storage_config_id` int DEFAULT NULL,
  `backup_agent_id` int DEFAULT NULL,
  `extra_json` json DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_backup_policy_s3_config` (`s3_storage_config_id`),
  KEY `fk_backup_policy_tool_config` (`backup_tool_config_id`),
  KEY `idx_backup_policies_agent_id` (`backup_agent_id`),
  CONSTRAINT `fk_backup_policy_agent` FOREIGN KEY (`backup_agent_id`) REFERENCES `backup_agents` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_backup_policy_s3_config` FOREIGN KEY (`s3_storage_config_id`) REFERENCES `s3_storage_configs` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_backup_policy_tool_config` FOREIGN KEY (`backup_tool_config_id`) REFERENCES `backup_tool_configs` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- dbms_meta.db_instances definition

CREATE TABLE `db_instances` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(128) NOT NULL,
  `db_type` enum('mysql','redis','doris','mongodb') NOT NULL,
  `host_input` varchar(255) NOT NULL,
  `resolved_ip` varchar(64) DEFAULT NULL,
  `port` int NOT NULL,
  `username` varchar(128) DEFAULT NULL,
  `password_encrypted` text,
  `cluster_id` bigint DEFAULT NULL,
  `role_label` varchar(64) DEFAULT NULL,
  `is_read_only` tinyint(1) NOT NULL DEFAULT '0',
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `extra_json` json DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `running_status` varchar(32) DEFAULT 'unknown',
  PRIMARY KEY (`id`),
  KEY `fk_instance_cluster` (`cluster_id`),
  KEY `idx_instances_type` (`db_type`),
  CONSTRAINT `fk_instance_cluster` FOREIGN KEY (`cluster_id`) REFERENCES `db_clusters` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- dbms_meta.backup_logs definition

CREATE TABLE `backup_logs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `policy_id` bigint NOT NULL,
  `started_at` datetime NOT NULL,
  `finished_at` datetime DEFAULT NULL,
  `file_path` varchar(255) DEFAULT NULL,
  `size_bytes` bigint DEFAULT NULL,
  `status` enum('running','success','failed') NOT NULL,
  `error_message` text,
  `extra_json` json DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_backup_logs_policy_time` (`policy_id`,`created_at`),
  CONSTRAINT `fk_backup_log_policy` FOREIGN KEY (`policy_id`) REFERENCES `backup_policies` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=71 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;