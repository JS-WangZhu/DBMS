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
        token VARCHAR(128) NOT NULL,
        status VARCHAR(16) NOT NULL,
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
        token VARCHAR(128) NOT NULL,
        status VARCHAR(16) NOT NULL,
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
