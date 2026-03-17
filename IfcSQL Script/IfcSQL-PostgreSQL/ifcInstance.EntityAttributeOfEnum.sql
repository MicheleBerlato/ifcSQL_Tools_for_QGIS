CREATE FOREIGN TABLE ifcinstance.EntityAttributeOfEnum (
"GlobalEntityInstanceId" bigint,
"OrdinalPosition" integer,
"TypeId" integer,
"Value" integer
)
SERVER mssql_ifcsql
OPTIONS (
SCHEMA_NAME 'ifcInstance',
TABLE_NAME 'EntityAttributeOfEnum'
);
