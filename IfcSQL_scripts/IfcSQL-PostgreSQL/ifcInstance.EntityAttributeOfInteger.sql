CREATE FOREIGN TABLE IF NOT EXISTS ifcinstance.entityattributeofinteger(
    "GlobalEntityInstanceId" bigint,
    "OrdinalPosition" integer,
    "TypeId" integer,
    "Value" integer
)
    SERVER mssql_ifcsql
    OPTIONS (schema_name 'ifcInstance', table_name 'EntityAttributeOfInteger');