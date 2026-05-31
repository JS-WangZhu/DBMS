CREATE TABLE user_menu_permissions (
        created_at DATETIME NOT NULL DEFAULT now(),
        updated_at DATETIME NOT NULL DEFAULT now(),
        id INTEGER NOT NULL AUTO_INCREMENT,
        user_id INTEGER NOT NULL,
        menu_key VARCHAR(64) NOT NULL,
        PRIMARY KEY (id)
);
CREATE TABLE user_cluster_permissions (
        created_at DATETIME NOT NULL DEFAULT now(),
        updated_at DATETIME NOT NULL DEFAULT now(),
        id INTEGER NOT NULL AUTO_INCREMENT,
        user_id INTEGER NOT NULL,
        cluster_id INTEGER NOT NULL,
        can_query BOOL NOT NULL,
        can_change BOOL NOT NULL,
        PRIMARY KEY (id)
);
CREATE TABLE api_keys (
        created_at DATETIME NOT NULL DEFAULT now(),
        updated_at DATETIME NOT NULL DEFAULT now(),
        id INTEGER NOT NULL AUTO_INCREMENT,
        user_id INTEGER NOT NULL,
        name VARCHAR(128) NULL,
        token VARCHAR(128) NOT NULL,
        purpose VARCHAR(32) NOT NULL DEFAULT 'general',
        scopes JSON NULL,
        status VARCHAR(16) NOT NULL,
        last_used_at DATETIME NULL,
        PRIMARY KEY (id),
        UNIQUE (token)
);
CREATE TABLE user_menu_permissions (
        created_at DATETIME NOT NULL DEFAULT now(),
        updated_at DATETIME NOT NULL DEFAULT now(),
        id INTEGER NOT NULL AUTO_INCREMENT,
        user_id INTEGER NOT NULL,
        menu_key VARCHAR(64) NOT NULL,
        PRIMARY KEY (id)
);
CREATE TABLE user_cluster_permissions (
        created_at DATETIME NOT NULL DEFAULT now(),
        updated_at DATETIME NOT NULL DEFAULT now(),
        id INTEGER NOT NULL AUTO_INCREMENT,
        user_id INTEGER NOT NULL,
        cluster_id INTEGER NOT NULL,
        can_query BOOL NOT NULL,
        can_change BOOL NOT NULL,
        PRIMARY KEY (id)
);
CREATE TABLE api_keys (
        created_at DATETIME NOT NULL DEFAULT now(),
        updated_at DATETIME NOT NULL DEFAULT now(),
        id INTEGER NOT NULL AUTO_INCREMENT,
        user_id INTEGER NOT NULL,
        name VARCHAR(128) NULL,
        token VARCHAR(128) NOT NULL,
        purpose VARCHAR(32) NOT NULL DEFAULT 'general',
        scopes JSON NULL,
        status VARCHAR(16) NOT NULL,
        last_used_at DATETIME NULL,
        PRIMARY KEY (id),
        UNIQUE (token)
);
CREATE TABLE role_group_cluster_permissions (
        created_at DATETIME NOT NULL DEFAULT now(),
        updated_at DATETIME NOT NULL DEFAULT now(),
        id INTEGER NOT NULL AUTO_INCREMENT,
        role_group_id INTEGER NOT NULL,
        cluster_id INTEGER NOT NULL,
        can_query BOOL NOT NULL,
        can_change BOOL NOT NULL,
        PRIMARY KEY (id)
);
CREATE TABLE user_role_groups (
        created_at DATETIME NOT NULL DEFAULT now(),
        updated_at DATETIME NOT NULL DEFAULT now(),
        id INTEGER NOT NULL AUTO_INCREMENT,
        user_id INTEGER NOT NULL,
        role_group_id INTEGER NOT NULL,
        PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS sso_configs (
        created_at DATETIME NOT NULL DEFAULT now(),
        updated_at DATETIME NOT NULL DEFAULT now(),
        id INTEGER NOT NULL AUTO_INCREMENT,
        enabled TINYINT(1) NOT NULL DEFAULT 0,
        provider_name VARCHAR(64) NOT NULL DEFAULT 'SSO',
        client_id VARCHAR(255) NOT NULL DEFAULT '',
        client_secret VARCHAR(255) NOT NULL DEFAULT '',
        authorize_url VARCHAR(512) NOT NULL DEFAULT '',
        token_url VARCHAR(512) NOT NULL DEFAULT '',
        userinfo_url VARCHAR(512) NOT NULL DEFAULT '',
        scope VARCHAR(255) NOT NULL DEFAULT 'openid profile email',
        redirect_uri VARCHAR(512) NOT NULL DEFAULT '',
        username_field VARCHAR(64) NOT NULL DEFAULT 'preferred_username',
        email_field VARCHAR(64) NOT NULL DEFAULT 'email',
        display_name_field VARCHAR(64) NOT NULL DEFAULT '',
        PRIMARY KEY (id)
);

-- SSO 用户绑定字段 (users 表扩展)
-- MySQL 8.0 支持多次运行: 若字段已存在会报错，请按需跳过
ALTER TABLE users ADD COLUMN sso_subject  VARCHAR(128) NULL;
ALTER TABLE users ADD COLUMN sso_provider VARCHAR(64)  NULL;
ALTER TABLE users ADD COLUMN email        VARCHAR(128) NULL;
ALTER TABLE users ADD COLUMN display_name VARCHAR(128) NULL;
ALTER TABLE users ADD COLUMN last_login_at DATETIME    NULL;
ALTER TABLE users ADD UNIQUE KEY uk_users_sso_subject (sso_subject);
ALTER TABLE sso_configs ADD COLUMN display_name_field VARCHAR(64) NOT NULL DEFAULT '';

CREATE TABLE `instance_status_configs` (`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
`id` INT NOT NULL AUTO_INCREMENT,
`metric_refresh_timeout_seconds` INT NOT NULL,
`probe_poll_interval_seconds` INT NOT NULL,
PRIMARY KEY (`id`)) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci AUTO_INCREMENT = 2 ROW_FORMAT = Dynamic;

-- MCP开放平台 / 数据访问路由相关字段
-- 如字段已存在，请按需跳过对应 ALTER。
ALTER TABLE api_keys ADD COLUMN name VARCHAR(128) NULL;
ALTER TABLE api_keys ADD COLUMN purpose VARCHAR(32) NOT NULL DEFAULT 'general';
ALTER TABLE api_keys ADD COLUMN scopes JSON NULL;
ALTER TABLE api_keys ADD COLUMN last_used_at DATETIME NULL;
ALTER TABLE db_clusters ADD COLUMN data_access_route_json JSON NULL;
