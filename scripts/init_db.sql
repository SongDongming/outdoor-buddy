-- ============================================
-- 户外徒步助手 — 数据库初始化脚本
-- 数据库: PostgreSQL
-- 编码: UTF-8
-- ============================================

-- 创建数据库（如果不存在，需手动执行）
-- CREATE DATABASE outdoor_assistant WITH ENCODING 'UTF8';

-- ============================================
-- 1. 用户表
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- ============================================
-- 2. 路线缓存表
-- ============================================
CREATE TABLE IF NOT EXISTS route_cache (
    id SERIAL PRIMARY KEY,
    keyword VARCHAR(200) NOT NULL,
    route_data JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_route_cache_keyword ON route_cache(keyword);
CREATE INDEX IF NOT EXISTS idx_route_cache_expires ON route_cache(expires_at);

-- ============================================
-- 3. 装备缓存表
-- ============================================
CREATE TABLE IF NOT EXISTS equipment_cache (
    id SERIAL PRIMARY KEY,
    keyword VARCHAR(200) NOT NULL,
    category VARCHAR(50),
    equipment_data JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_equipment_cache_keyword ON equipment_cache(keyword);
CREATE INDEX IF NOT EXISTS idx_equipment_cache_category ON equipment_cache(category);
CREATE INDEX IF NOT EXISTS idx_equipment_cache_expires ON equipment_cache(expires_at);

-- ============================================
-- 4. 收藏表
-- ============================================
CREATE TABLE IF NOT EXISTS favorites (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    fav_type VARCHAR(30) NOT NULL CHECK (fav_type IN ('route', 'equipment', 'plan')),
    title VARCHAR(200),
    content JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_favorites_user_id ON favorites(user_id);
CREATE INDEX IF NOT EXISTS idx_favorites_type ON favorites(fav_type);
CREATE INDEX IF NOT EXISTS idx_favorites_user_type ON favorites(user_id, fav_type);

-- ============================================
-- 5. 查询历史表
-- ============================================
CREATE TABLE IF NOT EXISTS query_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    query_type VARCHAR(30) NOT NULL CHECK (query_type IN ('route', 'equipment', 'ticket', 'weather', 'plan', 'qa')),
    query_params JSONB NOT NULL,
    query_result_summary TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_query_history_user_id ON query_history(user_id);
CREATE INDEX IF NOT EXISTS idx_query_history_type ON query_history(query_type);
CREATE INDEX IF NOT EXISTS idx_query_history_created ON query_history(created_at DESC);

-- ============================================
-- 6. 行程预案表
-- ============================================
CREATE TABLE IF NOT EXISTS trip_plans (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    route_params JSONB,
    weather_data JSONB,
    plan_content JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trip_plans_user_id ON trip_plans(user_id);

-- ============================================
-- 7. 会话上下文表
-- ============================================
CREATE TABLE IF NOT EXISTS session_contexts (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) UNIQUE NOT NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    context_data JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_session_contexts_session_id ON session_contexts(session_id);
CREATE INDEX IF NOT EXISTS idx_session_contexts_updated ON session_contexts(updated_at);

-- ============================================
-- 插入默认管理员账号（密码: admin123 的 bcrypt hash）
-- ============================================
-- INSERT INTO users (username, password_hash, role) VALUES
-- ('admin', '$2b$12$LJ3m4ys3GZfnYMz8kVsKaOTS0mGynsFPk5BdKQJqNt4GtfXxDmHGi', 'admin');

-- ============================================
-- 8. 论坛分类表
-- ============================================
CREATE TABLE IF NOT EXISTS forum_categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    slug VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- 9. 论坛帖子表
-- ============================================
CREATE TABLE IF NOT EXISTS forum_posts (
    id SERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    category_id INT REFERENCES forum_categories(id),
    author_id INT REFERENCES users(id),
    images JSONB DEFAULT '[]',
    view_count INT DEFAULT 0,
    reply_count INT DEFAULT 0,
    is_pinned BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_forum_posts_category ON forum_posts(category_id);
CREATE INDEX IF NOT EXISTS idx_forum_posts_author ON forum_posts(author_id);
CREATE INDEX IF NOT EXISTS idx_forum_posts_created ON forum_posts(created_at DESC);

-- ============================================
-- 10. 论坛回复表
-- ============================================
CREATE TABLE IF NOT EXISTS forum_replies (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    post_id INT REFERENCES forum_posts(id) ON DELETE CASCADE,
    author_id INT REFERENCES users(id),
    images JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_forum_replies_post ON forum_replies(post_id);

-- ============================================
-- 插入默认论坛分类
-- ============================================
INSERT INTO forum_categories (name, slug, description, sort_order) VALUES
('路线讨论', 'route-discussion', '讨论徒步路线、攻略、经验', 1),
('装备交流', 'equipment-exchange', '装备评测、推荐、使用心得', 2),
('经验分享', 'experience-sharing', '户外经验、技巧、心得分享', 3),
('约伴出行', 'trip-partners', '寻找同伴、组队出行', 4),
('其他', 'other', '其他户外相关话题', 5)
ON CONFLICT (slug) DO NOTHING;