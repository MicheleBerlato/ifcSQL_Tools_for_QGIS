CREATE FOREIGN TABLE ifcinstance.EntityAttributeOfString (
"GlobalEntityInstanceId" bigint,
"OrdinalPosition" integer,
"TypeId" integer,
"Value" text
)
SERVER mssql_ifcsql
OPTIONS (
SCHEMA_NAME 'ifcInstance',
TABLE_NAME 'EntityAttributeOfString'
);
