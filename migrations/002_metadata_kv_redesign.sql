-- 迁移：文件元数据系统重构
-- 将固定列 FileMetadata 表替换为灵活的 ObjectMetadata KV 表
-- 日期：2026-02-23

BEGIN;

-- ==================== 1. object 表新增 mime_type 列 ====================
ALTER TABLE object ADD COLUMN IF NOT EXISTS mime_type VARCHAR(127);

-- ==================== 2. physicalfile 表新增 checksum_sha256 列 ====================
ALTER TABLE physicalfile ADD COLUMN IF NOT EXISTS checksum_sha256 VARCHAR(64);

-- ==================== 3. 创建 objectmetadata KV 表 ====================
CREATE TABLE IF NOT EXISTS objectmetadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    object_id UUID NOT NULL REFERENCES object(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    value TEXT NOT NULL,
    is_public BOOLEAN NOT NULL DEFAULT false,
    CONSTRAINT uq_object_metadata_object_name UNIQUE (object_id, name)
);

CREATE INDEX IF NOT EXISTS ix_object_metadata_object_id
    ON objectmetadata (object_id);

-- ==================== 4. 创建 custompropertydefinition 表 ====================
CREATE TABLE IF NOT EXISTS custompropertydefinition (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    owner_id UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    type VARCHAR NOT NULL,
    icon VARCHAR(100),
    options JSON,
    default_value VARCHAR(500),
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_custompropertydefinition_owner_id
    ON custompropertydefinition (owner_id);

-- ==================== 5. 迁移旧数据（从 filemetadata 到 objectmetadata）====================
-- 将 filemetadata 中的数据迁移到 objectmetadata KV 格式
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'filemetadata') THEN
        -- 同时将 mime_type 上提到 object 表
        UPDATE object o
        SET mime_type = fm.mime_type
        FROM filemetadata fm
        WHERE fm.object_id = o.id AND fm.mime_type IS NOT NULL;

        -- 将 checksum_sha256 迁移到 physicalfile 表
        UPDATE physicalfile pf
        SET checksum_sha256 = fm.checksum_sha256
        FROM filemetadata fm
        JOIN object o ON fm.object_id = o.id
        WHERE o.physical_file_id = pf.id AND fm.checksum_sha256 IS NOT NULL;

        -- 迁移 width → exif:width
        INSERT INTO objectmetadata (id, object_id, name, value, is_public)
        SELECT gen_random_uuid(), object_id, 'exif:width', CAST(width AS TEXT), true
        FROM filemetadata WHERE width IS NOT NULL;

        -- 迁移 height → exif:height
        INSERT INTO objectmetadata (id, object_id, name, value, is_public)
        SELECT gen_random_uuid(), object_id, 'exif:height', CAST(height AS TEXT), true
        FROM filemetadata WHERE height IS NOT NULL;

        -- 迁移 duration → stream:duration
        INSERT INTO objectmetadata (id, object_id, name, value, is_public)
        SELECT gen_random_uuid(), object_id, 'stream:duration', CAST(duration AS TEXT), true
        FROM filemetadata WHERE duration IS NOT NULL;

        -- 迁移 bitrate → stream:bitrate
        INSERT INTO objectmetadata (id, object_id, name, value, is_public)
        SELECT gen_random_uuid(), object_id, 'stream:bitrate', CAST(bitrate AS TEXT), true
        FROM filemetadata WHERE bitrate IS NOT NULL;

        -- 删除旧表
        DROP TABLE filemetadata;
    END IF;
END $$;

COMMIT;
