-- Table: ifcgeometry.entitygeometry

-- DROP TABLE IF EXISTS ifcgeometry.entitygeometry;

CREATE TABLE IF NOT EXISTS ifcgeometry.entitygeometry
(
    "GlobalId_MSSQL" bigint NOT NULL,
    "GlobalId_IfcFile" text COLLATE pg_catalog."default",
    "ProjectNumber_MSSQL" bigint,
    "ProjectName" text COLLATE pg_catalog."default", -- Inserito dopo ProjectNumber
    "IfcClass" text COLLATE pg_catalog."default",
    "EntityName" text COLLATE pg_catalog."default",  -- Inserito dopo IfcClass
    "Geometry" geometry,
    "Triangles" bigint,
    CONSTRAINT entitygeometry_pkey PRIMARY KEY ("GlobalId_MSSQL")
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS ifcgeometry.entitygeometry
    OWNER to postgres;

-- Index: idx_entitygeometry_geom

-- DROP INDEX IF EXISTS ifcgeometry.idx_entitygeometry_geom;

CREATE INDEX IF NOT EXISTS idx_entitygeometry_geom
    ON ifcgeometry.entitygeometry USING gist
    ("Geometry")
    TABLESPACE pg_default;