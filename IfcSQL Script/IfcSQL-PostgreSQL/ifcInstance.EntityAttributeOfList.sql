CREATE FOREIGN TABLE IF NOT EXISTS ifcinstance.entityattributeoflist(
    "GlobalEntityInstanceId" bigint,
    "OrdinalPosition" integer,
    "TypeId" integer
)
    SERVER mssql_ifcsql
    OPTIONS (schema_name 'ifcInstance', table_name 'EntityAttributeOfList');