CREATE FOREIGN TABLE ifcinstance.entity (
"GlobalEntityInstanceId" bigint,
"EntityTypeId" integer
)
SERVER mssql_ifcsql
OPTIONS (
SCHEMA_NAME 'ifcInstance',
TABLE_NAME 'Entity');
