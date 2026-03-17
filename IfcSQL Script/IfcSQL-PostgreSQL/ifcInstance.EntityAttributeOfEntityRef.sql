CREATE FOREIGN TABLE ifcinstance.EntityAttributeOfEntityRef (
"GlobalEntityInstanceId" bigint,
"OrdinalPosition" integer,
"TypeId" integer,
"Value" bigint
)
SERVER mssql_ifcsql
OPTIONS (
SCHEMA_NAME 'ifcInstance',
TABLE_NAME 'EntityAttributeOfEntityRef'
);
