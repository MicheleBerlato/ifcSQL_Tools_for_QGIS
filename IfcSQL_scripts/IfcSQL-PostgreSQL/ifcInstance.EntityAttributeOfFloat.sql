CREATE FOREIGN TABLE ifcinstance.EntityAttributeOfFloat (
"GlobalEntityInstanceId" bigint,
"OrdinalPosition" integer,
"TypeId" integer,
"Value" double precision
)
SERVER mssql_ifcsql
OPTIONS (
SCHEMA_NAME 'ifcInstance',
TABLE_NAME 'EntityAttributeOfFloat'
);
