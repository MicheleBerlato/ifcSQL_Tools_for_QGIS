CREATE FOREIGN TABLE ifcinstance.EntityAttributeOfBoolean (
"GlobalEntityInstanceId" bigint,
"OrdinalPosition" integer,
"TypeId" integer,
"Value" boolean
)
SERVER mssql_ifcsql
OPTIONS (
SCHEMA_NAME 'ifcInstance',
TABLE_NAME 'EntityAttributeOfBoolean'
);
