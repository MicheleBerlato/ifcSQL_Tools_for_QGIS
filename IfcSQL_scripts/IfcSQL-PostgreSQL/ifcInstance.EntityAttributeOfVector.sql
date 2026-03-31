CREATE FOREIGN TABLE IF NOT EXISTS ifcinstance.entityattributeofvector(
    "GlobalEntityInstanceId" bigint,
    "OrdinalPosition" integer,
    "TypeId" integer,
	"X" double precision,
	"Y" double precision,
	"Z" double precision
)
    SERVER mssql_ifcsql
    OPTIONS (schema_name 'ifcInstance', table_name 'EntityAttributeOfVector');