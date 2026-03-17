CREATE FOREIGN TABLE IF NOT EXISTS ifcinstance.entityattributeofbinary(
    "GlobalEntityInstanceId" bigint,
    "OrdinalPosition" integer,
    "TypeId" integer,
    "Value" text
)
    SERVER mssql_ifcsql
    OPTIONS (schema_name 'ifcInstance', table_name 'EntityAttributeOfBinary');