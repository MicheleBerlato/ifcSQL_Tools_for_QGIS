CREATE FOREIGN TABLE ifcproject.EntityInstanceIdAssignment (
"ProjectId" integer,
"ProjectEntityInstanceId" bigint,
"GlobalEntityInstanceId" bigint
)

SERVER mssql_ifcsql
OPTIONS (
SCHEMA_NAME 'ifcProject',
TABLE_NAME 'EntityInstanceIdAssignment'
);
